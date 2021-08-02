import asyncio
import json
import logging
import os
import pandas as pd
import re

from contextlib import suppress
from enum import Enum, unique
from io import StringIO
from urllib.parse import unquote

UID = 'uid'
REST_IGNORED = dict(ignored=1)
REST_SUCCESS = dict(success=1)


@unique
class ReportStatus(Enum):
    QUEUE = 'queue'
    NEEDS_REVIEW = 'needs_review'
    IN_REVIEW = 'in_review'
    COMPLETED = 'completed'


class RestService:
    def __init__(self, web_svc, reg_svc, data_svc, ml_svc, dao, externally_called=False):
        self.QUEUE_LIMIT = 20
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

    @staticmethod
    def get_status_enum():
        return ReportStatus

    async def prepare_queue(self):
        """Function to add to the queue any reports left from a previous session."""
        reports = await self.dao.get('reports', dict(error=0, current_status=ReportStatus.QUEUE.value))
        for report in reports:
            # Sentences from this report may have previously populated other db tables
            # Being selected from the queue will begin analysis again so delete previous progress
            await self.dao.delete('report_sentences', dict(report_uid=report[UID]))
            await self.dao.delete('report_sentence_hits', dict(report_uid=report[UID]))
            await self.dao.delete('original_html', dict(report_uid=report[UID]))
            # Add to the queue
            await self.queue.put(report)

    async def set_status(self, criteria=None):
        default_error = dict(error='Error setting status.')
        try:
            # Check for malformed request parameters
            new_status, report_title = criteria['set_status'], criteria['report_title']
        except KeyError:
            return default_error
        # Get the report data from the provided report title
        try:
            report_dict = await self.dao.get('reports', dict(title=unquote(report_title)))
        except TypeError:  # Thrown when unquote() receives a non-string type
            return default_error
        try:
            report_id = report_dict[0][UID]
        except (KeyError, IndexError):  # Thrown if the report title did not match any report in the db
            return default_error
        # May be refined to allow reverting statuses in future - should use enum to check valid status
        if new_status == ReportStatus.COMPLETED.value:
            # Check there are no unconfirmed attacks
            unchecked = await self.data_svc.get_unconfirmed_attack_count(report_id=report_id)
            if unchecked:
                return dict(error='There are ' + str(unchecked) + ' attacks unconfirmed for this report.', alert_user=1)
            # Check the report status is not queued (because queued reports will have 0 unchecked attacks)
            if await self.check_report_status(report_id=report_id, status=ReportStatus.QUEUE.value):
                return default_error
            # Finally, update the status
            await self.dao.update('reports', where=dict(uid=report_id), data=dict(current_status=new_status))
            self.seen_report_status[report_id] = new_status
            return REST_SUCCESS
        else:
            return default_error

    async def delete_report(self, criteria=None):
        default_error = dict(error='Error deleting report.')
        try:
            # Check for malformed request parameters
            report_title = criteria['report_title']
        except KeyError:
            return default_error
        # Get the report data from the provided report title
        try:
            report = await self.dao.get('reports', dict(title=unquote(report_title)))
        except TypeError:  # Thrown when unquote() receives a non-string type
            return default_error
        try:
            report_id, r_status, r_error = report[0][UID], report[0]['current_status'], report[0]['error']
        except (KeyError, IndexError):  # Thrown if the report title is not in the db or db record is malformed
            return default_error
        # Check a queued, error-free report ID hasn't been provided -> this may be mid-analysis
        if r_status == ReportStatus.QUEUE.value and r_error == 0:
            return default_error
        # Proceed with delete
        await self.dao.delete('reports', dict(uid=report_id))
        return REST_SUCCESS

    async def remove_sentence(self, criteria=None):
        default_error = dict(error='Error removing item.')
        try:
            # Check for malformed request parameters
            sen_id = criteria['sentence_id']
        except KeyError:
            return default_error
        # Determine if sentence or image
        sentence_dict = await self.dao.get('report_sentences', dict(uid=sen_id))
        img_dict = await self.dao.get('original_html', dict(uid=sen_id))
        # Get the report ID from either
        report_id = None
        with suppress(KeyError, IndexError):
            report_id = sentence_dict[0]['report_uid']
        with suppress(KeyError, IndexError):
            report_id = img_dict[0]['report_uid']
        # Use this report ID to determine its status and if we can continue
        if not await self.check_report_status_multiple(
                report_id=report_id, statuses=[ReportStatus.IN_REVIEW.value, ReportStatus.NEEDS_REVIEW.value]):
            return default_error
        # This is most likely a sentence ID sent through, so delete as expected
        await self.dao.delete('report_sentences', dict(uid=sen_id))
        # This could also be an image, so delete from original_html table too
        await self.dao.delete('original_html', dict(uid=sen_id))
        return REST_SUCCESS

    async def sentence_context(self, criteria=None):
        try:
            # Check for malformed request parameters
            sen_id = criteria['sentence_id']
        except KeyError:
            return dict(error='Error retrieving sentence info.')
        return await self.data_svc.get_active_sentence_hits(sentence_id=sen_id)

    async def confirmed_attacks(self, criteria=None):
        try:
            # Check for malformed request parameters
            sen_id = criteria['sentence_id']
        except KeyError:
            return dict(error='Error retrieving sentence info.')
        return await self.data_svc.get_confirmed_attacks(sentence_id=sen_id)

    async def insert_report(self, criteria=None):
        try:
            # Check for malformed request parameters
            criteria['title']
        except KeyError:
            return dict(error='Error inserting report(s).')
        return await self._insert_batch_reports(criteria, len(criteria['title']))

    async def insert_csv(self, criteria=None):
        try:
            df = self.verify_csv(criteria['file'])
        except (TypeError, ValueError) as e:  # Any errors occurring from the csv-checks
            return dict(error=str(e), alert_user=1)
        except KeyError:  # Check for malformed request parameters
            return dict(error='Error inserting report(s).')
        return await self._insert_batch_reports(df, df.shape[0])

    async def _insert_batch_reports(self, batch, row_count):
        default_error = dict(error='Error inserting report(s).')
        for row in range(row_count):
            try:
                title, url = batch['title'][row].strip(), batch['url'][row].strip()
            # Check for malformed request parameters; AttributeError thrown if not strings
            except (AttributeError, KeyError):
                return default_error
            try:
                # Enforce http on urls that do not begin with http(s)
                prefix_check = re.match('^https?://', url, re.IGNORECASE)
                url = 'http://' + url if prefix_check is None else url
                self.web_svc.verify_url(url=url)
            # Raised if verify_url() fails
            except ValueError:
                return default_error
            # Ensure the report has a unique title
            title = await self.data_svc.get_unique_title(title)
            # Set up a temporary dictionary to represent db object
            temp_dict = dict(title=title, url=url, current_status=ReportStatus.QUEUE.value)
            # Insert report into db and update temp_dict with inserted ID from db
            temp_dict[UID] = await self.dao.insert_generate_uid('reports', temp_dict)
            # Finally, update queue and check queue when batch is finished
            await self.queue.put(temp_dict)
        asyncio.create_task(self.check_queue())
        return REST_SUCCESS

    @staticmethod
    def verify_csv(file_param):
        """Function to return a dataframe from csv-like text."""
        # Check if the text can be converted into a file and then converted into a dataframe (df)
        try:
            file = StringIO(file_param)
            df = pd.read_csv(file)
        except Exception:
            raise TypeError('Could not parse file')
        # Next, check if only the columns 'title' and 'url' exist in the df
        title, url = 'title', 'url'
        columns = list(df.columns)
        columns_error = 'Two columns have not been specified (\'Title\',\'URL\')'
        # Check if exactly 2 columns have been specified
        if len(columns) != 2:
            raise ValueError(columns_error)
        # Rename the columns to ensure the column names have the same case (lower case)
        new_columns = dict()
        # Check that both 'title' and 'url' appear in the columns; raise error for anything different
        for col in columns:
            if col.strip().lower() == title:
                new_columns[col] = title
            elif col.strip().lower() == url:
                new_columns[col] = url
            else:
                raise ValueError(columns_error)
        # Check that the new columns' length is exactly 2
        if len(new_columns) != 2:
            raise ValueError(columns_error)
        # Return new df with renamed columns
        return df.rename(columns=new_columns)

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
            criteria = await self.queue.get()  # get next task off queue and run it
            task = asyncio.create_task(self.start_analysis(criteria))
            self.resources.append(task)

    async def start_analysis(self, criteria=None):
        report_id = criteria[UID]
        logging.info('Beginning analysis for ' + report_id)

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
        await self.dao.update('reports', where=dict(uid=report_id),
                              data=dict(current_status=ReportStatus.NEEDS_REVIEW.value))
        logging.info('Finished analysing report ' + report_id)

    async def add_attack(self, criteria=None):
        try:
            # The sentence and attack IDs
            sen_id, attack_id = criteria['sentence_id'], criteria['attack_uid']
        except KeyError:
            return dict(error='Error adding attack.')
        # Get the attack information for this attack id
        attack_dict = await self.dao.get('attack_uids', dict(uid=attack_id))
        # Get the report sentence information for the sentence id
        sentence_dict = await self.dao.get('report_sentences', dict(uid=sen_id))
        # Check the method can continue
        checks = await self._pre_add_reject_attack_checks(sen_id=sen_id, sentence_dict=sentence_dict,
                                                          attack_id=attack_id, attack_dict=attack_dict)
        if checks is not None:
            return checks
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
                return REST_IGNORED
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
        await self.check_report_status(report_id=sentence_dict[0]['report_uid'], update_if_false=True)
        # Return status message
        return REST_SUCCESS

    async def reject_attack(self, criteria=None):
        try:
            # The sentence and attack IDs
            sen_id, attack_id = criteria['sentence_id'], criteria['attack_uid']
        except KeyError:
            return dict(error='Error rejecting attack.')
        # Get the report sentence information for the sentence id
        sentence_dict = await self.dao.get('report_sentences', dict(uid=sen_id))
        # Get the attack information for this attack id
        attack_dict = await self.dao.get('attack_uids', dict(uid=attack_id))
        # Check the method can continue
        checks = await self._pre_add_reject_attack_checks(sen_id=sen_id, sentence_dict=sentence_dict,
                                                          attack_id=attack_id, attack_dict=attack_dict)
        if checks is not None:
            return checks
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
        # Run the updates, deletions and insertions for this method altogether
        await self.dao.run_sql_list(sql_list=sql_commands)
        # As a technique has been rejected, ensure the report's status reflects analysis has started
        await self.check_report_status(report_id=sentence_dict[0]['report_uid'], update_if_false=True)
        return REST_SUCCESS

    async def _pre_add_reject_attack_checks(self, sen_id='', sentence_dict=None, attack_id='', attack_dict=None):
        """Function to check for adding or rejecting attacks, enough sentence and attack data has been given."""
        # Check there is sentence data to access
        try:
            a, b = sentence_dict[0]['text'], sentence_dict[0]['found_status']
            report_id = sentence_dict[0]['report_uid']
        except (KeyError, IndexError):
            return dict(error='Error. Please quote SE%s when contacting admin.' % sen_id, alert_user=1)
        # Check there is attack data to access
        try:
            attack_dict[0]['name'], attack_dict[0]['tid']
        except (KeyError, IndexError):
            return dict(error='Error. Please quote AE%s when contacting admin.' % attack_id, alert_user=1)
        # Check the report status is acceptable
        if not await self.check_report_status_multiple(report_id=report_id,
                                                       statuses=[ReportStatus.IN_REVIEW.value,
                                                                 ReportStatus.NEEDS_REVIEW.value]):
            return dict(error='Error. Please quote RSE%s when contacting admin.' % report_id, alert_user=1)
        return None

    async def check_report_status(self, report_id='', status=ReportStatus.IN_REVIEW.value, update_if_false=False):
        """Function to check a report is of the given status and updates it if not."""
        # No report ID, no result
        if report_id is None:
            return None
        # A quick check without a db call; if the status is right, exit method
        if self.seen_report_status.get(report_id) == status:
            return True
        # Check the db
        report_dict = await self.dao.get('reports', dict(uid=report_id))
        try:
            db_status = report_dict[0]['current_status']
        except (KeyError, IndexError):
            return None
        if db_status == status:
            # Before exiting method as status matches, update dictionary for future checks
            self.seen_report_status[report_id] = db_status
            return True
        # Report status is not a match; finally update db (if requested) and return boolean
        if update_if_false:
            # Update the report status in the db and the dictionary variable for future checks
            await self.dao.update('reports', where=dict(uid=report_id), data=dict(current_status=status))
            self.seen_report_status[report_id] = status
            return True
        else:
            self.seen_report_status[report_id] = db_status
            return False

    async def check_report_status_multiple(self, report_id='', statuses=[]):
        """Function to check a report is one of the given statuses."""
        # No report ID, no result
        if report_id is None:
            return None
        # A quick check without a db call; if the status is right, exit method
        if self.seen_report_status.get(report_id) in statuses:
            return True
        # Check the db
        report_dict = await self.dao.get('reports', dict(uid=report_id))
        try:
            db_status = report_dict[0]['current_status']
        except (KeyError, IndexError):
            return None
        if db_status in statuses:
            # Before exiting method as status matches, update dictionary for future checks
            self.seen_report_status[report_id] = db_status
            return True
        # Report status is not a match
        return False
