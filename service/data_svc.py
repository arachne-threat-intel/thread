import os
import re
import json
import logging

from stix2 import TAXIICollectionSource, Filter

try:
    # This is the appropriate import for taxii-client v2.x; this might fail in older taxii-client versions
    from taxii2client.v20 import Collection
except ModuleNotFoundError:
    # The original import statement used in case of error
    from taxii2client import Collection


def defang_text(text):
    """
    Function to normalize quoted data to be sql compliant
    :param text: Text to be defang'd
    :return: Defang'd text
    """
    text = text.replace("'", "''")
    text = text.replace('"', '""')
    return text


class DataService:

    def __init__(self, dao, web_svc, externally_called=False):
        self.dao = dao
        self.web_svc = web_svc
        self.externally_called = externally_called

    async def reload_database(self, schema='conf/schema.sql'):
        """
        Function to reinitialize the database with the packaged schema
        :param schema: SQL schema file to build database from
        :return: nil
        """
        schema = os.path.join('tram', schema) if self.externally_called else schema
        with open(schema) as schema:
            await self.dao.build((schema.read()))

    async def insert_attack_stix_data(self):
        """
        Function to pull stix/taxii information and insert in to the local db
        :return: status code
        """
        logging.info('Downloading ATT&CK data from STIX/TAXII...')
        attack = {}
        collection = Collection("https://cti-taxii.mitre.org/stix/collections/95ecc380-afe9-11e4-9b6c-751b66dd541e/")
        tc_source = TAXIICollectionSource(collection)
        filter_objs = {"techniques": Filter("type", "=", "attack-pattern"),
                       "groups": Filter("type", "=", "intrusion-set"), "malware": Filter("type", "=", "malware"),
                       "tools": Filter("type", "=", "tool"), "relationships": Filter("type", "=", "relationship")}
        for key in filter_objs:
            attack[key] = tc_source.query(filter_objs[key])
        references = {}

        # add all of the patterns and dictionary keys/values for each technique and software
        for i in attack["techniques"]:
            references[i["id"]] = {"name": i["name"], "id": i["external_references"][0]["external_id"],
                                   "example_uses": [],
                                   "description": i['description'].replace('<code>', '').replace('</code>', '').replace(
                                       '\n', '').encode('ascii', 'ignore').decode('ascii') if hasattr(i, "description")
                                   else 'No description provided',
                                   "similar_words": [i["name"]]}

        for i in attack["relationships"]:
            if i["relationship_type"] == 'uses':
                if 'attack-pattern' in i["target_ref"]:
                    use = i["description"]
                    # remove unnecessary strings, fix unicode errors
                    use = use.replace('<code>', '').replace('</code>', '').replace('"', "").replace(',', '').replace(
                        '\t', '').replace('  ', ' ').replace('\n', '').encode('ascii', 'ignore').decode('ascii')
                    find_pattern = re.compile('\[.*?\]\(.*?\)')  # get rid of att&ck reference (name)[link to site]
                    m = find_pattern.findall(use)
                    if len(m) > 0:
                        for j in m:
                            use = use.replace(j, '')
                            if use[0:2] == '\'s':
                                use = use[3:]
                            elif use[0] == ' ':
                                use = use[1:]
                    # combine all the examples to one list
                    references[i["target_ref"]]["example_uses"].append(use)

        for i in attack["malware"]:
            if 'description' not in i:  # some software do not have description, example: darkmoon https://attack.mitre.org/software/S0209
                continue
            else:
                references[i["id"]] = {"id": i['id'], "name": i["name"], "description": i["description"],
                                       "examples": [], "example_uses": [], "similar_words": [i["name"]]}
        for i in attack["tools"]:
            references[i["id"]] = {"id": i['id'], "name": i["name"], "description": i["description"], "examples": [],
                                   "example_uses": [], "similar_words": [i["name"]]}

        attack_data = references
        logging.info("Finished...now creating the database.")

        cur_uids = await self.dao.get('attack_uids') if await self.dao.get('attack_uids') else []
        cur_items = [i['uid'] for i in cur_uids]
        for k, v in attack_data.items():
            if k not in cur_items:
                await self.dao.insert('attack_uids', dict(uid=k, description=defang_text(v['description']), tid=v['id'],
                                                          name=v['name']))
                if 'regex_patterns' in v:
                    [await self.dao.insert_generate_uid('regex_patterns',
                                                        dict(attack_uid=k, regex_pattern=defang_text(x)))
                     for x in v['regex_patterns']]
                if 'similar_words' in v:
                    [await self.dao.insert_generate_uid('similar_words',
                                                        dict(attack_uid=k, similar_word=defang_text(x)))
                     for x in v['similar_words']]
                if 'false_negatives' in v:
                    [await self.dao.insert_generate_uid('false_negatives',
                                                        dict(attack_uid=k, false_negative=defang_text(x)))
                     for x in v['false_negatives']]
                if 'false_positives' in v:
                    [await self.dao.insert_generate_uid('false_positives',
                                                        dict(attack_uid=k, false_positive=defang_text(x)))
                     for x in v['false_positives']]
                if 'true_positives' in v:
                    [await self.dao.insert_generate_uid('true_positives',
                                                        dict(attack_uid=k, true_positive=defang_text(x)))
                     for x in v['true_positives']]
                if 'example_uses' in v:
                    [await self.dao.insert_generate_uid('true_positives',
                                                        dict(attack_uid=k, true_positive=defang_text(x)))
                     for x in v['example_uses']]
        logging.info('[!] DB Item Count: {}'.format(len(await self.dao.get('attack_uids'))))

    async def insert_attack_json_data(self, buildfile):
        """
        Function to read in the enterprise attack json file and insert data into the database
        :param buildfile: Enterprise attack json file to build from
        :return: nil
        """
        cur_items = [x['uid'] for x in await self.dao.get('attack_uids')]
        logging.debug('[#] {} Existing items in the DB'.format(len(cur_items)))
        with open(buildfile, 'r') as infile:
            attack_dict = json.load(infile)
            loaded_items = {}
            # Extract all TIDs
            for item in attack_dict['objects']:
                if 'external_references' in item:
                    # Filter down
                    if any(x for x in item['external_references'] if x['source_name'] == 'mitre-attack'):
                        items = [x['external_id'] for x in item['external_references'] if
                                 x['source_name'] == 'mitre-attack']
                        if len(items) == 1:
                            tid = items[0]
                            # Add in
                            if tid.startswith('T') and not tid.startswith('TA'):
                                if item['type'] == "attack-pattern":
                                    loaded_items[item['id']] = {'id': tid, 'name': item['name'],
                                                                'examples': [],
                                                                'similar_words': [],
                                                                'description': item['description']
                                                                if hasattr(item, 'description')
                                                                else 'No description provided',
                                                                'example_uses': []}
                        else:
                            logging.critical('[!] Error: multiple MITRE sources: {} {}'.format(item['id'], items))
            # Extract uses for all TIDs
            for item in attack_dict['objects']:
                if item['type'] == 'relationship':
                    if item["relationship_type"] == 'uses':
                        if 'description' in item:
                            normalized_example = item['description'].replace('<code>', '').replace('</code>',
                                       '').replace('\n', '').encode('ascii', 'ignore').decode('ascii')
                            # Remove att&ck reference (name)[link to site]
                            normalized_example = re.sub('\[.*?\]\(.*?\)', '', normalized_example)
                            if item['target_ref'].startswith('attack-pattern'):
                                if item['target_ref'] in loaded_items:
                                    loaded_items[item['target_ref']]['example_uses'].append(normalized_example)
                                else:
                                    logging.critical('[!] Found target_ref not in loaded data: {}'.format(item['target_ref']))
        logging.debug("[#] {} Techniques found in input file".format(len(loaded_items)))
        # Deduplicate input data from existing items in the DB
        to_add = {x: y for x, y in loaded_items.items() if x not in cur_items}
        logging.debug('[#] {} Techniques found that are not in the existing database'.format(len(to_add)))
        for k, v in to_add.items():
            await self.dao.insert('attack_uids', dict(uid=k, description=defang_text(v['description']), tid=v['id'],
                                                      name=v['name']))
            if 'example_uses' in v:
                [await self.dao.insert_generate_uid('true_positives', dict(attack_uid=k, true_positive=defang_text(x)))
                 for x in v['example_uses']]

    async def status_grouper(self, status):
        reports = await self.dao.get('reports', dict(current_status=status))
        for report in reports:
            report.update(dict(link="/edit/{}".format(report['title'])))
        return reports

    async def build_sentences(self, report_id):
        sentences = await self.dao.get('report_sentences', dict(report_uid=report_id))
        for sentence in sentences:
            sentence['hits'] = await self.get_active_sentence_hits(sentence_id=sentence['uid'])
            if await self.dao.get('true_positives', dict(sentence_id=sentence['uid'])):
                sentence['confirmed'] = 'true'
            else:
                sentence['confirmed'] = 'false'
        return sentences

    async def get_techniques(self):
        techniques = await self.dao.get('attack_uids')
        return techniques

    async def get_confirmed_techniques(self, report_id):
        # The SQL select join query to retrieve the confirmed techniques for the report from the database
        select_join_query = (
            "SELECT report_sentences.uid, report_sentence_hits.attack_uid, report_sentence_hits.report_uid, "
            "report_sentence_hits.attack_tid, report_sentences.text, report_sentence_hits.initial_model_match "
            "FROM (report_sentences INNER JOIN report_sentence_hits "
            "ON report_sentences.uid = report_sentence_hits.sentence_id) "
            "WHERE report_sentence_hits.report_uid = ? AND report_sentence_hits.confirmed = 1")
        # Run the SQL select join query
        return await self.dao.raw_select(select_join_query, parameters=tuple([report_id]))

    async def get_confirmed_techniques_for_report(self, report_id):
        # Get the confirmed hits
        hits = await self.get_confirmed_techniques(report_id)
        techniques = []
        for hit in hits:
            # For each confirmed technique returned,
            # create a technique object and add it to the list of techniques.
            technique = {'model_score': hit['initial_model_match'], 'techniqueID': hit['attack_tid'],
                         'comment': self.web_svc.remove_html_markup_and_found(hit['text'])}
            techniques.append(technique)
        # Return the list of confirmed techniques
        return techniques

    async def get_active_sentence_hits(self, sentence_id=''):
        """Function to retrieve active sentence hits (and ignoring historic ones, e.g. a model's initial prediction)."""
        return await self.dao.get('report_sentence_hits', dict(sentence_id=sentence_id, active_hit=1))

    async def get_unique_title(self, title):
        """
        Function to retrieve a unique title whilst checking for a given title in the database.
        :param title: The current title to check for duplicates in the database.
        :return: A title that will be unique in the reports table of the database.
        """
        # Check for any duplicates of the given title
        existing = await self.dao.get('reports', dict(title=title))
        # If there is already a report with this title...
        if existing:
            # Search for duplicates in the reports table like title_1, title_2, etc
            # Using 'like' operator means any literal %s and _s need to be escaped
            title_escaped = title.replace('%', '\\%').replace('_', '\\_')
            # The query with a qmark placeholder for the title and stating an escape character is used
            query = 'SELECT * FROM reports WHERE title LIKE ? ESCAPE \'\\\';'
            # Run the query with the escaped-title as a parameter plus a _X suffix
            underscore_hits = await self.dao.raw_select(query, parameters=(f'{title_escaped}\\_%',))
            # If we have matches...
            if underscore_hits:
                # Collect all the numerical suffixes
                suffixes = set()
                # Collect them by iterating through each matched report...
                for match in underscore_hits:
                    match_title = match.get('title')
                    if match_title:
                        # and obtaining substring in title after last occurrence of _
                        suffix = match_title.rpartition('_')[-1]
                        # Add this to the suffixes list if it's a number else skip to next match
                        try:
                            suffixes.add(int(suffix))
                        except ValueError:
                            pass
                # If we have numerical suffixes...
                if suffixes:
                    # Get the range from 1 to the max suffix number collected (+1 as range() doesn't include this)
                    true_range = set(range(1, max(suffixes) + 1))
                    # See what numbers are missing from the collected suffixes by doing a difference with the sets
                    suffix_diff = true_range - suffixes
                    # If there is a difference, the next number will be the minimum in this set
                    if suffix_diff:
                        return title + '_' + str(min(suffix_diff))
                    # If there is no difference, all numbers in the range are found as suffixes with title
                    # so return the next number along from suffixes
                    else:
                        return title + '_' + str(max(suffixes) + 1)
                # Else there were no numerical suffixes so can return title_1
                else:
                    return title + '_1'
            # Else no matches on suffix (title_X) so can return title_1
            else:
                return title + '_1'
        # Else no reports currently have this title so the title can be used as is
        else:
            return title

    async def ml_reg_split(self, techniques):
        list_of_legacy, list_of_techs = [], []
        for k, v in techniques.items():
            try:
                if len(v['example_uses']) > 8:
                    list_of_techs.append(v['name'])
                else:
                    list_of_legacy.append(v['id'])
            except:
                print(v)
        return list_of_legacy, list_of_techs
