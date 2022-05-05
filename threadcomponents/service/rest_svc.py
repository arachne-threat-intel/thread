# NOTICE: As required by the Apache License v2.0, this notice is to state this file has been modified by Arachne Digital
# This file has been moved into a different directory
# To see its full history, please use `git log --follow <filename>` to view previous commits and additional contributors

import asyncio
import json
import logging
import os
import pandas as pd
import re

from aiohttp import web
from datetime import datetime, timedelta
from enum import Enum, unique
from functools import partial
from io import StringIO
from urllib.parse import unquote

PUBLIC = 'public'
UID = 'uid'
URL = 'url'
REST_IGNORED = dict(ignored=1)
REST_SUCCESS = dict(success=1)


@unique
class ReportStatus(Enum):
    QUEUE = ('queue', 'In Queue')
    NEEDS_REVIEW = ('needs_review', 'Needs Review')
    IN_REVIEW = ('in_review', 'Analyst Reviewing')
    COMPLETED = ('completed', 'Completed')

    # For each tuple above, set the value and display name as two separate properties
    def __new__(cls, val: str, display: str):
        obj = object.__new__(cls)
        obj._value_ = val
        obj.display_name = display
        return obj


class RestService:
    def __init__(self, web_svc, reg_svc, data_svc, ml_svc, dao, dir_prefix='', queue_limit=None, max_tasks=1,
                 attack_file_settings=None):
        self.MAX_TASKS = max_tasks
        self.QUEUE_LIMIT = queue_limit
        self.dao = dao
        self.data_svc = data_svc
        self.web_svc = web_svc
        self.ml_svc = ml_svc
        self.reg_svc = reg_svc
        self.is_local = self.web_svc.is_local
        self.queue_map = dict()  # map each user to their own queue
        try:
            self.queue = asyncio.Queue()  # task queue
        except RuntimeError as e:  # a RuntimeError may occur if there is no event loop
            logging.error('Encountered error %s; attempting to resolve by setting new event loop' % str(e))
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.queue = asyncio.Queue()
        self.current_tasks = []  # tasks that are currently being executed
        # A dictionary to keep track of report statuses we have seen
        self.seen_report_status = dict()
        # The offline attack dictionary
        attack_file_settings = attack_file_settings or dict()
        default_attack_filepath = os.path.join(dir_prefix, 'threadcomponents', 'models', 'attack_dict.json')
        self.attack_dict_loc = attack_file_settings.get('filepath', default_attack_filepath)
        self.json_tech, self.list_of_legacy, self.list_of_techs = {}, [], []
        self.update_attack_file = attack_file_settings.get('update', False)  # Are we updating this file periodically?
        self.attack_file_indent = attack_file_settings.get('indent', 2)
        self.set_internal_attack_data()

    def set_internal_attack_data(self, load_attack_dict=True):
        """Function to set the class variables holding attack data."""
        if load_attack_dict:
            with open(self.attack_dict_loc, 'r', encoding='utf_8') as attack_dict_f:
                self.json_tech = json.load(attack_dict_f)
        self.list_of_legacy, self.list_of_techs = self.data_svc.ml_reg_split(self.json_tech)

    async def fetch_and_update_attack_data(self, is_startup=False):
        """Function to fetch and update the attack data."""
        # Did DB-updates occur? Or updates to our internal json-tech dictionary?
        updates, updated_json_tech = False, False
        # The output of the attack-data-updates from data_svc
        added_attacks, inactive_attacks, name_changes = await self.data_svc.fetch_and_update_attack_data()
        # If new attacks were added...
        if added_attacks:
            updates = True
            # We only want to list added attacks after startup because during startup may lead to logging a long list
            if not is_startup:
                logging.info('Consider adding example uses for %s to %s' % (', '.join(added_attacks), self.attack_dict_loc))
        # If attacks were renamed...
        if name_changes:
            updates = True
            # Update the json-tech for each attack with a new name
            for tech_id, new_name, old_db_name in name_changes:
                current_entry = self.json_tech.get(tech_id)
                if current_entry:
                    # Update the name if the name is different to the json-tech's entry
                    current_entry_name = current_entry.get('name')
                    if current_entry_name != new_name:
                        self.json_tech[tech_id]['name'] = new_name
                        updated_json_tech = True
                    # Update similar-words with the old and new names for this attack
                    similar_words = current_entry.get('similar_words', [])
                    for name in [new_name, old_db_name, current_entry_name]:
                        if name not in similar_words:
                            similar_words.append(name)
                            updated_json_tech = True
                    self.json_tech[tech_id]['similar_words'] = similar_words
        # If the json-tech dictionary was updated...
        if updated_json_tech:
            # Ensure any lists dependent on json-tech are updated
            self.set_internal_attack_data(load_attack_dict=False)
            # Update the file it came from if boolean is set
            if self.update_attack_file:
                with open(self.attack_dict_loc, 'w', encoding='utf-8') as json_file_opened:
                    json.dump(self.json_tech, json_file_opened, ensure_ascii=False, indent=self.attack_file_indent)
            else:  # else log the name-changes
                logging.info('The following name changes have occurred in the DB but not in %s' % self.attack_dict_loc)
                for tech_id, new_name, old_db_name in name_changes:
                    logging.info('%s: %s (previously `%s`)' % (tech_id, new_name, old_db_name))
        return updates

    @staticmethod
    def get_status_enum():
        return ReportStatus

    def get_queue_for_user(self, token=None):
        """Function to retrieve queue (as list) for a given user token."""
        # No token = queue for public-use
        token = token or PUBLIC
        # Set up empty list if queue-map doesn't already have one
        if token not in self.queue_map:
            self.queue_map[token] = []
        return self.queue_map[token]

    def remove_report_from_queue_map(self, report):
        """Function to remove given report from internal queue-map."""
        queue = self.get_queue_for_user(token=report.get('token'))
        queue.remove(report[URL])

    def clean_current_tasks(self):
        """Function to remove finished tasks from the current_tasks list."""
        for task in range(len(self.current_tasks)):  # check resources for finished tasks
            if self.current_tasks[task].done():
                del self.current_tasks[task]  # delete finished tasks

    async def prepare_queue(self):
        """Function to add to the queue any reports left from a previous session."""
        reports = await self.dao.get('reports', dict(error=self.dao.db_false_val,
                                                     current_status=ReportStatus.QUEUE.value))
        for report in reports:
            # Sentences from this report may have previously populated other db tables
            # Being selected from the queue will begin analysis again so delete previous progress
            await self.dao.delete('report_sentences', dict(report_uid=report[UID]))
            await self.dao.delete('report_sentence_hits', dict(report_uid=report[UID]))
            await self.dao.delete('original_html', dict(report_uid=report[UID]))
            # Get the relevant queue for this user
            queue = self.get_queue_for_user(token=report.get('token'))
            # Add to the queue
            await self.queue.put(report)
            queue.append(report[URL])

    async def set_status(self, request, criteria=None):
        default_error = dict(error='Error setting status.')
        try:
            # Check for malformed request parameters (KeyError) or criteria being None (TypeError)
            new_status, report_title = criteria['set_status'], criteria['report_title']
        except (KeyError, TypeError):
            return default_error
        # Get the report data from the provided report title
        try:
            report_dict = await self.dao.get('reports', dict(title=unquote(report_title)))
        except TypeError:  # Thrown when unquote() receives a non-string type
            return default_error
        try:
            report_id, r_status = report_dict[0][UID], report_dict[0]['current_status']
        except (KeyError, IndexError):  # Thrown if the report title did not match any report in the db
            return default_error
        # Found a valid report, check if protected by token
        await self.web_svc.action_allowed(request, 'set-status', context=dict(report=report_dict[0]))
        # May be refined to allow reverting statuses in future - should use enum to check valid status
        if new_status == ReportStatus.COMPLETED.value:
            # Check there are no unconfirmed attacks
            unchecked = await self.data_svc.get_unconfirmed_attack_count(report_id=report_id)
            if unchecked:
                partial_msg = '%s %s %s' % \
                              ('is' if unchecked == 1 else 'are', unchecked, 'attack' + ('' if unchecked == 1 else 's'))
                return dict(error='There %s unconfirmed for this report.' % partial_msg, alert_user=1)
            # Check the report status is not queued (because queued reports will have 0 unchecked attacks)
            if r_status not in [ReportStatus.NEEDS_REVIEW.value, ReportStatus.IN_REVIEW.value]:
                return default_error
            # Finally, update the status
            await self.dao.update('reports', where=dict(uid=report_id), data=dict(current_status=new_status))
            self.seen_report_status[report_id] = new_status
            return REST_SUCCESS
        else:
            return default_error

    async def delete_report(self, request, criteria=None):
        default_error = dict(error='Error deleting report.')
        try:
            # Check for malformed request parameters (KeyError) or criteria being None (TypeError)
            report_title = criteria['report_title']
        except (KeyError, TypeError):
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
        # Found a valid report, check if protected by token
        await self.web_svc.action_allowed(request, 'delete-report', context=dict(report=report[0]))
        # Check a queued, error-free report ID hasn't been provided -> this may be mid-analysis
        if (not r_error) and (r_status not in [ReportStatus.NEEDS_REVIEW.value, ReportStatus.IN_REVIEW.value,
                                               ReportStatus.COMPLETED.value]):
            return default_error
        # Proceed with delete
        await self.dao.delete('reports', dict(uid=report_id))
        return REST_SUCCESS

    async def remove_sentence(self, request, criteria=None):
        default_error = dict(error='Error removing item.')
        try:
            # Check for malformed request parameters (KeyError) or criteria being None (TypeError)
            sen_id = criteria['sentence_id']
        except (KeyError, TypeError):
            return default_error
        report_id = await self.data_svc.get_report_id_from_sentence_id(sentence_id=sen_id)
        # Use this report ID to check permissions, determine its status and if we can continue
        await self.check_report_permission(request, report_id=report_id, action='delete-sentence')
        if not await self.check_report_status_multiple(
                report_id=report_id, statuses=[ReportStatus.IN_REVIEW.value, ReportStatus.NEEDS_REVIEW.value]):
            return default_error
        # This is most likely a sentence ID sent through, so delete as expected
        await self.dao.delete('report_sentences', dict(uid=sen_id))
        # This could also be an image, so delete from original_html table too
        await self.dao.delete('original_html', dict(uid=sen_id))
        # As a report has been edited, ensure the report's status reflects analysis has started
        await self.check_report_status(report_id=report_id, update_if_false=True)
        return REST_SUCCESS

    async def rollback_report(self, request, criteria=None):
        default_error = dict(error='Error completing rollback of report.')
        try:
            # Check for malformed request parameters (KeyError) or criteria being None (TypeError)
            report_title = criteria['report_title']
        except (KeyError, TypeError):
            return default_error
        # Get the report data from the provided report title
        try:
            report = await self.dao.get('reports', dict(title=unquote(report_title)))
        except TypeError:  # Thrown when unquote() receives a non-string type
            return default_error
        try:
            report_id, r_status = report[0][UID], report[0]['current_status']
        except (KeyError, IndexError):  # Thrown if the report title is not in the db or db record is malformed
            return default_error
        # Found a valid report, check if protected by token
        await self.web_svc.action_allowed(request, 'rollback-report', context=dict(report=report[0]))
        # Only mid-review reports can be rollbacked
        if r_status != ReportStatus.IN_REVIEW.value:
            return default_error
        # Proceed with the rollback; first, hide the report from the UI and give it a temp status
        await self.dao.update('reports', where=dict(uid=report_id), data=dict(current_status='HIDDEN'))
        # Execute the rollback
        success = await self.data_svc.rollback_report(report_id=report_id)
        if success:
            # Finish by setting the status to 'Needs Review' and removing error (if error was added previously)
            await self.dao.update(
                'reports', where=dict(uid=report_id),
                data=dict(current_status=ReportStatus.NEEDS_REVIEW.value, error=self.dao.db_false_val))
            self.seen_report_status[report_id] = ReportStatus.NEEDS_REVIEW.value
            return REST_SUCCESS
        else:
            # If unsuccessful: log this, change report status back to what it was and add error flag
            logging.error('Report %s failed to rollback.' % report_id)
            await self.dao.update('reports', where=dict(uid=report_id),
                                  data=dict(current_status=r_status, error=self.dao.db_true_val))
            return default_error

    async def sentence_context(self, request, criteria=None):
        sen_id = await self.check_and_get_sentence_id(request, request_data=criteria)
        return await self.data_svc.get_active_sentence_hits(sentence_id=sen_id)

    async def confirmed_attacks(self, request, criteria=None):
        sen_id = await self.check_and_get_sentence_id(request, request_data=criteria)
        return await self.data_svc.get_confirmed_attacks_for_sentence(sentence_id=sen_id)

    async def check_and_get_sentence_id(self, request, request_data=None):
        """Function to verify request data contains a valid sentence ID and return it."""
        try:
            # Check for malformed request parameters (KeyError) or request_data being None (TypeError)
            sen_id = request_data['sentence_id']
        except (KeyError, TypeError):
            raise web.HTTPBadRequest()
        report_id = await self.data_svc.get_report_id_from_sentence_id(sentence_id=sen_id)
        if not report_id:
            raise web.HTTPBadRequest()
        # No further checks if local
        if self.is_local:
            return sen_id
        # Check permissions
        await self.check_report_permission(request, report_id=report_id, action='get-sentence')
        return sen_id

    async def insert_report(self, request, criteria=None):
        # Check for errors whilst updating request data with token (if applicable)
        error = await self.pre_insert_add_token(request, request_data=criteria, key='title')
        if error:
            return error
        # For both the title and url...
        for column in ['title', URL]:
            # Obtain the value from the request; return an error if an argument is missing
            value = str(criteria.get(column, '')).strip()
            if not value:
                return dict(error='Missing value for %s.' % column, alert_user=1)
            # Place title and URL in list to be compatible with _insert_batch_reports()
            criteria[column] = [value]
        return await self._insert_batch_reports(request, criteria, 1, token=criteria.get('token'))

    async def insert_csv(self, request, criteria=None):
        # Check for errors whilst updating request data with token (if applicable)
        error = await self.pre_insert_add_token(request, request_data=criteria, key='file')
        if error:
            return error
        try:
            df = self.verify_csv(criteria['file'])
        except (TypeError, ValueError) as e:  # Any errors occurring from the csv-checks
            return dict(error=str(e), alert_user=1)
        return await self._insert_batch_reports(request, df, df.shape[0], token=criteria.get('token'))

    async def pre_insert_add_token(self, request, request_data=None, key=None):
        """Function to check sent request data before inserting reports and return an error if there was an issue."""
        try:
            # Check for malformed request parameters (KeyError) or criteria being None (TypeError)
            request_data[key]
        except (KeyError, TypeError):
            return dict(error='Error inserting report(s).')
        # If running locally, there are no further checks but ensure the token is None (to avoid mix of ''s and Nones)
        if self.is_local:
            request_data.update(token=None)
            return None
        # If not running locally, check the token from the request_data is valid if one is given
        token = request_data.get('token')  # obtain the token
        if token:
            # If there is a token, check it is a valid token
            user = await self.web_svc.get_username_from_token(request, token=token)
            # Alert user if they tried to associate their submission with an invalid token
            if user is None:
                return dict(error='Report(s) not submitted. Please enter a valid token or confirm you are making this '
                                  'submission public. To find your token, please refer to your Arachne profile. If '
                                  'this error is persistent, please contact us.', alert_user=1)
        # If there is no token, blank data with None (to avoid mix of empty strings and Nones)
        else:
            request_data.update(token=None)
        return None

    async def _insert_batch_reports(self, request, batch, row_count, token=None):
        # Possible responses to the request
        default_error, success = dict(error='Error inserting report(s).'), REST_SUCCESS.copy()
        # Different counts for different reasons why reports are not queued
        limit_exceeded, duplicate_urls, malformed_urls = 0, 0, 0
        # Get the relevant queue for this user
        queue = self.get_queue_for_user(token=token)
        for row in range(row_count):
            # If a new report will exceed the queue limit, stop iterating through further reports
            if self.QUEUE_LIMIT and len(queue) + 1 > self.QUEUE_LIMIT:
                limit_exceeded = row_count - row
                break
            try:
                title, url = batch['title'][row].strip(), batch[URL][row].strip()
            # Check for malformed request parameters; AttributeError thrown if not strings
            except (AttributeError, KeyError):
                return default_error
            try:
                # Enforce http on urls that do not begin with http(s)
                prefix_check = re.match('^https?://', url, re.IGNORECASE)
                url = 'http://' + url if prefix_check is None else url
                await self.web_svc.verify_url(request, url=url)
            # Raised if verify_url() fails
            except ValueError as ve:
                return dict(error=str(ve), alert_user=1)
            # Ensure the report has a unique title
            title = await self.data_svc.get_unique_title(title)
            # Set up a temporary dictionary to represent db object
            temp_dict = dict(title=title, url=url, current_status=ReportStatus.QUEUE.value, token=token)
            # Before adding to the db, check that this submitted URL isn't already in the queue; if so, skip it
            skip_report = False
            for queued_url in queue:
                try:
                    if self.web_svc.urls_match(testing_url=url, matches_with=queued_url):
                        skip_report = True
                        duplicate_urls += 1
                        break
                except ValueError:
                    skip_report = True
                    malformed_urls += 1
                    break
            # Proceed to add to queue if URL was not found
            if not skip_report:
                # Insert report into db and update temp_dict with inserted ID from db
                temp_dict[UID] = await self.dao.insert_generate_uid('reports', temp_dict)
                # Finally, update queue and check queue when batch is finished
                await self.queue.put(temp_dict)
                queue.append(url)
        if limit_exceeded or duplicate_urls or malformed_urls:
            message = '%s of %s ' % (sum([limit_exceeded, duplicate_urls, malformed_urls]), row_count) + \
                      'report(s) not added to the queue.\n- %s exceeded queue limit.' % limit_exceeded + \
                      '\n- %s already in the queue/duplicate URL(s).' % duplicate_urls + \
                      '\n- %s malformed URL(s).' % malformed_urls
            success.update(dict(info=message, alert_user=1))
        asyncio.create_task(self.check_queue())
        return success

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
        title = 'title'
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
            elif col.strip().lower() == URL:
                new_columns[col] = URL
            else:
                raise ValueError(columns_error)
        # Check that the new columns' length is exactly 2
        if len(new_columns) != 2:
            raise ValueError(columns_error)
        # Create a new df with renamed columns
        new_df = df.rename(columns=new_columns)
        # Tidy up the values before further checks
        new_df = new_df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        # Validate each row has a value
        for col in [title, URL]:
            values = pd.Series(list(new_df[col].values))
            # If any value in this column is an empty string or not a string (missing values become NaNs), raise error
            if (values.map(type) != str).any() or (values.map(len) == 0).any():
                raise ValueError('Column `%s` in CSV is missing text in at least one row' % col)
        # All previous checks passed: return the new df
        return new_df

    async def check_queue(self):
        """
        description: executes as concurrent job, manages taking jobs off the queue and executing them.
        input: nil
        output: nil
        """
        self.clean_current_tasks()
        while self.queue.qsize() > 0:  # while there are still tasks to do...
            await asyncio.sleep(1)  # allow other tasks to run while waiting
            while len(self.current_tasks) >= self.MAX_TASKS:  # check resource pool until a task is finished
                self.clean_current_tasks()
                await asyncio.sleep(1)  # allow other tasks to run while waiting
            criteria = await self.queue.get()  # get next task off queue and run it
            # Use run_in_executor (due to event loop potentially blocked otherwise) to start analysis
            loop = asyncio.get_running_loop()
            task = loop.run_in_executor(None, partial(self.run_start_analysis, criteria=criteria))
            self.current_tasks.append(task)

    def run_start_analysis(self, criteria=None):
        """Function to run start_analysis() for given criteria."""
        # Create a new loop to execute the async method as per https://stackoverflow.com/a/46075571
        loop = asyncio.new_event_loop()
        try:
            coroutine = self.start_analysis(criteria)
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coroutine)
        finally:
            loop.close()

    async def start_analysis(self, criteria=None):
        report_id = criteria[UID]
        logging.info('Beginning analysis for ' + report_id)

        original_html, newspaper_article = await self.web_svc.map_all_html(criteria[URL])
        if original_html is None and newspaper_article is None:
            logging.error('Skipping report; could not download url ' + criteria[URL])
            await self.dao.update('reports', where=dict(uid=report_id), data=dict(error=self.dao.db_true_val))
            self.remove_report_from_queue_map(criteria)
            return

        html_data = newspaper_article.text.replace('\n', '<br>')
        article = dict(title=criteria['title'], html_text=html_data)

        # Here we build the sentence dictionary
        html_sentences = self.web_svc.tokenize_sentence(article['html_text'])
        rebuilt, model_dict = await self.ml_svc.build_pickle_file(self.list_of_techs, self.json_tech)

        ml_analyzed_html = await self.ml_svc.analyze_html(self.list_of_techs, model_dict, html_sentences)
        regex_patterns = await self.dao.get('regex_patterns')
        reg_analyzed_html = self.reg_svc.analyze_html(regex_patterns, html_sentences)

        # Merge ML and Reg hits
        analyzed_html = await self.ml_svc.combine_ml_reg(ml_analyzed_html, reg_analyzed_html)

        for s_idx, sentence in enumerate(analyzed_html):
            if sentence['ml_techniques_found']:
                await self.ml_svc.ml_techniques_found(report_id, sentence, s_idx)
            elif sentence['reg_techniques_found']:
                await self.reg_svc.reg_techniques_found(report_id, sentence, s_idx)
            else:
                data = dict(report_uid=report_id, text=sentence['text'], html=sentence['html'], sen_index=s_idx,
                            found_status=self.dao.db_false_val)
                await self.dao.insert_with_backup('report_sentences', data)

        for e_idx, element in enumerate(original_html):
            html_element = dict(report_uid=report_id, text=element['text'], tag=element['tag'], elem_index=e_idx,
                                found_status=self.dao.db_false_val)
            await self.dao.insert_with_backup('original_html', html_element)

        # The report is about to be moved out of the queue
        update_data = dict(current_status=ReportStatus.NEEDS_REVIEW.value)
        if not self.is_local:
            # Prepare its expiry date (now + 1 week)
            expiry_date = datetime.now() + timedelta(weeks=1)
            expiry_date_str = expiry_date.strftime('%Y-%m-%d %H:%M:%S')
            update_data.update(dict(expires_on=expiry_date_str))
        # Update card to reflect the end of queue
        await self.dao.update('reports', where=dict(uid=report_id), data=update_data)
        # Update the relevant queue for this user
        self.remove_report_from_queue_map(criteria)
        logging.info('Finished analysing report ' + report_id)

    async def add_attack(self, request, criteria=None):
        try:
            # The sentence and attack IDs
            sen_id, attack_id = criteria['sentence_id'], criteria['attack_uid']
        except (KeyError, TypeError):
            return dict(error='Error adding attack.')
        # Get the attack information for this attack id
        attack_dict = await self.dao.get('attack_uids', dict(uid=attack_id))
        # Get the report sentence information for the sentence id
        sentence_dict = await self.dao.get('report_sentences', dict(uid=sen_id))
        # Check the method can continue
        checks = await self._pre_add_reject_attack_checks(request, sen_id=sen_id, sentence_dict=sentence_dict,
                                                          attack_id=attack_id, attack_dict=attack_dict)
        if checks is not None:
            return checks
        a_name, tid, inactive = attack_dict[0]['name'], attack_dict[0]['tid'], attack_dict[0]['inactive']
        if inactive:
            return dict(error="%s, '%s' is not in the current Att%%ck framework. " % (tid, a_name) +
                              'Please contact us if this is incorrect.', alert_user=1)
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
                data=dict(active_hit=self.dao.db_true_val, confirmed=self.dao.db_true_val), return_sql=True))
            # Update model_initially_predicted flag using returned historic_hits
            model_initially_predicted = returned_hit['initial_model_match']
        else:
            # Insert new row in the report_sentence_hits database table to indicate a new confirmed technique
            # This is needed to ensure that requests to get all confirmed techniques works correctly
            sql_commands.append(await self.dao.insert_generate_uid(
                'report_sentence_hits', dict(sentence_id=sen_id, attack_uid=attack_id, attack_tid=tid,
                                             attack_technique_name=a_name, report_uid=sentence_dict[0]['report_uid'],
                                             confirmed=self.dao.db_true_val), return_sql=True))
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
        if not sentence_dict[0]['found_status']:
            sql_commands.append(await self.dao.update(
                'report_sentences', where=dict(uid=sen_id),
                data=dict(found_status=self.dao.db_true_val), return_sql=True))
        # Run the updates, deletions and insertions for this method altogether
        await self.dao.run_sql_list(sql_list=sql_commands)
        # As a technique has been added, ensure the report's status reflects analysis has started
        await self.check_report_status(report_id=sentence_dict[0]['report_uid'], update_if_false=True)
        # Return status message
        return REST_SUCCESS

    async def reject_attack(self, request, criteria=None):
        try:
            # The sentence and attack IDs
            sen_id, attack_id = criteria['sentence_id'], criteria['attack_uid']
        except (KeyError, TypeError):
            return dict(error='Error rejecting attack.')
        # Get the report sentence information for the sentence id
        sentence_dict = await self.dao.get('report_sentences', dict(uid=sen_id))
        # Get the attack information for this attack id
        attack_dict = await self.dao.get('attack_uids', dict(uid=attack_id))
        # Check the method can continue
        checks = await self._pre_add_reject_attack_checks(request, sen_id=sen_id, sentence_dict=sentence_dict,
                                                          attack_id=attack_id, attack_dict=attack_dict)
        if checks is not None:
            return checks
        # Get the sentence to insert by removing html markup
        sentence_to_insert = await self.web_svc.remove_html_markup_and_found(sentence_dict[0]['text'])
        # The list of SQL commands to run in a single transaction
        sql_commands = [
            # Delete any sentence-hits where the model didn't initially guess the attack
            await self.dao.delete(
                'report_sentence_hits', dict(sentence_id=sen_id, attack_uid=attack_id,
                                             initial_model_match=self.dao.db_false_val), return_sql=True),
            # For sentence-hits where the model did guess the attack, flag as inactive and unconfirmed
            await self.dao.update(
                'report_sentence_hits',
                where=dict(sentence_id=sen_id, attack_uid=attack_id, initial_model_match=self.dao.db_true_val),
                data=dict(active_hit=self.dao.db_false_val, confirmed=self.dao.db_false_val), return_sql=True),
            # This sentence may have previously been added as a true positive or false negative; delete these
            await self.dao.delete('true_positives', dict(sentence_id=sen_id, attack_uid=attack_id), return_sql=True),
            await self.dao.delete('false_negatives', dict(sentence_id=sen_id, attack_uid=attack_id), return_sql=True)
        ]
        # Check if the ML model initially predicted this attack
        model_initially_predicted = len(await self.dao.get(
            'report_sentence_hits',
            dict(sentence_id=sen_id, attack_uid=attack_id, initial_model_match=self.dao.db_true_val)))
        # If it did, then this is a false positive
        if model_initially_predicted:
            existing = len(await self.dao.get('false_positives', dict(sentence_id=sen_id, attack_uid=attack_id)))
            if not existing:  # Only add to the false positives table if it's not already there
                sql_commands.append(await self.dao.insert_generate_uid(
                    'false_positives', dict(sentence_id=sen_id, attack_uid=attack_id,
                                            false_positive=sentence_to_insert), return_sql=True))
        # Check if this sentence has other attacks mapped to it
        number_of_techniques = await self.dao.get('report_sentence_hits',
                                                  equal=dict(sentence_id=sen_id, active_hit=self.dao.db_true_val),
                                                  not_equal=dict(attack_uid=attack_id))
        # If it doesn't, update the sentence found-status to false
        if len(number_of_techniques) == 0:
            sql_commands.append(await self.dao.update(
                'report_sentences', where=dict(uid=sen_id),
                data=dict(found_status=self.dao.db_false_val), return_sql=True))
        # Run the updates, deletions and insertions for this method altogether
        await self.dao.run_sql_list(sql_list=sql_commands)
        # As a technique has been rejected, ensure the report's status reflects analysis has started
        await self.check_report_status(report_id=sentence_dict[0]['report_uid'], update_if_false=True)
        return REST_SUCCESS

    async def _pre_add_reject_attack_checks(self, request, sen_id='', sentence_dict=None, attack_id='', attack_dict=None):
        """Function to check for adding or rejecting attacks, enough sentence and attack data has been given."""
        # Check there is sentence data to access
        try:
            a, b = sentence_dict[0]['text'], sentence_dict[0]['found_status']
            report_id = sentence_dict[0]['report_uid']
        except (KeyError, IndexError):  # sentence error (SE) occurred
            return dict(error='Error. Please quote SE%s when contacting admin.' % sen_id, alert_user=1)
        # Check there is attack data to access
        try:
            attack_dict[0]['name'], attack_dict[0]['tid']
        except (KeyError, IndexError):  # attack-info error (AE) occurred
            return dict(error='Error. Please quote AE%s when contacting admin.' % attack_id, alert_user=1)
        # Check permissions
        await self.check_report_permission(request, report_id=report_id, action='add-reject-attack')
        # Check the report status is acceptable (return a report status error (RSE) if not)
        if not await self.check_report_status_multiple(report_id=report_id,
                                                       statuses=[ReportStatus.IN_REVIEW.value,
                                                                 ReportStatus.NEEDS_REVIEW.value]):
            return dict(error='Error. Please quote RSE%s when contacting admin.' % report_id, alert_user=1)
        return None

    async def check_report_permission(self, request, report_id='', action='unspecified'):
        """Function to check a request is permitted given an action involving a report ID."""
        # Do this if we need to
        if self.is_local:
            return True
        # If there is no report ID, the user hasn't supplied something correctly
        if not report_id:
            raise web.HTTPBadRequest()
        # Obtain the report from the db
        report = await self.dao.get('reports', dict(uid=report_id))
        try:
            report[0]['uid']
        except (KeyError, IndexError):
            # No report exists or db record malformed
            raise web.HTTPBadRequest()
        # Run the checker
        await self.web_svc.action_allowed(request, action, context=dict(report=report[0]))

    async def check_report_status(self, report_id='', status=ReportStatus.IN_REVIEW.value, update_if_false=False):
        """Function to check a report is of the given status and updates it if not."""
        # No report ID, no result
        if not report_id:
            return None
        # A quick check without a db call; if the status is right, exit method
        if self.seen_report_status.get(report_id) == status:
            return True
        # Check the db
        report_dict = await self.dao.get('reports', dict(uid=report_id))
        try:
            db_status = report_dict[0]['current_status']
        except (KeyError, IndexError):
            # No report exists or db record malformed: return neither True or False
            return None
        # Else a status for this report was retrieved, continue with the method
        # Before returning result, update dictionary for future checks
        self.seen_report_status[report_id] = db_status
        if db_status == status:
            return True  # Report status matches
        # Report status is not a match; finally update db (if requested) and return boolean
        if update_if_false:
            # Update the report status in the db and the dictionary variable for future checks
            await self.dao.update('reports', where=dict(uid=report_id), data=dict(current_status=status))
            self.seen_report_status[report_id] = status
            return True
        else:
            return False  # Report status does not match and we are not updating the db

    async def check_report_status_multiple(self, report_id='', statuses=None):
        """Function to check a report is one of the given statuses."""
        # No report ID or statuses, no result
        if (not report_id) or statuses is None:
            return None
        # A quick check without a db call; if the status is right, exit method
        if self.seen_report_status.get(report_id) in statuses:
            return True
        # Check the db
        report_dict = await self.dao.get('reports', dict(uid=report_id))
        try:
            db_status = report_dict[0]['current_status']
        except (KeyError, IndexError):
            # No report exists or db record malformed: return neither True or False
            return None
        # Else a status for this report was retrieved, continue with the method
        # Before returning result, update dictionary for future checks
        self.seen_report_status[report_id] = db_status
        if db_status in statuses:
            return True  # Report status matches
        # Report status is not a match
        return False
