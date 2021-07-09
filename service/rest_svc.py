import asyncio
import json
import logging
import os
import pandas as pd

from io import StringIO

UID = 'uid'


class RestService:
    def __init__(self, web_svc, reg_svc, data_svc, ml_svc, dao, externally_called=False):
        self.dao = dao
        self.data_svc = data_svc
        self.web_svc = web_svc
        self.ml_svc = ml_svc
        self.reg_svc = reg_svc
        self.queue = asyncio.Queue()  # task queue
        self.resources = []  # resource array
        self.externally_called = externally_called
        # A dictionary to keep track of report statuses we have seen
        self.seen_report_status = dict()
        # The offline attack dictionary TODO check and update differences from db (different attack names)
        attack_dict_loc = 'models/attack_dict.json'
        attack_dict_loc = os.path.join('tram', attack_dict_loc) if self.externally_called else attack_dict_loc
        with open(attack_dict_loc, 'r', encoding='utf_8') as attack_dict_f:
            self.json_tech = json.load(attack_dict_f)

    async def prepare_queue(self):
        """Function to add to the queue any reports left from a previous session."""
        reports = await self.dao.get('reports', dict(error=0, current_status='queue'))
        for report in reports:
            # Sentences from this report may have previously populated other db tables
            # Being selected from the queue will begin analysis again so delete previous progress
            await self.dao.delete('report_sentences', dict(report_uid=report[UID]))
            await self.dao.delete('report_sentence_hits', dict(report_uid=report[UID]))
            await self.dao.delete('original_html', dict(report_uid=report[UID]))
            # Add to the queue
            await self.queue.put(report)

    async def set_status(self, criteria=None):
        new_status, report_id = criteria['set_status'], criteria['report_id']
        if new_status == 'completed':
            unchecked = await self.data_svc.get_unconfirmed_attack_count(report_id=report_id)
            if unchecked:
                return dict(error='There are ' + str(unchecked) + ' attacks unconfirmed for this report.')
        await self.dao.update('reports', where=dict(uid=report_id), data=dict(current_status=new_status))
        self.seen_report_status[report_id] = new_status
        return dict(status='Report status updated to ' + new_status)

    async def delete_report(self, criteria=None):
        report_id = criteria['report_id']
        await self.dao.delete('reports', dict(uid=report_id))
        return dict(status='Successfully deleted report ' + report_id)

    async def remove_sentence(self, criteria=None):
        sen_id = criteria['sentence_id']
        # This is most likely a sentence ID sent through, so delete as expected
        await self.dao.delete('report_sentences', dict(uid=sen_id))
        # This could also be an image, so delete from original_html table too
        await self.dao.delete('original_html', dict(uid=sen_id))
        return dict(status='Successfully deleted item ' + sen_id)

    async def sentence_context(self, criteria=None):
        return await self.data_svc.get_active_sentence_hits(sentence_id=criteria[UID])

    async def confirmed_attacks(self, criteria=None):
        return await self.data_svc.get_confirmed_attacks(sentence_id=criteria['sentence_id'])

    async def insert_report(self, criteria=None):
        for i in range(len(criteria['title'])):
            criteria['title'][i] = await self.data_svc.get_unique_title(criteria['title'][i])
            temp_dict = dict(title=criteria['title'][i], url=criteria['url'][i], current_status='queue')
            temp_dict[UID] = await self.dao.insert_generate_uid('reports', temp_dict)
            await self.queue.put(temp_dict)
        asyncio.create_task(self.check_queue())  # check queue background task
        await asyncio.sleep(0.01)

    async def insert_csv(self, criteria=None):
        file = StringIO(criteria['file'])
        df = pd.read_csv(file)
        for row in range(df.shape[0]):
            temp_dict = dict(title=df['title'][row], url=df['url'][row], current_status='queue')
            temp_dict[UID] = await self.dao.insert_generate_uid('reports', temp_dict)
            await self.queue.put(temp_dict)
        asyncio.create_task(self.check_queue())
        await asyncio.sleep(0.01)

    async def check_queue(self):
        """
        description: executes as concurrent job, manages taking jobs off the queue and executing them.
        If a job is already being processed, wait until that job is done, then execute next job on queue.
        input: nil
        output: nil
        """
        for task in range(len(self.resources)):  # check resources for finished tasks
            if self.resources[task].done():
                del self.resources[task]  # delete finished tasks

        max_tasks = 1
        while self.queue.qsize() > 0:  # while there are still tasks to do....
            await asyncio.sleep(0.01)  # check resources and execute tasks
            if len(self.resources) >= max_tasks:  # if the resource pool is maxed out...
                while len(self.resources) >= max_tasks:  # check resource pool until a task is finished
                    for task in range(len(self.resources)):
                        if self.resources[task].done():
                            del self.resources[task]  # when task is finished, remove from resource pool
                    await asyncio.sleep(1)  # allow other tasks to run while waiting
                criteria = await self.queue.get()  # get next task off queue, and run it
                task = asyncio.create_task(self.start_analysis(criteria))
                self.resources.append(task)
            else:
                criteria = await self.queue.get()  # get next task off queue and run it
                task = asyncio.create_task(self.start_analysis(criteria))
                self.resources.append(task)

    async def start_analysis(self, criteria=None):
        report_id = criteria[UID]
        logging.info('Beginning analysis for ' + report_id)
        tech_data = await self.data_svc.get_techniques()
        techniques = {}
        for row in tech_data:
            await asyncio.sleep(0.01)
            # skip software
            if 'tool' in row['tid'] or 'malware' in row['tid']:
                continue
            else:
                # query for true positives
                true_pos = await self.dao.get('true_positives', dict(attack_uid=row[UID]))
                tp, fp = [], []
                for t in true_pos:
                    tp.append(t['true_positive'])
                # query for false negatives
                false_neg = await self.dao.get('false_negatives', dict(attack_uid=row[UID]))
                for f in false_neg:
                    tp.append(f['false_negative'])
                # query for false positives for this technique
                false_positives = await self.dao.get('false_positives', dict(attack_uid=row[UID]))
                for fps in false_positives:
                    fp.append(fps['false_positive'])

                techniques[row[UID]] = {'id': row['tid'], 'name': row['name'], 'similar_words': [], 'example_uses': tp,
                                        'false_positives': fp}

        original_html, newspaper_article = await self.web_svc.map_all_html(criteria['url'])
        if original_html is None and newspaper_article is None:
            logging.error('Skipping report; could not download url ' + criteria['url'])
            await self.dao.update('reports', where=dict(uid=report_id), data=dict(error=1))
            return

        html_data = newspaper_article.text.replace('\n', '<br>')
        article = dict(title=criteria['title'], html_text=html_data)
        list_of_legacy, list_of_techs = await self.data_svc.ml_reg_split(self.json_tech)

        true_negatives = await self.ml_svc.get_true_negs()
        # Here we build the sentence dictionary
        html_sentences = self.web_svc.tokenize_sentence(article['html_text'])
        model_dict = await self.ml_svc.build_pickle_file(list_of_techs, self.json_tech, true_negatives)

        ml_analyzed_html = await self.ml_svc.analyze_html(list_of_techs, model_dict, html_sentences)
        regex_patterns = await self.dao.get('regex_patterns')
        reg_analyzed_html = self.reg_svc.analyze_html(regex_patterns, html_sentences)

        # Merge ML and Reg hits
        analyzed_html = await self.ml_svc.combine_ml_reg(ml_analyzed_html, reg_analyzed_html)

        for sentence in analyzed_html:
            if sentence['ml_techniques_found']:
                await self.ml_svc.ml_techniques_found(report_id, sentence)
            elif sentence['reg_techniques_found']:
                await self.reg_svc.reg_techniques_found(report_id, sentence)
            else:
                data = dict(report_uid=report_id, text=sentence['text'], html=sentence['html'], found_status=0)
                await self.dao.insert_generate_uid('report_sentences', data)

        for element in original_html:
            html_element = dict(report_uid=report_id, text=element['text'], tag=element['tag'], found_status=0)
            await self.dao.insert_generate_uid('original_html', html_element)

        # Update card to reflect the end of queue
        await self.dao.update('reports', where=dict(uid=report_id), data=dict(current_status='needs_review'))
        logging.info('Finished analysing report ' + report_id)

    async def add_attack(self, criteria=None):
        # The sentence and attack IDs
        sen_id, attack_id = criteria['sentence_id'], criteria['attack_uid']
        # Get the attack information for this attack id
        attack_dict = await self.dao.get('attack_uids', dict(uid=attack_id))
        # Get the report sentence information for the sentence id
        sentence_dict = await self.dao.get('report_sentences', dict(uid=sen_id))
        # Get the sentence to insert by removing html markup
        sentence_to_insert = await self.web_svc.remove_html_markup_and_found(sentence_dict[0]['text'])
        # A flag to determine if the model initially predicted this attack for this sentence
        model_initially_predicted = False
        # The list of SQL commands to run in a single transaction
        sql_commands = []
        # Check this sentence + attack combination isn't already in report_sentence_hits
        historic_hits = await self.dao.get('report_sentence_hits', dict(sentence_id=sen_id, attack_uid=attack_id))
        if historic_hits:
            returned_hit = historic_hits[0]
            # If this attack is already confirmed for this sentence, we are not going to do anything further
            if returned_hit['confirmed']:
                return dict(status='ignored; attack already confirmed')
            # Else update the hit as active and confirmed
            sql_commands.append(await self.dao.update(
                'report_sentence_hits', where=dict(sentence_id=sen_id, attack_uid=attack_id),
                data=dict(active_hit=1, confirmed=1), return_sql=True))
            # Update model_initially_predicted flag using returned historic_hits
            model_initially_predicted = returned_hit['initial_model_match']
        else:
            # Insert new row in the report_sentence_hits database table to indicate a new confirmed technique
            # This is needed to ensure that requests to get all confirmed techniques works correctly
            sql_commands.append(await self.dao.insert_generate_uid(
                'report_sentence_hits', dict(sentence_id=sen_id, attack_uid=attack_id,
                                             attack_technique_name=attack_dict[0]['name'],
                                             report_uid=sentence_dict[0]['report_uid'],
                                             attack_tid=attack_dict[0]['tid'], confirmed=1), return_sql=True))
        # As this will now be either a true positive or false negative, ensure it is not a false positive too
        sql_commands.append(await self.dao.delete('false_positives', dict(sentence_id=sen_id, attack_uid=attack_id),
                                                  return_sql=True))
        # If the ML model correctly predicted this attack, then it is a true positive
        if model_initially_predicted:
            existing = len(await self.dao.get('true_positives', dict(sentence_id=sen_id, attack_uid=attack_id)))
            if not existing:  # Only add to the true positives table if it's not already there
                sql_commands.append(await self.dao.insert_generate_uid(
                    'true_positives', dict(sentence_id=sen_id, attack_uid=attack_id, true_positive=sentence_to_insert),
                    return_sql=True))
        else:
            # Insert new row in the false_negatives database table as model incorrectly flagged as not an attack
            existing = len(await self.dao.get('false_negatives', dict(sentence_id=sen_id, attack_uid=attack_id)))
            if not existing:  # Only add to the false negatives table if it's not already there
                sql_commands.append(await self.dao.insert_generate_uid(
                    'false_negatives', dict(sentence_id=sen_id, attack_uid=attack_id,
                                            false_negative=sentence_to_insert), return_sql=True))
        # If the found_status for the sentence id is set to false when adding a missing technique
        # then update the found_status value to true for the sentence id in the report_sentence table 
        if sentence_dict[0]['found_status'] == 0:
            sql_commands.append(await self.dao.update(
                'report_sentences', where=dict(uid=sen_id), data=dict(found_status=1), return_sql=True))
        # Run the updates, deletions and insertions for this method altogether
        await self.dao.run_sql_list(sql_list=sql_commands)
        # As a technique has been added, ensure the report's status reflects analysis has started
        await self.check_report_status(report_id=sentence_dict[0]['report_uid'])
        # Return status message
        return dict(status='attack accepted')

    async def reject_attack(self, criteria=None):
        # The sentence and attack IDs
        sen_id, attack_id = criteria['sentence_id'], criteria['attack_uid']
        # Get the report sentence information for the sentence id
        sentence_dict = await self.dao.get('report_sentences', dict(uid=sen_id))
        # Get the sentence to insert by removing html markup
        sentence_to_insert = await self.web_svc.remove_html_markup_and_found(sentence_dict[0]['text'])
        # The list of SQL commands to run in a single transaction
        sql_commands = [
            # Delete any sentence-hits where the model didn't initially guess the attack
            await self.dao.delete(
                'report_sentence_hits', dict(sentence_id=sen_id, attack_uid=attack_id, initial_model_match=0),
                return_sql=True),
            # For sentence-hits where the model did guess the attack, flag as inactive and unconfirmed
            await self.dao.update(
                'report_sentence_hits', where=dict(sentence_id=sen_id, attack_uid=attack_id, initial_model_match=1),
                data=dict(active_hit=0, confirmed=0), return_sql=True),
            # This sentence may have previously been added as a true positive or false negative; delete these
            await self.dao.delete('true_positives', dict(sentence_id=sen_id, attack_uid=attack_id), return_sql=True),
            await self.dao.delete('false_negatives', dict(sentence_id=sen_id, attack_uid=attack_id), return_sql=True)
        ]
        # Check if the ML model initially predicted this attack
        model_initially_predicted = len(await self.dao.get(
            'report_sentence_hits', dict(sentence_id=sen_id, attack_uid=attack_id, initial_model_match=1)))
        # If it did, then this is a false positive
        if model_initially_predicted:
            existing = len(await self.dao.get('false_positives', dict(sentence_id=sen_id, attack_uid=attack_id)))
            if not existing:  # Only add to the false positives table if it's not already there
                sql_commands.append(await self.dao.insert_generate_uid(
                    'false_positives', dict(sentence_id=sen_id, attack_uid=attack_id,
                                            false_positive=sentence_to_insert), return_sql=True))
        # Check if this sentence has other attacks mapped to it
        number_of_techniques = await self.dao.get('report_sentence_hits', equal=dict(sentence_id=sen_id, active_hit=1),
                                                  not_equal=dict(attack_uid=attack_id))
        # If it doesn't, update the sentence found-status to 0 (false)
        if len(number_of_techniques) == 0:
            sql_commands.append(await self.dao.update(
                'report_sentences', where=dict(uid=sen_id), data=dict(found_status=0), return_sql=True))
            last = dict(status='true')
        else:
            last = dict(status='false', id=sen_id)
        # Run the updates, deletions and insertions for this method altogether
        await self.dao.run_sql_list(sql_list=sql_commands)
        # As a technique has been rejected, ensure the report's status reflects analysis has started
        await self.check_report_status(report_id=sentence_dict[0]['report_uid'])
        return dict(status='attack rejected', last=last)

    async def check_report_status(self, report_id='', status='in_review'):
        """Function to check a report is of the given status and updates it if not."""
        # A quick check without a db call; if the status is right, exit method
        if self.seen_report_status.get(report_id) == status:
            return
        # Check the db
        report_dict = await self.dao.get('reports', dict(uid=report_id))
        if report_dict[0]['current_status'] == status:
            # Before exiting method as status matches, update dictionary for future checks
            self.seen_report_status[report_id] = status
            return
        # Update the report status in the db and the dictionary variable for future checks
        await self.dao.update('reports', where=dict(uid=report_id), data=dict(current_status=status))
        self.seen_report_status[report_id] = status
