# NOTICE: As required by the Apache License v2.0, this notice is to state this file has been modified by Arachne Digital
# This file has been moved into a different directory
# To see its full history, please use `git log --follow <filename>` to view previous commits and additional contributors

import os
import re
import requests
import json
import logging

from contextlib import suppress
from copy import deepcopy
from datetime import datetime
from stix2 import Filter, MemoryStore
from urllib.parse import quote

# Text to set on attack descriptions where this originally was not set
NO_DESC = 'No description provided'
# A name for a temporary table representing the output of SQL_PAR_ATTACK
FULL_ATTACK_INFO = 'full_attack_info'


def fetch_attack_data():
    """Function to fetch the latest Att%ck data."""
    url = 'https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/' \
          'enterprise-attack.json'
    return requests.get(url).json()


def attack_data_reject(attack_data):
    """Function to check given a single attack data, whether it should be skipped."""
    return attack_data.get('x_mitre_deprecated') or attack_data.get('revoked')


def attack_data_get_tid(attack_data):
    """Function that, given a single attack data, retrieves its TID."""
    # Obtain the ID of the attack in case we need to use this instead of a TID
    data_id = attack_data['id']
    # We cannot find the TID if there are no external references
    external_refs = attack_data.get('external_references')
    if not external_refs:
        return data_id
    # For each external reference, check the URL is the Mitre Att&ck page; if it is, retrieve the TID
    # (Can't check by source_name as this can be 'mitre-attack', 'mitre-mobile-attack', or possibly other variations)
    tid = None
    for ref in external_refs:
        source = ref.get('url', '')
        if not (source.startswith('https://attack.mitre.org/') or source.startswith('http://attack.mitre.org/')):
            continue
        tid = ref.get('external_id')
        break
    return tid or data_id


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
        self.region_dict = {}
        self.country_dict = {}
        self.country_region_dict = {}
        # SQL queries below use a string-pos function which differs across DB engines; obtain the correct one
        str_pos = self.dao.db_func(self.dao.db.FUNC_STR_POS)
        # SQL query to obtain attack records where sub-techniques are returned with their parent-technique info
        sql_par_attack_base = (
            # Use a temporary table 'parent_tids' to return attacks which are sub-techniques (i.e. tid is Txxx.xx)
            # Use the substring method to save in the parent_tid column as the Txxx part of the tid (without the .xx)
            "WITH parent_tids(uid, name, tid, inactive, parent_tid) AS "
            "(SELECT uid, name, tid, inactive, SUBSTR(tid, 0, %s(tid, '.'))" % str_pos + " "
            # %% in LIKE because % messes up parameters in psycopg (https://github.com/psycopg/psycopg2/issues/827)
            # LIKE '%.%' = '%%.%%' so this does not affect other DB engines
            "FROM attack_uids WHERE tid LIKE '%%.%%'{inactive_AND}) "
            # With parent_tids, select all fields from it and the name of the parent_tid from the attack_uids table
            # Need to use `AS parent_name` to not confuse it with parent_tids.name
            # Using an INNER JOIN because we only care about returning sub-techniques here
            "SELECT parent_tids.*, attack_uids.name AS parent_name FROM "
            "(attack_uids INNER JOIN parent_tids ON attack_uids.tid = parent_tids.parent_tid){inactive_WHERE} "
            # Union the sub-tech query with one for all other techniques (where the tid does not contain a '.')
            # Need to pass in two NULLs so the number of columns for the UNION is the same
            # (and parent_name & parent_tid doesn't exist for these techniques which are not sub-techniques)
            "UNION SELECT uid, name, tid, inactive, NULL, NULL FROM attack_uids WHERE tid NOT LIKE '%%.%%'{inactive_AND}")
        # Use this query to omit any 'inactive' attacks
        exc_inactive = 'inactive = %s' % self.dao.db_false_val
        with_par_attack = 'WITH %s(uid, name, tid, inactive, parent_tid, parent_name) AS (%s) ' % (FULL_ATTACK_INFO, '%s')
        self.SQL_PAR_ATTACK = sql_par_attack_base.format(inactive_AND=' AND ' + exc_inactive,
                                                         inactive_WHERE=' WHERE attack_uids.' + exc_inactive)
        # A prefix SQL statement to use with queries that want the full attack info
        self.SQL_WITH_PAR_ATTACK = with_par_attack % self.SQL_PAR_ATTACK
        # A version of the above queries that includes inactive attacks
        self.SQL_PAR_ATTACK_INC_INACTIVE = sql_par_attack_base.format(inactive_AND='', inactive_WHERE='')
        self.SQL_WITH_PAR_ATTACK_INC_INACTIVE = with_par_attack % self.SQL_PAR_ATTACK_INC_INACTIVE

    async def reload_database(self, schema_file=os.path.join('threadcomponents', 'conf', 'schema.sql')):
        """
        Function to reinitialize the database with the packaged schema
        :param schema_file: SQL schema file to build database from
        :return: nil
        """
        # Begin by obtaining the text from the schema file
        schema_file = os.path.join(self.dir_prefix, schema_file)  # prefix directory path if there is one
        with open(schema_file) as schema_opened:
            schema = schema_opened.read()
        # Given the schema, generate a new schema for tables that need to have a copied structure
        copied_tables_schema = self.dao.generate_copied_tables(schema=schema)
        # Proceed to build both schemas
        await self.dao.build(schema)
        await self.dao.build(copied_tables_schema, is_partial=True)

    async def fetch_and_update_attack_data(self):
        """
        Function to retrieve ATT&CK data and insert it into the DB.
        Further reading on approach: https://github.com/arachne-threat-intel/thread/pull/27#issuecomment-1047456689
        """
        logging.info('Downloading ATT&CK data from GitHub repo `mitre-attack/attack-stix-data`...')
        attack = {}
        stix_json = fetch_attack_data()
        ms = MemoryStore(stix_data=stix_json['objects'])
        filter_objs = {'techniques': Filter('type', '=', 'attack-pattern'),
                       'groups': Filter('type', '=', 'intrusion-set'), 'malware': Filter('type', '=', 'malware'),
                       'tools': Filter('type', '=', 'tool'), 'relationships': Filter('type', '=', 'relationship')}
        for key in filter_objs:
            # Could pass [filter_objs[key], Filter('x_mitre_deprecated', '!=', True), Filter('revoked', '!=', True)]
            # But numbers are not adding up when ('=', False) are used
            attack[key] = ms.query(filter_objs[key])
        references = {}

        # add all of the patterns and dictionary keys/values for each technique and software
        for i in attack['techniques']:
            if attack_data_reject(i):
                continue
            references[i['id']] = {'name': i['name'], 'tid': attack_data_get_tid(i), 'example_uses': [],
                                   'description': i.get('description', NO_DESC).replace('<code>', '').replace(
                                       '</code>', '').replace('\n', '').encode('ascii', 'ignore').decode('ascii'),
                                   'similar_words': [i['name']]}

        for i in attack['relationships']:
            if attack_data_reject(i):
                continue
            if i['relationship_type'] == 'uses':
                if ('attack-pattern' in i['target_ref']) and (i['target_ref'] in references):
                    use = i.get('description', NO_DESC)
                    # remove unnecessary strings, fix unicode errors
                    use = use.replace('<code>', '').replace('</code>', '').replace('"', '').replace(',', '').replace(
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
                    references[i['target_ref']]['example_uses'].append(use)

        for i in attack['malware']:
            # TODO check if we should be skipping those without a description?
            # some software do not have description, example: darkmoon https://attack.mitre.org/software/S0209
            if ('description' not in i) or attack_data_reject(i):
                continue
            else:
                references[i['id']] = {'tid': attack_data_get_tid(i), 'name': i['name'],
                                       'description': i.get('description', NO_DESC),
                                       'examples': [], 'example_uses': [], 'similar_words': [i['name']]}
        for i in attack['tools']:
            if attack_data_reject(i):
                continue
            references[i['id']] = {'tid': attack_data_get_tid(i), 'name': i['name'],
                                   'description': i.get('description', NO_DESC),
                                   'examples': [], 'example_uses': [], 'similar_words': [i['name']]}

        attack_data = references
        logging.info('Finished...now creating the database.')

        cur_attacks = (await self.dao.get_dict_value_as_key('uid', table='attack_uids', columns=['name', 'inactive'])) or dict()
        cur_uids = set(cur_attacks.keys())
        retrieved_uids = set(attack_data.keys())
        added_attacks = retrieved_uids - cur_uids
        name_changes = []
        for k, v in attack_data.items():
            # If this loop takes long, the below logging-statement will help track progress
            # logging.info('Processing attack %s of %s.' % (list(attack_data.keys()).index(k) + 1, len(attack_data)))
            if k not in cur_uids:
                await self.dao.insert('attack_uids', dict(uid=k, tid=v['tid'], name=v['name']))
                if 'regex_patterns' in v:
                    [await self.dao.insert_generate_uid('regex_patterns',
                                                        dict(attack_uid=k, regex_pattern=defang_text(x)))
                     for x in v['regex_patterns']]
                if 'similar_words' in v:
                    [await self.dao.insert_generate_uid('similar_words',
                                                        dict(attack_uid=k, similar_word=defang_text(x)))
                     for x in v['similar_words']]
                if 'false_negatives' in v:
                    [await self.dao.insert_generate_uid(
                        'false_negatives',
                        dict(attack_uid=k, false_negative=self.dao.truncate_str(defang_text(x), 800)))
                     for x in v['false_negatives']]
                if 'false_positives' in v:
                    [await self.dao.insert_generate_uid(
                        'false_positives',
                        dict(attack_uid=k, false_positive=self.dao.truncate_str(defang_text(x), 800)))
                     for x in v['false_positives']]
                if 'true_positives' in v:
                    [await self.dao.insert_generate_uid(
                        'true_positives',
                        dict(attack_uid=k, true_positive=self.dao.truncate_str(defang_text(x), 800)))
                     for x in v['true_positives']]
                if 'example_uses' in v:
                    [await self.dao.insert_generate_uid(
                        'true_positives',
                        dict(attack_uid=k, true_positive=self.dao.truncate_str(defang_text(x), 800)))
                     for x in v['example_uses']]
            else:
                # If the attack is already in the DB, check the name hasn't changed; update if so
                retrieved_name = (attack_data.get(k, dict())).get('name')
                current_attack_data = cur_attacks.get(k, dict())
                current_name = current_attack_data.get('name')
                if retrieved_name and (retrieved_name != current_name):
                    await self.dao.update('attack_uids', where=dict(uid=k), data=dict(name=retrieved_name))
                    name_changes.append((k, retrieved_name, current_name))
                    # Update the similar-words table if we're updating the attack-entry
                    for name in [retrieved_name, current_name]:
                        if name:  # proceed if there is a value
                            # Check an attack doesn't already have a similar-word with this name
                            db_criteria = dict(attack_uid=k, similar_word=name)
                            stored = await self.dao.get('similar_words', equal=db_criteria)
                            # If not, update the attack's similar-words to include this name
                            if not stored:
                                await self.dao.insert_generate_uid('similar_words', db_criteria)
                # Confirm this attack is considered active
                if current_attack_data.get('inactive'):
                    await self.dao.update('attack_uids', where=dict(uid=k), data=dict(inactive=self.dao.db_false_val))
        # Inactive attack IDs have been calculated by using what is in the database currently
        # Update the database entries to be inactive if not already flagged as such
        already_inactive = await self.dao.raw_select(
            ('SELECT uid FROM attack_uids WHERE inactive = %s' % self.dao.db_true_val), single_col=True)
        inactive_attacks = (cur_uids - retrieved_uids) - set(already_inactive)
        for inactive_id in inactive_attacks:
            await self.dao.update('attack_uids', where=dict(uid=inactive_id), data=dict(inactive=self.dao.db_true_val))
        logging.info('[!] DB Item Count: {}'.format(len(await self.dao.get('attack_uids'))))
        return added_attacks, inactive_attacks, name_changes

    async def insert_attack_json_data(self, buildfile):
        """
        Function to read in the enterprise attack json file and insert data into the database
        :param buildfile: Enterprise attack json file to build from
        :return: nil
        """
        cur_uids = await self.dao.get_column_as_list(table='attack_uids', column='uid')
        logging.info('[#] {} Existing items in the DB'.format(len(cur_uids)))
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
        logging.info("[#] {} Techniques found in input file".format(len(loaded_items)))
        # Deduplicate input data from existing items in the DB
        to_add = {x: y for x, y in loaded_items.items() if x not in cur_uids}
        logging.info('[#] {} Techniques found that are not in the existing database'.format(len(to_add)))
        for k, v in to_add.items():
            await self.dao.insert('attack_uids', dict(uid=k, tid=v['id'], name=v['name']))
            if 'example_uses' in v:
                [await self.dao.insert_generate_uid(
                    'true_positives', dict(attack_uid=k, true_positive=self.dao.truncate_str(defang_text(x), 800)))
                 for x in v['example_uses']]

    async def set_regions_data(self, buildfile=os.path.join('threadcomponents', 'conf', 'country-regions.json')):
        """Function to read in the regions json file."""
        buildfile = os.path.join(self.dir_prefix, buildfile)
        with open(buildfile, 'r') as regions_file:
            loaded_regions = json.load(regions_file)

        self.region_dict = {}
        for region in loaded_regions:
            self.region_dict[region['id']] = region['name']

    async def set_countries_data(self, buildfile=os.path.join('threadcomponents', 'conf', 'countries-iso2.json')):
        """Function to read in the countries json file."""
        buildfile = os.path.join(self.dir_prefix, buildfile)  # prefix directory path if there is one
        # Load the JSON file and set the country dictionary with the ISO2 value mapped to the country name
        with open(buildfile, 'r') as infile:
            loaded_countries = json.load(infile)
        self.country_dict = {}
        self.country_region_dict = {}
        for entry in loaded_countries:
            self.country_dict[entry['alpha-2']] = entry['name']
            self.country_region_dict[entry['alpha-2']] = entry['region-id']

    async def insert_category_json_data(self, buildfile=os.path.join('threadcomponents', 'conf', 'categories',
                                                                     'industry.json')):
        """Function to read in the categories json file and insert data into the database."""
        buildfile = os.path.join(self.dir_prefix, buildfile)  # prefix directory path if there is one
        # The current categories saved in the db
        cur_categories = await self.dao.get_column_as_list(table='categories', column='keyname')
        # Load the JSON file
        with open(buildfile, 'r') as infile:
            categories_dict = self.web_svc.categories_dict = json.load(infile)
        # Dictionaries to hold the display names and parent-category names for categories
        parent_cat_names, display_names = {}, {}
        # Loop through category list once to map all sub-categories to their parent categories
        for keyname, entry in categories_dict.items():
            sub_categories = entry.get('sub_categories', [])
            # Even if a category is in our db, we need to check if any of its sub-categories are new
            if (keyname in cur_categories) and not sub_categories:
                continue
            for sub_cat in sub_categories:
                if sub_cat not in cur_categories:
                    parent_cat_names[sub_cat] = keyname
        # Loop through a second time to construct the display name of categories
        for keyname, entry in categories_dict.items():
            if keyname in cur_categories:
                continue
            # While we have a parent category; traversed less-than 3 categories; and not repeated parent categories...
            parent_cat_name = parent_cat_names.get(keyname)
            parent_history = {keyname}
            display_name = entry['name']
            count = 0
            while (parent_cat_name is not None) and (count < 3) and (parent_cat_name not in parent_history):
                count += 1
                parent_history.add(parent_cat_name)
                parent_cat_entry = categories_dict.get(parent_cat_name)
                if not parent_cat_entry:
                    break
                # ...make the parent category name prefix the current display name
                display_name = parent_cat_entry['name'] + ' - ' + display_name
                parent_cat_name = parent_cat_names.get(parent_cat_name)
            display_names[keyname] = display_name
        # Finally, insert the categories into the database
        for keyname, entry in categories_dict.items():
            if keyname in cur_categories:
                continue
            await self.dao.insert_generate_uid('categories', dict(keyname=keyname, name=entry['name'],
                                                                  display_name=display_names[keyname]))

    async def insert_keyword_json_data(self, buildfile=os.path.join('rosettaStone', 'cta_names_mappings.json')):
        """Function to read in the keywords json file and insert data into the database."""
        buildfile = os.path.join(self.dir_prefix, buildfile)  # prefix directory path if there is one
        # The current keywords saved in the db
        cur_keywords = await self.dao.get_column_as_list(table='keywords', column='name')
        # Load the JSON file
        with open(buildfile, 'r') as infile:
            keywords_dict = json.load(infile)
        # Obtain all the unique keywords and aliases into a set
        to_add = set()
        for keyword, entry in keywords_dict.items():
            to_add.add(keyword)
            for list_key in ['full_aliases', 'partial_aliases', 'subgroups', 'campaigns']:
                to_add.update(entry.get(list_key, []))
        # Check which ones are not in the database and add them if so
        to_add = to_add - set(cur_keywords)
        for adding_keyword in to_add:
            await self.dao.insert_generate_uid('keywords', dict(name=adding_keyword))
        return to_add

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
            # Format dates if applicable
            expires_on = report.get('expires_on', '')
            if isinstance(expires_on, datetime):
                # Replace the expiry date with a formatted string
                is_expired = expires_on < datetime.now(tz=expires_on.tzinfo)
                report.update(dict(expires_on=expires_on.strftime('%Y-%m-%d %H:%M %Z'), is_expired=is_expired))
            report.update(dict(link=edit_link, title_quoted=title_quoted))
        return reports

    async def get_all_categories(self):
        """Function to retrieve all the possible categories for a report."""
        query = 'SELECT keyname, display_name FROM categories'
        return await self.dao.raw_select(query)

    async def get_report_category_keynames(self, report_id):
        """Function to retrieve the category keynames for a report given a report ID."""
        query = 'SELECT category_keyname FROM report_categories WHERE report_uid = %s' % self.dao.db_qparam
        return await self.dao.raw_select(query, parameters=tuple([report_id]), single_col=True)

    async def get_report_categories_for_display(self, report_id, include_keynames=False):
        """Function to retrieve the categories for a report given a report ID."""
        # We are definitely returning the display name; include the keyname if applicable
        columns = ['display_name']
        if include_keynames:
            columns.append('keyname')
        query = "SELECT " + (', '.join(columns)) + " FROM (categories INNER JOIN report_categories ON " \
                "categories.keyname = report_categories.category_keyname)"
        query += ' WHERE report_uid = %s' % self.dao.db_qparam
        # If we are including keynames, return a dictionary where each entry is searchable by the keyname
        if include_keynames:
            return await self.dao.get_dict_value_as_key('keyname', sql=query, sql_params=tuple([report_id]))
        # Else return the list of display names for this report
        return await self.dao.raw_select(query, parameters=tuple([report_id]), single_col=len(columns) == 1)

    async def get_report_aggressors_victims(self, report_id, include_display=False):
        """Function to retrieve the aggressors and victims for a report given a report ID."""
        # Obtain all groups,  and countries for this report
        query = "SELECT keyword, NULL AS region, NULL AS country, association_type " \
                "FROM report_keywords " \
                "WHERE report_uid = {sel} " \
                "UNION " \
                "SELECT NULL AS keyword, region, NULL AS country, association_type " \
                "FROM report_regions " \
                "WHERE report_uid = {sel} " \
                "UNION " \
                "SELECT NULL AS keyword, NULL AS region, country, association_type " \
                "FROM report_countries " \
                "WHERE report_uid = {sel}".format(sel=self.dao.db_qparam)
        db_results = await self.dao.raw_select(query, parameters=tuple([report_id, report_id, report_id]))
        # Check if this report is flagged at having all victims
        query = 'SELECT association_type, association_with FROM report_all_assoc WHERE report_uid = %s' % self.dao.db_qparam
        all_assoc = await self.dao.raw_select(query, parameters=tuple([report_id]))
        # Set up the dictionary to return the results split by aggressor and victim
        r_template = dict(groups=[], categories_all=False, region_ids=[], regions_all=False, country_codes=[], countries_all=False)
        if include_display:
            r_template.update(dict(countries=[]))
        results = dict(aggressors=deepcopy(r_template), victims=deepcopy(r_template))
        # Flag select-all in results: only doing this for victims
        for results_key, db_assoc_type in [('victims', 'victim')]:
            results[results_key]['categories_all'] = any((r.get('association_with') == 'category') and
                                                         (r.get('association_type') == db_assoc_type) for r in all_assoc)
            results[results_key]['countries_all'] = any((r.get('association_with') == 'country') and
                                                        (r.get('association_type') == db_assoc_type) for r in all_assoc)
        # Go through the retrieved database results and place result in appropriate dictionary/list
        for entry in db_results:
            # First determine if this result is for an aggressor or victim
            assoc_type = entry.get('association_type')
            if assoc_type == 'aggressor':
                updating = results['aggressors']
            elif assoc_type == 'victim':
                updating = results['victims']
            else:
                logging.error('INVALID report association `%s` saved in db, uid `%s`' % (assoc_type, entry.get('uid')))
                continue
            # Then determine if this result is for a group, region or country: append value if not already flagged as select-all
            assoc_value_g, assoc_value_r, assoc_value_c = entry.get('keyword'), entry.get('region'), entry.get('country')
            if not (assoc_value_g or assoc_value_r or assoc_value_c):
                logging.error('GROUP, REGION or COUNTRY missing in db entry uid `%s`' % entry.get('uid'))
                continue
            if assoc_value_g:
                updating['groups'].append(assoc_value_g)
            elif assoc_value_r and not updating['regions_all']:
                updating['region_ids'].append(str(assoc_value_r))
                if include_display:
                    updating['regions'].append(self.region_dict.get(assoc_value_r))
            elif assoc_value_c and not updating['countries_all']:
                updating['country_codes'].append(assoc_value_c)
                if include_display:
                    updating['countries'].append(self.country_dict.get(assoc_value_c))
        return results

    async def get_report_sentences(self, report_id):
        """Function to retrieve all report sentences for a given report ID."""
        return await self.dao.get('report_sentences', equal=dict(report_uid=report_id), order_by_asc=dict(sen_index=1))

    async def get_report_sentence_indicators_of_compromise(self, report_id):
        """Function to retrieve all indicators of compromise for a given report ID."""
        return await self.dao.get('report_sentence_indicators_of_compromise', equal=dict(report_id=report_id))

    async def get_report_sentences_with_attacks(self, report_id=''):
        """Function to retrieve all report sentences and any attacks they may have given a report ID."""
        # Ensure date fields are converted into strings
        start_date = self.dao.db.sql_date_field_to_str('report_sentence_hits.start_date', field_name_as='tech_start_date')
        end_date = self.dao.db.sql_date_field_to_str('report_sentence_hits.end_date', field_name_as='tech_end_date')
        select_join_query = (
            # Using the temporary table with parent-technique info
            self.SQL_WITH_PAR_ATTACK +
            # The relevant report-sentence fields we want
            "SELECT report_sentences.*, report_sentence_hits.attack_tid, report_sentence_hits.attack_technique_name, "
            # We want to add any sub-technique's parent-technique name
            "report_sentence_hits.active_hit, " + FULL_ATTACK_INFO + ".parent_name AS attack_parent_name, "
            # LEFT (not INNER) JOINS with FULL_ATTACK_INFO may have 'inactive' data; return 'inactive' from attack_uids
            "attack_uids.inactive AS inactive_attack, " + start_date + ", " + end_date + " "
            # The first join for the report data; LEFT OUTER JOIN because we want all report sentences
            "FROM (((report_sentences LEFT OUTER JOIN report_sentence_hits "
            "ON report_sentences.uid = report_sentence_hits.sentence_id) "
            # A second join for the full attack table; still using a LEFT JOIN
            "LEFT JOIN " + FULL_ATTACK_INFO + " ON " + FULL_ATTACK_INFO + ".uid = report_sentence_hits.attack_uid) "
            # FULL_ATTACK_INFO omits 'inactive' flag; join so we have this info
            "LEFT JOIN attack_uids ON report_sentence_hits.attack_uid = attack_uids.uid) "
            # Finish with the WHERE clause stating which report this is for
            "WHERE report_sentences.report_uid = %s" % self.dao.db_qparam + " "
            # Need to order by for JOIN query (otherwise sentences can be out of order if attacks are updated)
            "ORDER BY report_sentences.sen_index")
        return await self.dao.raw_select(select_join_query, parameters=tuple([report_id]))

    async def get_techniques(self, get_parent_info=False):
        # If we are not getting the parent-attack info (for sub-techniques), then return all results as normal
        if not get_parent_info:
            return await self.dao.get('attack_uids', equal=dict(inactive=self.dao.db_false_val))
        # Else run the SQL query which returns the parent info
        return await self.dao.raw_select(self.SQL_PAR_ATTACK)

    async def get_report_id_from_sentence_id(self, sentence_id=None):
        """Function to retrieve the report ID from a sentence ID."""
        if not sentence_id:
            return None
        # Determine if sentence or image
        sentence_dict = await self.dao.get('report_sentences', dict(uid=sentence_id))
        img_dict = await self.dao.get('original_html', dict(uid=sentence_id))
        # Get the report ID from either
        report_id = None
        with suppress(KeyError, IndexError):
            report_id = sentence_dict[0]['report_uid']
        with suppress(KeyError, IndexError):
            report_id = img_dict[0]['report_uid']
        return report_id

    async def get_confirmed_attacks_for_sentence(self, sentence_id=''):
        """Function to retrieve confirmed-attack data for a sentence."""
        # Ensure any date fields are converted into strings
        start_date = self.dao.db.sql_date_field_to_str('report_sentence_hits.start_date')
        end_date = self.dao.db.sql_date_field_to_str('report_sentence_hits.end_date')
        select_join_query = (
            # Select all columns from the full attack info table
            self.SQL_WITH_PAR_ATTACK_INC_INACTIVE + "SELECT " + FULL_ATTACK_INFO + ".*, "
            # Include row ID for use when updating dates of attack
            "report_sentence_hits.uid AS mapping_id, " + start_date + ", " + end_date + " "
            # Use an INNER JOIN on full_attack_info and report_sentence_hits (to get the intersection of attacks)
            "FROM (" + FULL_ATTACK_INFO + " INNER JOIN report_sentence_hits ON " + FULL_ATTACK_INFO +
            ".uid = report_sentence_hits.attack_uid) "
            # Finish with the WHERE clause stating which sentence we are searching for and that the attack is confirmed
            "WHERE report_sentence_hits.sentence_id = %s" % self.dao.db_qparam + " "
            "AND report_sentence_hits.confirmed = %s" % self.dao.db_true_val)
        # Run the above query and return its results
        return await self.dao.raw_select(select_join_query, parameters=tuple([sentence_id]))

    async def get_unconfirmed_undated_attack_count(self, report_id='', return_detail=False):
        """Function to retrieve the number of unconfirmed attacks without a start-date for a report."""
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
            "AND (report_sentence_hits.confirmed = %s" % self.dao.db_false_val + " "
            "OR report_sentence_hits.start_date IS NULL)")
        ignore = await self.dao.raw_select(select_join_query, parameters=tuple([report_id]))
        # Ideally would use an SQL MINUS query but this caused errors
        # Return the count if we are not returning the detail
        if not return_detail:
            return len(all_unconfirmed) - len(ignore)
        # If returning details, set up a dictionary and convert the dictionaries in ignore to tuples (for matching)
        unconfirmed_by_sentence = dict()
        tuple_ig = [(x.get('attack_uid', 'error'), x.get('sentence_id', 'error'), x.get('attack_tid', 'error'))
                    for x in ignore]
        # Loop through each unconfirmed hit; check it's not in ignore; add to final dictionary (group by sentence)
        for u in all_unconfirmed:
            sen_id = u.get('sentence_id', 'error')
            a_id, a_tid = u.get('attack_uid', 'error'), u.get('attack_tid', 'error')
            if (a_id, sen_id, a_tid) in tuple_ig:
                continue
            current_list = unconfirmed_by_sentence.get(sen_id, [])
            attack_info = dict(attack_uid=a_id, attack_tid=a_tid)
            if attack_info not in current_list:
                current_list.append(attack_info)
                unconfirmed_by_sentence[sen_id] = current_list
        return unconfirmed_by_sentence

    async def get_confirmed_techniques_for_nav_export(self, report_id):
        # Ensure date fields are converted into strings
        start_date = self.dao.db.sql_date_field_to_str('report_sentence_hits.start_date', field_name_as='tech_start_date')
        end_date = self.dao.db.sql_date_field_to_str('report_sentence_hits.end_date', field_name_as='tech_end_date')
        # The SQL select join query to retrieve the confirmed techniques for the nav export
        select_join_query = (
            "SELECT report_sentences.uid, report_sentence_hits.attack_uid, report_sentence_hits.report_uid, "
            "report_sentence_hits.attack_tid, report_sentences.text, report_sentence_hits.initial_model_match,"
            " " + start_date + ", " + end_date + " "
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
                         'comment': await self.web_svc.remove_html_markup_and_found(hit['text']),
                         'tech_start_date': hit.get('tech_start_date'), 'tech_end_date': hit.get('tech_end_date')}
            techniques.append(technique)
        # Return the list of confirmed techniques
        return techniques

    async def get_active_sentence_hits(self, sentence_id=''):
        """Function to retrieve active sentence hits (and ignoring historic ones, e.g. a model's initial prediction)."""
        select_join_query = (
            # Using the temporary table with parent-technique info
            self.SQL_WITH_PAR_ATTACK_INC_INACTIVE +
            # The relevant fields we want from report_sentence_hits
            "SELECT report_sentence_hits.sentence_id, report_sentence_hits.attack_uid, "
            "report_sentence_hits.attack_tid, report_sentence_hits.attack_technique_name, "
            # We want to add any sub-technique's parent-technique name
            + FULL_ATTACK_INFO + ".parent_name AS attack_parent_name, " + FULL_ATTACK_INFO + ".inactive "
            # As we are querying two tables, state the FROM clause is an INNER JOIN on the two
            "FROM (" + FULL_ATTACK_INFO + " INNER JOIN report_sentence_hits ON " + FULL_ATTACK_INFO +
            ".uid = report_sentence_hits.attack_uid) "
            # Finish with the WHERE clause stating which sentence we are searching for and that the hit is active
            "WHERE report_sentence_hits.sentence_id = %s" % self.dao.db_qparam + " "
            "AND report_sentence_hits.active_hit = %s" % self.dao.db_true_val)
        # Run the above query and return its results
        return await self.dao.raw_select(select_join_query, parameters=tuple([sentence_id]))
    
    async def get_report_unique_techniques_count(self, report_id) -> int:
        """Function to return the amount of unique techniques found in a report."""
        count_query = (
            "SELECT COUNT(DISTINCT(attack_uid)) AS count " +
            "FROM report_sentence_hits " +
            "WHERE report_uid = %s" % self.dao.db_qparam
        )
        count_query_result = await self.dao.raw_select(count_query, parameters=tuple([report_id]))
        return count_query_result[0]['count']

    async def remove_expired_reports(self):
        """Function to delete expired reports."""
        # The query below uses a timestamp function which differs across DB engines; obtain the correct one
        time_now = self.dao.db_func(self.dao.db.FUNC_TIME_NOW) + '()'
        # Expired reports are where its timestamp is behind the current time (hence less-than)
        query = 'DELETE FROM reports WHERE expires_on < %s' % time_now
        await self.dao.run_sql_list(sql_list=[(query,)])

    async def remove_report_by_id(self, report_id=''):
        """Function to delete a report by its ID."""
        await self.dao.delete('reports', dict(uid=report_id))

    async def get_report_by_id_or_title(self, by_id=False, by_title=False, report='', add_expiry_bool=True):
        """Given a report ID or title, returns matching report records."""
        # Retrieval by ID or title must be specified, not both nor neither
        if (by_id and by_title) or (not by_id and not by_title):
            raise ValueError('Incorrect parameters: unsure if retrieval is by report ID or title.')
        # Proceed to set up the query: ensure date fields are converted into strings
        date_written = self.dao.db.sql_date_field_to_str('date_written', str_suffix=True)
        start_date = self.dao.db.sql_date_field_to_str('start_date', str_suffix=True)
        end_date = self.dao.db.sql_date_field_to_str('end_date', str_suffix=True)
        # Set up the sql statements to select the fields
        fields = [date_written, start_date, end_date]
        if add_expiry_bool:
            # Similar to remove_expired_reports() above, get the appropriate time-function and execute a query
            time_now = self.dao.db_func(self.dao.db.FUNC_TIME_NOW) + '()'
            fields.append('expires_on < %s AS is_expired' % time_now)
        column = 'title' if by_title else 'uid'
        query = 'SELECT *, %s FROM reports WHERE %s = %s' % (', '.join(fields), column, self.dao.db_qparam)
        return await self.dao.raw_select(query, parameters=tuple([report]))

    async def get_report_by_title(self, report_title='', add_expiry_bool=True):
        """Given a report title, returns matching report records."""
        return await self.get_report_by_id_or_title(by_title=True, report=report_title, add_expiry_bool=add_expiry_bool)

    async def get_report_by_id(self, report_id='', add_expiry_bool=True):
        """Given a report ID, returns matching report records."""
        return await self.get_report_by_id_or_title(by_id=True, report=report_id, add_expiry_bool=add_expiry_bool)

    async def rollback_report(self, report_id=''):
        """Function to rollback a report to its initial state."""
        # The list of SQL statements to run for this operation
        sql_list = [
            # Delete the report sentences - this will trigger related true/false positives/negatives to be deleted
            await self.dao.delete('report_sentences', dict(report_uid=report_id), return_sql=True),
            # Delete related images for this report
            await self.dao.delete('original_html', dict(report_uid=report_id), return_sql=True)
        ]
        # For each table that contains the initial report data
        for table in self.dao.db.backup_table_list:
            columns = ', '.join(self.dao.db.get_column_names_from_table(table))
            # Construct the INSERT INTO SELECT statement: select all columns from the initial data and insert into table
            sql = 'INSERT INTO %s (%s) SELECT %s FROM %s%s WHERE report_uid = %s;' % \
                  (table, columns, columns, table, self.dao.db.backup_table_suffix, self.dao.db_qparam)
            # Table names can't be parameters so state the report ID as a parameter for the above statement
            parameters = tuple([report_id])
            # Append to the SQL list the statement itself and the parameters to use
            sql_list.append(tuple([sql, parameters]))
        # Run the deletions and insertions for this method altogether; return if it was successful
        return await self.dao.run_sql_list(sql_list=sql_list)

    async def export_report_data(self, report=None, report_id='', report_title=''):
        """Function to retrieve all the data for a report."""
        # If we have no report, retrieve the report using the ID or title
        if not report:
            if report_id:
                report = (await self.get_report_by_id(report_id=report_id))[0]
            elif report_title:
                report = (await self.get_report_by_title(report_title=report_title))[0]
            else:
                raise ValueError('Insufficient arguments to retrieve report data.')
        # Using the report, obtain the ID (if not already given) to continue the data retrieval
        if not report_id:
            # Be wary, this can raise KeyError
            report_id = report['uid']
        # Retrieve and return the rest of the report data
        sentences = await self.get_report_sentences_with_attacks(report_id=report_id)
        categories = await self.get_report_categories_for_display(report_id, include_keynames=True)
        keywords = await self.get_report_aggressors_victims(report_id, include_display=True)
        # We aren't saving victim-groups as of now
        keywords['victims'].pop('groups')
        keywords['victims']['categories'] = [row.get('display_name', cat_code) for cat_code, row in categories.items()]
        keywords['victims']['category_codes'] = list(categories.keys())
        all_data = dict(report=report, sentences=sentences)
        all_data.update(keywords)
        return all_data

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

    def ml_reg_split(self, techniques):
        list_of_legacy, list_of_techs = [], []
        for k, v in techniques.items():
            try:
                if len(v['example_uses']) > 8:
                    list_of_techs.append((v['id'], v['name']))
                else:
                    list_of_legacy.append(v['id'])
            except:
                print(v)
        return list_of_legacy, list_of_techs
