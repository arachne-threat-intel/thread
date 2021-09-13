# NOTICE: As required by the Apache License v2.0, this notice is to state this file has been modified by Arachne Digital

import os
import re
import json
import logging

from stix2 import TAXIICollectionSource, Filter
from urllib.parse import quote

try:
    # This is the appropriate import for taxii-client v2.x; this might fail in older taxii-client versions
    from taxii2client.v20 import Collection
except ModuleNotFoundError:
    # The original import statement used in case of error
    from taxii2client import Collection

# Text to set on attack descriptions where this originally was not set
NO_DESC = 'No description provided'
# A name for a temporary table representing the output of SQL_PAR_ATTACK
FULL_ATTACK_INFO = 'full_attack_info'


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

    def __init__(self, dao, web_svc, dir_prefix=''):
        self.dao = dao
        self.web_svc = web_svc
        self.dir_prefix = dir_prefix
        # SQL queries below use a string-pos function which differs across DB engines; obtain the correct one
        str_pos = self.dao.db_func(self.dao.db.FUNC_STR_POS)
        # SQL query to obtain attack records where sub-techniques are returned with their parent-technique info
        # Currently omits 'description' as it is large and is not used in the front-end (this can be added here though)
        self.SQL_PAR_ATTACK = (
            # Use a temporary table 'parent_tids' to return attacks which are sub-techniques (i.e. tid is Txxx.xx)
            # Use the substring method to save in the parent_tid column as the Txxx part of the tid (without the .xx)
            "WITH parent_tids(uid, name, tid, parent_tid) AS "
            "(SELECT uid, name, tid, SUBSTR(tid, 0, %s(tid, '.'))" % str_pos + " "
            # %% in LIKE because % messes up parameters in psycopg (https://github.com/psycopg/psycopg2/issues/827)
            # LIKE '%.%' = '%%.%%' so this does not affect other DB engines
            "FROM attack_uids WHERE tid LIKE '%%.%%') "
            # With parent_tids, select all fields from it and the name of the parent_tid from the attack_uids table
            # Need to use `AS parent_name` to not confuse it with parent_tids.name
            # Using an INNER JOIN because we only care about returning sub-techniques here
            "SELECT parent_tids.*, attack_uids.name AS parent_name FROM "
            "(attack_uids INNER JOIN parent_tids ON attack_uids.tid = parent_tids.parent_tid) "
            # Union the sub-tech query with one for all other techniques (where the tid does not contain a '.')
            # Need to pass in two NULLs so the number of columns for the UNION is the same
            # (and parent_name & parent_tid doesn't exist for these techniques which are not sub-techniques)
            "UNION SELECT uid, name, tid, NULL, NULL FROM attack_uids WHERE tid NOT LIKE '%%.%%'")
        # A prefix SQL statement to use with queries that want the full attack info
        self.SQL_WITH_PAR_ATTACK = \
            'WITH %s(uid, name, tid, parent_tid, parent_name) AS (%s) ' % (FULL_ATTACK_INFO, self.SQL_PAR_ATTACK)

    async def reload_database(self, schema=os.path.join('conf', 'schema.sql')):
        """
        Function to reinitialize the database with the packaged schema
        :param schema: SQL schema file to build database from
        :return: nil
        """
        schema = os.path.join(self.dir_prefix, schema)  # prefix directory path if there is one
        with open(schema) as schema:
            await self.dao.build(schema.read())

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
                                   "description": i.get('description', NO_DESC).replace('<code>', '').replace(
                                       '</code>', '').replace('\n', '').encode('ascii', 'ignore').decode('ascii'),
                                   "similar_words": [i["name"]]}

        for i in attack["relationships"]:
            if i["relationship_type"] == 'uses':
                if 'attack-pattern' in i["target_ref"]:
                    use = i.get('description', NO_DESC)
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
            references[i["id"]] = {"id": i['id'], "name": i["name"], "description": i.get('description', NO_DESC),
                                   "examples": [], "example_uses": [], "similar_words": [i["name"]]}

        attack_data = references
        logging.info("Finished...now creating the database.")

        cur_uids = await self.get_technique_uids()
        for k, v in attack_data.items():
            if k not in cur_uids:
                await self.dao.insert('attack_uids', dict(uid=k, description=defang_text(v.get('description', NO_DESC)),
                                                          tid=v['id'], name=v['name']))
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
        cur_uids = await self.get_technique_uids()
        logging.debug('[#] {} Existing items in the DB'.format(len(cur_uids)))
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
                                                                'description': item.get('description', NO_DESC),
                                                                'example_uses': []}
                        else:
                            logging.critical('[!] Error: multiple MITRE sources: {} {}'.format(item['id'], items))
            # Extract uses for all TIDs
            for item in attack_dict['objects']:
                if item['type'] == 'relationship':
                    if item["relationship_type"] == 'uses':
                        if 'description' in item:
                            normalized_example = item['description'].replace('<code>', '').replace('</code>', '')\
                                .replace('\n', '').encode('ascii', 'ignore').decode('ascii')
                            # Remove att&ck reference (name)[link to site]
                            normalized_example = re.sub('\[.*?\]\(.*?\)', '', normalized_example)
                            if item['target_ref'].startswith('attack-pattern'):
                                if item['target_ref'] in loaded_items:
                                    loaded_items[item['target_ref']]['example_uses'].append(normalized_example)
                                else:
                                    logging.critical('[!] Found target_ref not in loaded data: {}'.format(item['target_ref']))
        logging.debug("[#] {} Techniques found in input file".format(len(loaded_items)))
        # Deduplicate input data from existing items in the DB
        to_add = {x: y for x, y in loaded_items.items() if x not in cur_uids}
        logging.debug('[#] {} Techniques found that are not in the existing database'.format(len(to_add)))
        for k, v in to_add.items():
            await self.dao.insert('attack_uids', dict(uid=k, description=defang_text(v.get('description', NO_DESC)),
                                                      tid=v['id'], name=v['name']))
            if 'example_uses' in v:
                [await self.dao.insert_generate_uid('true_positives', dict(attack_uid=k, true_positive=defang_text(x)))
                 for x in v['example_uses']]

    async def status_grouper(self, status, criteria=None):
        # The search based on the given status
        search = dict(current_status=status)
        # If extra search criteria has been passed, update the current search dictionary
        if type(criteria) is dict:
            search.update(criteria)
        # Execute the search on the reports table
        reports = await self.dao.get('reports', search)
        for report in reports:
            del report['uid']  # Prevent ID reaching request-response
            title_quoted = quote(report['title'], safe='')
            edit_link = self.web_svc.get_route(self.web_svc.EDIT_KEY, param=title_quoted)
            report.update(dict(link=edit_link, title_quoted=title_quoted))
        return reports

    async def get_report_sentences(self, report_id):
        return await self.dao.get('report_sentences', dict(report_uid=report_id))

    async def get_report_sentences_with_attacks(self, report_id=''):
        """Function to retrieve all report sentences and any attacks they may have given a report ID."""
        select_join_query = (
            # Using the temporary table with parent-technique info
            self.SQL_WITH_PAR_ATTACK +
            # The relevant report-sentence fields we want
            "SELECT report_sentences.*, report_sentence_hits.attack_tid, report_sentence_hits.attack_technique_name, "
            # We want to add any sub-technique's parent-technique name
            "report_sentence_hits.active_hit, " + FULL_ATTACK_INFO + ".parent_name AS attack_parent_name "
            # The first join for the report data; LEFT OUTER JOIN because we want all report sentences
            "FROM ((report_sentences LEFT OUTER JOIN report_sentence_hits "
            "ON report_sentences.uid = report_sentence_hits.sentence_id) "
            # A second join for the full attack table; still using a LEFT JOIN
            "LEFT JOIN " + FULL_ATTACK_INFO + " ON " + FULL_ATTACK_INFO + ".uid = report_sentence_hits.attack_uid)"
            # Finish with the WHERE clause stating which report this is for
            "WHERE report_sentences.report_uid = %s" % self.dao.db_qparam)
        return await self.dao.raw_select(select_join_query, parameters=tuple([report_id]))

    async def get_techniques(self, get_parent_info=False):
        # If we are not getting the parent-attack info (for sub-techniques), then return all results as normal
        if not get_parent_info:
            return await self.dao.get('attack_uids')
        # Else run the SQL query which returns the parent info
        return await self.dao.raw_select(self.SQL_PAR_ATTACK)

    async def get_technique_uids(self):
        """A function to obtain the list of attack IDs from the db."""
        return await self.dao.get_column_as_list(table='attack_uids', column='uid')

    async def get_confirmed_attacks_for_sentence(self, sentence_id=''):
        """Function to retrieve confirmed-attack data for a sentence."""
        select_join_query = (
            # Select all columns from the full attack info table
            self.SQL_WITH_PAR_ATTACK + "SELECT " + FULL_ATTACK_INFO + ".* "
            # Use an INNER JOIN on full_attack_info and report_sentence_hits (to get the intersection of attacks)
            "FROM (" + FULL_ATTACK_INFO + " INNER JOIN report_sentence_hits ON " + FULL_ATTACK_INFO +
            ".uid = report_sentence_hits.attack_uid) "
            # Finish with the WHERE clause stating which sentence we are searching for and that the attack is confirmed
            "WHERE report_sentence_hits.sentence_id = %s" % self.dao.db_qparam + " "
            "AND report_sentence_hits.confirmed = %s" % self.dao.db_true_val)
        # Run the above query and return its results
        return await self.dao.raw_select(select_join_query, parameters=tuple([sentence_id]))

    async def get_unconfirmed_attack_count(self, report_id=''):
        """Function to retrieve the number of unconfirmed attacks for a report."""
        # Retrieve all unconfirmed attacks
        all_unconfirmed = await self.dao.get('report_sentence_hits', dict(report_uid=report_id,
                                                                          confirmed=self.dao.db_false_val))
        # Ignore entries in the database where the model was incorrect (i.e. is unconfirmed because it was rejected and
        # we are storing in report_sentence_hits that initial_model_match=1 so confirmed=0): these are false positives
        select_join_query = (
            "SELECT * FROM (report_sentence_hits INNER JOIN false_positives "
            "ON report_sentence_hits.attack_uid = false_positives.attack_uid "
            "AND report_sentence_hits.sentence_id = false_positives.sentence_id) "
            "WHERE report_sentence_hits.report_uid = %s" % self.dao.db_qparam + " "
            "AND report_sentence_hits.confirmed = %s" % self.dao.db_false_val)
        ignore = await self.dao.raw_select(select_join_query, parameters=tuple([report_id]))
        # Ideally would use an SQL MINUS query but this caused errors
        return len(all_unconfirmed) - len(ignore)

    async def get_confirmed_techniques_for_nav_export(self, report_id):
        # The SQL select join query to retrieve the confirmed techniques for the nav export
        select_join_query = (
            "SELECT report_sentences.uid, report_sentence_hits.attack_uid, report_sentence_hits.report_uid, "
            "report_sentence_hits.attack_tid, report_sentences.text, report_sentence_hits.initial_model_match "
            "FROM (report_sentences INNER JOIN report_sentence_hits "
            "ON report_sentences.uid = report_sentence_hits.sentence_id) "
            "WHERE report_sentence_hits.report_uid = %s" % self.dao.db_qparam + " "
            "AND report_sentence_hits.confirmed = %s" % self.dao.db_true_val)
        # Get the confirmed hits as the above SQL query
        hits = await self.dao.raw_select(select_join_query, parameters=tuple([report_id]))
        techniques = []
        for hit in hits:
            # For each confirmed technique returned,
            # create a technique object and add it to the list of techniques.
            technique = {'model_score': hit['initial_model_match'], 'techniqueID': hit['attack_tid'],
                         'comment': await self.web_svc.remove_html_markup_and_found(hit['text'])}
            techniques.append(technique)
        # Return the list of confirmed techniques
        return techniques

    async def get_active_sentence_hits(self, sentence_id=''):
        """Function to retrieve active sentence hits (and ignoring historic ones, e.g. a model's initial prediction)."""
        select_join_query = (
            # Using the temporary table with parent-technique info
            self.SQL_WITH_PAR_ATTACK +
            # The relevant fields we want from report_sentence_hits
            "SELECT report_sentence_hits.sentence_id, report_sentence_hits.attack_uid, "
            "report_sentence_hits.attack_tid, report_sentence_hits.attack_technique_name, "
            # We want to add any sub-technique's parent-technique name
            + FULL_ATTACK_INFO + ".parent_name AS attack_parent_name "
            # As we are querying two tables, state the FROM clause is an INNER JOIN on the two
            "FROM (" + FULL_ATTACK_INFO + " INNER JOIN report_sentence_hits ON " + FULL_ATTACK_INFO +
            ".uid = report_sentence_hits.attack_uid) "
            # Finish with the WHERE clause stating which sentence we are searching for and that the hit is active
            "WHERE report_sentence_hits.sentence_id = %s" % self.dao.db_qparam + " "
            "AND report_sentence_hits.active_hit = %s" % self.dao.db_true_val)
        # Run the above query and return its results
        return await self.dao.raw_select(select_join_query, parameters=tuple([sentence_id]))

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
            query = 'SELECT * FROM reports WHERE title LIKE %s ESCAPE \'\\\';' % self.dao.db_qparam
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
