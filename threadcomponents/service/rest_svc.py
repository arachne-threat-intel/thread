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
from contextlib import suppress
from datetime import datetime, timedelta
from enum import Enum, unique
from functools import partial
from htmldate import find_date
from io import StringIO
from ipaddress import IPv4Address, IPv4Interface, IPv6Address, IPv6Interface
from urllib.parse import unquote

PUBLIC = 'public'
UID = 'uid'
URL = 'url'
TITLE = 'title'
DATETIME_OBJ = 'datetime_obj'
REST_IGNORED = dict(ignored=1)
REST_SUCCESS = dict(success=1)

# The minimum amount of tecniques for a report to not be discarded
REPORT_TECHNIQUES_MINIMUM = 5


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


@unique
class AssociationWith(Enum):
    CA = 'category'
    CN = 'country'
    RG = 'region'
    GR = 'group'


class RestService:
    def __init__(self, web_svc, reg_svc, data_svc, ml_svc, dao, dir_prefix='', queue_limit=None, max_tasks=1,
                 sentence_limit=None, attack_file_settings=None):
        self.MAX_TASKS = max_tasks
        self.QUEUE_LIMIT = queue_limit
        self.SENTENCE_LIMIT = sentence_limit
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
        updated_json_tech = False

        # The output of the attack-data-updates from data_svc
        attack_data = self.data_svc.fetch_flattened_attack_data()
        await self.data_svc.update_db_with_flattened_attack_data(attack_data=attack_data)
        self.update_json_tech_with_flattened_attack_data(attack_data=attack_data, is_startup=is_startup)

    def update_json_tech_with_flattened_attack_data(self, attack_data, is_startup):
        """Function to update the attack dictionary file."""
        # Loop the attack data and check if any attacks have been added or renamed or changed in anyway
        added_count, updated_count = 0, 0
        for attack_uid, attack_item in attack_data.items():
            # If the attack is not in the json-tech dictionary, add it
            if attack_uid not in self.json_tech:
                added_count += 1
                self.json_tech[attack_uid] = attack_item
                self.json_tech[attack_uid]['id'] = self.json_tech[attack_uid].pop('tid')

                # We only want to list added attacks after startup because during startup may lead to logging a long list
                if not is_startup:
                    logging.info(f'Consider adding example uses for {attack_uid} to {self.attack_dict_loc}')
            else:
                # print('We have an existing attack: %s' % attack_uid)
                updated = False
                current_entry = self.json_tech.get(attack_uid)
                if current_entry['id'] != attack_item['tid']:
                    print('ID MISMATCH: This should not happen, skipping', attack_uid)

                # Check description change
                if current_entry['description'] != attack_item['description']:
                    updated = True
                    current_entry['description'] = attack_item['description']

                # Check for new example uses
                for example_use in attack_item['example_uses']:
                    if example_use not in current_entry['example_uses']:
                        updated = True
                        current_entry['example_uses'].append(example_use)

                # Check similar words
                for similar_word in attack_item['similar_words']:
                    if similar_word not in current_entry['similar_words']:
                        updated = True
                        current_entry['similar_words'].append(similar_word)

                # Check for name change
                if current_entry['name'] != attack_item['name']:
                    updated = True
                    for name in [current_entry['name'], attack_item['name']]:
                        if name not in current_entry['similar_words']:
                            current_entry['similar_words'].append(name)

                    current_entry['name'] = attack_item['name']

                if updated:
                    updated_count += 1

        logging.info(f'Added {added_count} new attacks and updated {updated_count} existing attacks to in memory attack dictionary')

        self.set_internal_attack_data(load_attack_dict=False)

        if self.update_attack_file:
            logging.info(f'Writing updated attack dictionary to {self.attack_dict_loc}')
            with open(self.attack_dict_loc, 'w', encoding='utf-8') as json_file_opened:
                json.dump(self.json_tech, json_file_opened, ensure_ascii=False, indent=self.attack_file_indent)

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
        temp_current_tasks = []
        for job in self.current_tasks:  # check resources for finished tasks
            if not job.done():
                temp_current_tasks.append(job)  # keep incomplete tasks
        self.current_tasks = temp_current_tasks

    async def prepare_queue(self):
        """Function to add to the queue any reports left from a previous session."""
        reports = await self.dao.get('reports', dict(error=self.dao.db_false_val,
                                                     current_status=ReportStatus.QUEUE.value))
        for report in reports:
            # Sentences from this report may have previously populated other db tables
            # Being selected from the queue will begin analysis again so delete previous progress
            report_id = report[UID]
            await self.dao.delete('report_sentences', dict(report_uid=report_id))
            await self.dao.delete('report_sentence_queue_progress', dict(report_uid=report_id))
            await self.dao.delete('report_sentence_hits', dict(report_uid=report_id))
            await self.dao.delete('original_html', dict(report_uid=report_id))
            # Get the relevant queue for this user
            queue = self.get_queue_for_user(token=report.get('token'))
            # Add to the queue
            await self.queue.put(report)
            queue.append(report[URL])

    async def _report_pre_check(self, request, criteria, action, report_variables, criteria_variables):
        """Function that given request data, checks the variables needed for the request are there.
        :return: report, error"""
        try:
            report_title = criteria['report_title']
        except (KeyError, TypeError):
            return None, True
        for variable in (criteria_variables or []):
            try:
                # Check for malformed request parameters (KeyError) or criteria being None (TypeError)
                criteria[variable]
            except (KeyError, TypeError):
                return None, True
        # Get the report data from the provided report title
        try:
            report = await self.data_svc.get_report_by_title(report_title=unquote(report_title),
                                                             add_expiry_bool=(not self.is_local))
        except TypeError:  # Thrown when unquote() receives a non-string type
            return None, True
        # Check we can obtain what we need about the report
        for variable in (report_variables or []):
            try:
                report[0][variable]
            except (KeyError, IndexError):  # Thrown if the report title is not in the db or db record is malformed
                return None, True
        # Found a valid report, check if protected by token
        await self.web_svc.action_allowed(request, action, context=dict(report=report[0]))
        return report[0], False

    async def set_status(self, request, criteria=None):
        default_error = dict(error='Error setting status.')
        # Do initial report checks
        report_dict, error = await self._report_pre_check(request, criteria, 'set-status',
                                                          [UID, 'current_status', 'date_written'], ['set_status'])
        if error:
            return default_error
        new_status = criteria['set_status']
        report_id, r_status, date_written = report_dict[UID], report_dict['current_status'], report_dict['date_written']
        # May be refined to allow reverting statuses in future - should use enum to check valid status
        if new_status == ReportStatus.COMPLETED.value:
            # Check there are no unconfirmed attacks
            unchecked = await self.data_svc.get_unconfirmed_undated_attack_count(report_id=report_id)
            if unchecked:
                partial_msg = '%s %s %s' % \
                              ('is' if unchecked == 1 else 'are', unchecked, 'attack' + ('' if unchecked == 1 else 's'))
                return dict(error='There %s unconfirmed or with no start date for this report.' % partial_msg,
                            alert_user=1)
            # Check the report status is not queued (because queued reports will have 0 unchecked attacks)
            if r_status not in [ReportStatus.NEEDS_REVIEW.value, ReportStatus.IN_REVIEW.value]:
                return default_error
            if not date_written:
                return dict(error='Please set an Article Publication Date for this report.', alert_user=1)
            # Finally, update the status and expiry date
            update_data = dict(current_status=new_status)
            self.add_report_expiry(data=update_data, days=1)
            await self.dao.update('reports', where=dict(uid=report_id), data=update_data)
            self.seen_report_status[report_id] = new_status
            # Before finishing, do any post-complete tasks if necessary
            if not self.is_local:
                report_data = await self.data_svc.export_report_data(report_id=report_id)
                await self.web_svc.on_report_complete(request, report_data)
            return REST_SUCCESS
        else:
            return default_error

    async def delete_report(self, request, criteria=None):
        default_error = dict(error='Error deleting report.')
        # Do initial report checks
        report, error = await self._report_pre_check(request, criteria, 'delete-report',
                                                     [UID, 'current_status', 'error'], None)
        if error:
            return default_error
        report_id, r_status, r_error = report[UID], report['current_status'], report['error']
        # Check a queued, error-free report ID hasn't been provided -> this may be mid-analysis
        if (not r_error) and (r_status not in [ReportStatus.NEEDS_REVIEW.value, ReportStatus.IN_REVIEW.value,
                                               ReportStatus.COMPLETED.value]):
            return default_error
        # Proceed with delete
        await self.dao.delete('reports', dict(uid=report_id))
        return REST_SUCCESS

    async def remove_sentence(self, request, criteria=None):
        default_error = dict(error='Error removing item.')
        sen_id, report_id, error = await self.check_edit_sentence_permission(
            request, criteria, default_error, 'delete-sentence')
        if error:
            return error

        # This is most likely a sentence ID sent through, so delete as expected
        await self.dao.delete('report_sentences', dict(uid=sen_id))
        # This could also be an image, so delete from original_html table too
        await self.dao.delete('original_html', dict(uid=sen_id))
        # As a report has been edited, ensure the report's status reflects analysis has started
        await self.check_report_status(report_id=report_id, update_if_false=True)
        return REST_SUCCESS

    async def set_report_categories(self, request, criteria=None):
        default_error, success = dict(error='Error updating report categories.'), REST_SUCCESS.copy()
        # Do initial report checks
        report, error = await self._report_pre_check(request, criteria, 'update-report-categories',
                                                     [UID, 'current_status'], None)
        if error:
            return default_error
        # Check all request parameters
        categories = criteria.get('categories')
        report_id, r_status = report[UID], report['current_status']
        if not isinstance(categories, list):
            return REST_IGNORED
        if r_status not in [ReportStatus.NEEDS_REVIEW.value, ReportStatus.IN_REVIEW.value]:
            return default_error
        # Retrieve current report categories
        current = await self.data_svc.get_report_category_keynames(report_id)
        valid_categories = set(self.web_svc.categories_dict.keys()).intersection(categories)
        to_add = valid_categories - set(current)
        to_delete = set(current) - valid_categories
        sql_list = []
        # Save the associations
        for category in to_add:
            sql_list.append(await self.dao.insert_generate_uid(
                'report_categories', dict(report_uid=report_id, category_keyname=category), return_sql=True))
        for category in to_delete:
            sql_list.append(await self.dao.delete(
                'report_categories', dict(report_uid=report_id, category_keyname=category), return_sql=True))
        await self.dao.run_sql_list(sql_list=sql_list)
        if sql_list:
            success.update(dict(info='The report categories have been updated.', alert_user=1))
        return success

    async def set_report_keywords(self, request, criteria=None):
        default_error, success = dict(error='Error updating aggressors and victims.'), REST_SUCCESS.copy()
        # Do initial report checks
        report, error = await self._report_pre_check(request, criteria, 'update-report-keywords',
                                                     [UID, 'current_status'], None)
        if error:
            return default_error
        # Check all request parameters
        aggressors = criteria.get('aggressors', dict())
        victims = criteria.get('victims', dict())
        report_id, r_status = report[UID], report['current_status']
        if not (isinstance(aggressors, dict) and isinstance(victims, dict)):
            return REST_IGNORED
        # Check aggressors and victims are passed as lists within these dictionaries
        for associate_dict in [aggressors, victims]:
            for association_type, associations in associate_dict.items():
                # Check a valid association type has been given (unless we are selecting-all)
                if association_type in ['countries_all', 'regions_all', 'categories_all']:
                    continue
                try:
                    AssociationWith(association_type)
                except ValueError:
                    return REST_IGNORED
                # Check the associations for this type are given in a list
                if not isinstance(associations, list):
                    return REST_IGNORED
        if r_status not in [ReportStatus.NEEDS_REVIEW.value, ReportStatus.IN_REVIEW.value]:
            return default_error
        # Retrieve current report aggressors and victims
        current = await self.data_svc.get_report_aggressors_victims(report_id)
        categories = await self.data_svc.get_report_category_keynames(report_id)
        current['victims']['categories'] = categories or []
        # For each aggressor and victim, have the current-data and request-data ready to compare
        aggressor_assoc = [AssociationWith.CN.value, AssociationWith.RG.value, AssociationWith.GR.value]
        victim_assoc = [AssociationWith.CN.value, AssociationWith.RG.value, AssociationWith.CA.value,
                        AssociationWith.GR.value]
        to_compare = [('aggressor', current['aggressors'], aggressors, False, aggressor_assoc),
                      ('victim', current['victims'], victims, True, victim_assoc)]
        # For each aggressor and victim, we know we need to go through countries and groups
        to_process = [('report_countries', 'country', 'country_codes', AssociationWith.CN.value, 'countries_all',
                       self.data_svc.country_dict.keys()),
                      ('report_regions', 'region', 'region_ids', AssociationWith.RG.value, 'regions_all',
                       self.data_svc.region_dict.keys()),
                      ('report_categories', 'category_keyname', 'categories', AssociationWith.CA.value,
                       'categories_all', self.web_svc.categories_dict.keys()),
                      ('report_keywords', 'keyword', 'groups', AssociationWith.GR.value, None,
                       self.web_svc.keyword_dropdown_list)]
        sql_list = []
        # Comparing current-data and request-data dictionaries: loop once to see if we're selecting all
        for assoc_type, current_assoc_dict, request_assoc_dict, allow_select_all, allowed_assoc_types in to_compare:
            if not allow_select_all:
                continue
            # Given the table names/columns, keys to use in the dictionaries ('*_k'), and list of valid values...
            for table_name, table_col, current_k, request_k, sel_all_k, valid_list in to_process:
                if not sel_all_k:
                    continue
                currently_is_all = current_assoc_dict[sel_all_k]
                requesting_is_all = request_assoc_dict.get(sel_all_k)
                if requesting_is_all:
                    # If we are requesting all, ignore any specified values in the list
                    request_assoc_dict[request_k] = []
                    if not currently_is_all:
                        # Requesting all when not currently-all: add an entry in the select-all table for this report
                        db_entry = dict(report_uid=report_id, association_type=assoc_type, association_with=request_k)
                        sql_list.append(await self.dao.insert_generate_uid('report_all_assoc', db_entry,
                                                                           return_sql=True))
                if currently_is_all:
                    # Currently all when not requesting all and values specified...
                    if (not requesting_is_all) and request_assoc_dict.get(request_k):
                        # ...delete entry in the select-all table for this report
                        db_entry = dict(report_uid=report_id, association_type=assoc_type, association_with=request_k)
                        sql_list.append(await self.dao.delete('report_all_assoc', db_entry, return_sql=True))

        # Loop twice to determine which association db entries need to be updated
        for assoc_type, current_assoc_dict, request_assoc_dict, allow_select_all, allowed_assoc_types in to_compare:
            for table_name, table_col, current_k, request_k, sel_all_k, valid_list in to_process:
                if request_k not in allowed_assoc_types:
                    continue
                # From the dictionary and using its relevant key, extract the current and requested data as sets
                current_set = set(current_assoc_dict[current_k])
                requested_set = set(request_assoc_dict.get(request_k, []))
                # Using the valid list of values, determine which of the requested values are valid
                valid_request_values = set(valid_list).intersection(requested_set)
                # Finally determine what values are being added and deleted
                to_add = valid_request_values - set(current_set)
                to_delete = set(current_set) - valid_request_values
                # Build the SQL query for this aggressor/victim country/group
                db_entry = dict(report_uid=report_id, association_type=assoc_type)
                for assoc_val in to_add:
                    temp = db_entry.copy()
                    temp[table_col] = assoc_val
                    sql_list.append(await self.dao.insert_generate_uid(table_name, temp, return_sql=True))
                # Check if there are deletions and current_set = to_delete; if so, no point doing individual deletes
                if (current_set == to_delete) and bool(to_delete) and not bool(to_add):
                    sql_list.append(await self.dao.delete(table_name, db_entry, return_sql=True))
                else:
                    for assoc_val in to_delete:
                        temp = db_entry.copy()
                        temp[table_col] = assoc_val
                        sql_list.append(await self.dao.delete(table_name, temp, return_sql=True))
        await self.dao.run_sql_list(sql_list=sql_list)
        if sql_list:
            success.update(dict(info='The report aggressors and victims have been updated.', alert_user=1))
        return success

    async def update_report_dates(self, request, criteria=None):
        default_error, success = dict(error='Error updating report dates.'), REST_SUCCESS.copy()
        # Do initial report checks
        report, error = await self._report_pre_check(request, criteria, 'update-report-dates',
                                                     [UID, 'current_status', 'date_written'], None)
        if error:
            return default_error
        date_of, start_date, end_date = criteria.get('date_of'), criteria.get('start_date'), criteria.get('end_date')
        # We only want to process booleans sent for these parameters
        same_dates, apply_to_all = criteria.get('same_dates') is True, criteria.get('apply_to_all') is True
        report_id, r_status, r_written = report[UID], report['current_status'], report['date_written']
        r_start, r_end = self.to_datetime_obj(report['start_date']), self.to_datetime_obj(report['end_date'])
        # Check a queued or completed report ID hasn't been provided
        if r_status not in [ReportStatus.NEEDS_REVIEW.value, ReportStatus.IN_REVIEW.value]:
            return default_error
        # Has a date-written not been provided if the report entry in db is lacking one?
        if (not r_written) and not date_of:
            return dict(error='Article Publication Date missing.', alert_user=1)
        # Do date-format and range checks
        start_dict = dict(field='start_date', value=start_date, is_lower=True)
        end_dict = dict(field='end_date', value=end_date, is_upper=True)
        dates = [dict(field='date_written', value=date_of), start_dict, end_dict]
        update_data, checks = self._pre_date_checks(dates, ['date_written'], success)
        if checks:
            return checks
        # Carry out further checks and final data tidy up before updating the database
        start_date_conv, end_date_conv = start_dict.get(DATETIME_OBJ), end_dict.get(DATETIME_OBJ)
        if (start_date_conv and end_date_conv) and same_dates and (end_date_conv != start_date_conv):
            return dict(error='Specified same dates but different dates provided.', alert_user=1)
        # Check that if one date in the date range is given, it fits with previously-saved/other date in range
        far_start_date = (start_date_conv and (not end_date_conv) and r_end and
                          (start_date_conv > r_end.replace(tzinfo=None)))
        near_end_date = (end_date_conv and (not start_date_conv) and r_start and
                         (end_date_conv < r_start.replace(tzinfo=None)))
        if far_start_date or near_end_date:
            return dict(error='The start/end dates do not follow the order of the existing start/end dates.',
                        alert_user=1)
        # Are there any techniques that have start/end dates that don't fit with these new report dates?
        if (not apply_to_all) and (start_date or end_date):
            start_date_lt, start_date_gt = 'start_date < {par_holder}', 'start_date > {par_holder}'
            end_date_lt, end_date_gt = 'end_date < {par_holder}', 'end_date > {par_holder}'
            if start_date and end_date:
                date_query = '({a} OR {b} OR {c} OR {d})'.format(a=start_date_lt, b=end_date_gt,
                                                                 c=start_date_gt, d=end_date_lt)
                date_params = [start_date, end_date, end_date, start_date]
            elif start_date:
                date_query = '({a} OR {b})'.format(a=start_date_lt, b=end_date_lt)
                date_params = [start_date, start_date]
            else:
                date_query, date_params = '({a} OR {b})'.format(a=end_date_gt, b=start_date_gt), [end_date, end_date]
            bounds_query = (("SELECT * FROM report_sentence_hits WHERE " + date_query + " AND report_uid = "
                            "{par_holder} AND confirmed = %s" % self.dao.db_true_val)
                            .format(par_holder=self.dao.db_qparam))
            out_of_bounds = await self.dao.raw_select(bounds_query, parameters=tuple(date_params + [report_id]))
            if out_of_bounds:
                number = len(out_of_bounds)
                error_msg = ('%s confirmed technique' % number) + (' has' if number == 1 else 's have') \
                            + ' start/end dates outside specified range.'
                return dict(error=error_msg, alert_user=1)
        if same_dates and start_date_conv:
            update_data['end_date'] = start_date
        # Update the database if there were values to update with; inform user of any which were ignored
        if update_data:
            sql_list = [await self.dao.update('reports', where=dict(uid=report_id), data=update_data, return_sql=True)]
            if apply_to_all:  # if we're applying the report date range to all techniques...
                techs_update_data = dict()
                if 'start_date' in update_data:
                    techs_update_data.update(dict(start_date=update_data.get('start_date')))
                if 'end_date' in update_data:
                    techs_update_data.update(dict(end_date=update_data.get('end_date')))
                if techs_update_data:
                    # WHERE clause can be just matching this report ID; narrowing this to unconfirmed techs might cause
                    # issues when they are later confirmed and have old/different date ranges
                    sql_list.append(await self.dao.update('report_sentence_hits', where=dict(report_uid=report_id),
                                                          data=techs_update_data, return_sql=True))
            await self.dao.run_sql_list(sql_list=sql_list)
        if not success.get('info'):  # the success response hasn't already been updated with info
            success.update(dict(info='The report dates have been updated.', alert_user=1))
        return success

    async def rollback_report(self, request, criteria=None):
        default_error = dict(error='Error completing rollback of report.')
        # Do initial report checks
        report, error = await self._report_pre_check(request, criteria, 'rollback-report', [UID, 'current_status'],
                                                     None)
        if error:
            return default_error
        report_id, r_status = report[UID], report['current_status']
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
        ioc = await self.dao.get('report_sentence_indicators_of_compromise', dict(sentence_id=sen_id))
        ioc = '' if not ioc else ioc[0]['refanged_sentence_text']
        techniques = await self.data_svc.get_active_sentence_hits(sentence_id=sen_id)
        return dict(techniques=techniques, ioc=ioc)

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
        if criteria.get('automatically_generated'):
            criteria['automatically_generated'] = [criteria['automatically_generated']]
        else:
            criteria['automatically_generated'] = [None]
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
            return

        # If automatically generated, check associated-data is valid
        if request_data.get('automatically_generated'):
            if not await self.web_svc.auto_gen_data_is_valid(request, request_data):
                return dict(error='Report(s) not submitted. Invalid data for automatically-generated submission.')
        # If not running locally, check if the user is requesting a private submission
        elif request_data.get('private'):
            # Obtain the token to make this submission private
            username, token = await self.web_svc.get_current_arachne_user(request)
            # Update report-data with token or alert user if this was not possible
            if token:
                request_data.update(token=token)
            else:
                return dict(error='Report(s) not submitted. Please ensure you are logged into Arachne for this '
                                  'to be private. If this error is persistent, please contact us.', alert_user=1)
        # If public (no token), blank data with None (to avoid mix of empty strings and Nones)
        else:
            request_data.update(token=None)

    async def _insert_batch_reports(self, request, batch, row_count, token=None):
        # Possible responses to the request
        default_error, success = dict(error='Error inserting report(s).'), REST_SUCCESS.copy()
        # Different counts for different reasons why reports are not queued
        limit_exceeded, duplicate_urls, malformed_urls, long_titles, long_urls = 0, 0, 0, 0, 0
        # Get the relevant queue for this user
        queue = self.get_queue_for_user(token=token)
        for row in range(row_count):
            # If a new report will exceed the queue limit, stop iterating through further reports
            if self.QUEUE_LIMIT and len(queue) + 1 > self.QUEUE_LIMIT:
                limit_exceeded = row_count - row
                break
            try:
                title, url = batch['title'][row].strip(), batch[URL][row].strip()
                automatically_generated = batch['automatically_generated'][row] \
                    if 'automatically_generated' in batch.keys() else None
            # Check for malformed request parameters; AttributeError thrown if not strings
            except (AttributeError, KeyError):
                return default_error
            try:
                # Enforce http on urls that do not begin with http(s)
                prefix_check = re.match('^https?://', url, re.IGNORECASE)
                url = 'http://' + url if prefix_check is None else url
                # Drop fragments
                if '#' in url:
                    url = url[:url.index('#')]
                await self.web_svc.verify_url(request, url=url)
            # Raised if verify_url() fails
            except ValueError as ve:
                return dict(error=str(ve), alert_user=1)
            # Ensure the report has a unique title
            title = await self.data_svc.get_unique_title(title)
            # Set up a temporary dictionary to represent db object
            temp_dict = dict(
                title=title,
                url=url,
                current_status=ReportStatus.QUEUE.value,
                automatically_generated=automatically_generated,
                token=token
            )
            self.add_report_expiry(data=temp_dict, weeks=1)
            # Are we skipping this report?
            skip_report = False
            if len(title) > 200:
                long_titles += 1
                skip_report = True
            if len(url) > 500:
                long_urls += 1
                skip_report = True
            if not skip_report:
                # Before adding to the db, check that this submitted URL isn't already in the queue; if so, skip it
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
            # Proceed to add to queue if report is not being skipped
            if not skip_report:
                # Insert report into db and update temp_dict with inserted ID from db
                temp_dict[UID] = await self.dao.insert_generate_uid('reports', temp_dict)
                # Finally, update queue and check queue when batch is finished
                await self.queue.put(temp_dict)
                queue.append(url)
        if limit_exceeded or duplicate_urls or malformed_urls or long_titles or long_urls:
            total_skipped = sum([limit_exceeded, duplicate_urls, malformed_urls, long_titles, long_urls])
            message = '%s of %s ' % (total_skipped, row_count) + 'report(s) not added to the queue.' + \
                      '\n- %s exceeded queue limit.' % limit_exceeded + \
                      '\n- %s already in the queue/duplicate URL(s).' % duplicate_urls + \
                      '\n- %s malformed URL(s).' % malformed_urls + \
                      '\n- %s report-title(s) exceeded 200-character limit.' % long_titles + \
                      '\n- %s URL(s) exceeded 500-character limit.' % long_urls
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
        # Create a new df with renamed columns & validate each row has a value
        new_df = df.rename(columns=new_columns)
        for col in [title, URL]:
            new_df[col] = new_df[col].map(lambda x: x.strip() if isinstance(x, str) else x)
            values = pd.Series(new_df[col].to_list())
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
        logging.info('CHECKING QUEUE')
        self.clean_current_tasks()
        while self.queue.qsize() > 0:  # while there are still tasks to do...
            logging.info('QUEUE SIZE: ' + str(self.queue.qsize()))
            await asyncio.sleep(1)  # allow other tasks to run while waiting
            while len(self.current_tasks) >= self.MAX_TASKS:  # check resource pool until a task is finished
                self.clean_current_tasks()
                await asyncio.sleep(1)  # allow other tasks to run while waiting
            criteria = await self.queue.get()  # get next task off queue and run it
            # Use run_in_executor (due to event loop potentially blocked otherwise) to start analysis
            loop = asyncio.get_running_loop()
            try:
                task = loop.run_in_executor(None, partial(self.run_start_analysis, criteria=criteria))
                self.current_tasks.append(task)
                await task
            except Exception as e:
                logging.error('Report analysis failed: ' + str(e))
                await self.error_report(criteria)
                continue

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

    async def error_report(self, report):
        """Function to error a given report."""
        report_id = report[UID]
        await self.dao.update('reports', where=dict(uid=report_id), data=dict(error=self.dao.db_true_val))
        self.remove_report_from_queue_map(report)
        await self.remove_report_if_automatically_generated(report_id)

    async def start_analysis(self, criteria=None):
        report_id = criteria[UID]
        logging.info('Beginning analysis for ' + report_id)

        original_html, newspaper_article = await self.web_svc.map_all_html(criteria[URL],
                                                                           sentence_limit=self.SENTENCE_LIMIT)
        if original_html is None and newspaper_article is None:
            logging.error('Skipping report; could not download url ' + criteria[URL])
            await self.error_report(criteria)
            return

        html_data = newspaper_article.text.replace('\n', '<br>')
        article = dict(title=criteria[TITLE], html_text=html_data)
        # Obtain the article date if possible
        article_date = None
        with suppress(ValueError):
            article_date = find_date(criteria[URL])
        # Check any obtained date is a sensible value to store in the database
        with suppress(TypeError, ValueError):
            self.check_input_date(article_date)

        # Here we build the sentence dictionary
        html_sentences = self.web_svc.tokenize_sentence(article['html_text'], sentence_limit=self.SENTENCE_LIMIT)
        if not html_sentences:
            logging.error('Skipping report; could not retrieve sentences from url ' + criteria[URL])
            await self.error_report(criteria)
            return

        html_sentences = html_sentences[:self.SENTENCE_LIMIT]
        await self.dao.insert_generate_uid('report_sentence_queue_progress',
                                           dict(report_uid=report_id, sentence_count=len(html_sentences)))

        rebuilt, model_dict = await self.ml_svc.build_pickle_file(self.list_of_techs, self.json_tech)

        ml_analyzed_html = await self.ml_svc.analyze_html(self.list_of_techs, model_dict, html_sentences)
        regex_patterns = await self.dao.get('regex_patterns')
        reg_analyzed_html = self.reg_svc.analyze_html(regex_patterns, html_sentences)

        # Merge ML and Reg hits
        analyzed_html = await self.ml_svc.combine_ml_reg(ml_analyzed_html, reg_analyzed_html)

        for s_idx, sentence in enumerate(analyzed_html):
            sentence['text'] = self.dao.truncate_str(sentence['text'], 800)
            sentence['html'] = self.dao.truncate_str(sentence['html'], 900)
            if sentence['ml_techniques_found']:
                await self.ml_svc.ml_techniques_found(report_id, sentence, s_idx, tech_start_date=article_date)
            elif sentence['reg_techniques_found']:
                await self.reg_svc.reg_techniques_found(report_id, sentence, s_idx, tech_start_date=article_date)
            else:
                data = dict(report_uid=report_id, text=sentence['text'], html=sentence['html'], sen_index=s_idx,
                            found_status=self.dao.db_false_val)
                await self.dao.insert_with_backup('report_sentences', data)

        for e_idx, element in enumerate(original_html):
            element['text'] = self.dao.truncate_str(element['text'], 800)
            html_element = dict(report_uid=report_id, text=element['text'], tag=element['tag'], elem_index=e_idx,
                                found_status=self.dao.db_false_val)
            await self.dao.insert_with_backup('original_html', html_element)

        # The report is about to be moved out of the queue
        update_data = dict(current_status=ReportStatus.NEEDS_REVIEW.value)
        # Save the article-date if we have one
        if article_date:
            update_data.update(dict(date_written=article_date))
        # Add expiry date (now + 1 week)
        self.add_report_expiry(data=update_data, weeks=1)
        # Update card to reflect the end of queue
        await self.dao.update('reports', where=dict(uid=report_id), data=update_data)
        # Update the relevant queue for this user
        self.remove_report_from_queue_map(criteria)
        logging.info('Finished analysing report ' + report_id)
        # DB tidy-up including removing report if low quality
        await self.dao.delete('report_sentence_queue_progress', dict(report_uid=report_id))
        await self.remove_report_if_low_quality(report_id)

    async def remove_report_if_low_quality(self, report_id):
        """Function that removes report if its quality is low."""
        reports_found = await self.data_svc.get_report_by_id_or_title(by_id=True, report=report_id)
        if len(reports_found) != 1:
            return

        report = reports_found[0]
        if not report['automatically_generated']:
            return

        unique_techniques_count = await self.data_svc.get_report_unique_techniques_count(report_id=report_id)

        # Remove report if amount of unique techniques found doesn't reach the minimum
        if unique_techniques_count < REPORT_TECHNIQUES_MINIMUM:
            await self.data_svc.remove_report_by_id(report_id=report_id)
            logging.info('Deleted report with ' + str(unique_techniques_count) + ' technique(s) found: ' + report[URL])
            return

        logging.info(str(unique_techniques_count) + ' technique(s) found for report ' + report_id)

    async def remove_report_if_automatically_generated(self, report_id):
        """Function that removes a report if it has been automatically generated."""
        reports_found = await self.data_svc.get_report_by_id_or_title(by_id=True, report=report_id)
        if len(reports_found) != 1:
            return

        report = reports_found[0]
        if not report['automatically_generated']:
            return

        await self.data_svc.remove_report_by_id(report_id=report_id)
        logging.info('Deleted skipped report: ' + report[URL])

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
        checks, report = await self._pre_add_reject_attack_checks(request, sen_id=sen_id, sentence_dict=sentence_dict,
                                                                  attack_id=attack_id, attack_dict=attack_dict)
        if checks is not None:
            return checks
        a_name, tid, inactive = attack_dict[0]['name'], attack_dict[0]['tid'], attack_dict[0]['inactive']
        if inactive:
            return dict(error="%s, '%s' is not in the current Att%%ck framework. " % (tid, a_name) +
                              'Please contact us if this is incorrect.', alert_user=1)
        # Get the sentence to insert by removing html markup
        sentence_to_insert = await self.web_svc.remove_html_markup_and_found(sentence_dict[0]['text'])
        sentence_to_insert = self.dao.truncate_str(sentence_to_insert, 800)
        # Get the report-start-date to default this attack mapping's start date as
        start_date = report['start_date_str']
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
                'report_sentence_hits', where=dict(sentence_id=sen_id, attack_uid=attack_id), return_sql=True,
                data=dict(active_hit=self.dao.db_true_val, confirmed=self.dao.db_true_val)))
            # Update model_initially_predicted flag using returned historic_hits
            model_initially_predicted = returned_hit['initial_model_match']
        else:
            # Insert new row in the report_sentence_hits database table to indicate a new confirmed technique
            # This is needed to ensure that requests to get all confirmed techniques works correctly
            sql_commands.append(await self.dao.insert_generate_uid(
                'report_sentence_hits', dict(sentence_id=sen_id, attack_uid=attack_id, attack_tid=tid,
                                             attack_technique_name=a_name, report_uid=sentence_dict[0]['report_uid'],
                                             confirmed=self.dao.db_true_val, start_date=start_date), return_sql=True))
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
        checks, report = await self._pre_add_reject_attack_checks(request, sen_id=sen_id, sentence_dict=sentence_dict,
                                                                  attack_id=attack_id, attack_dict=attack_dict)
        if checks is not None:
            return checks
        # Get the sentence to insert by removing html markup
        sentence_to_insert = await self.web_svc.remove_html_markup_and_found(sentence_dict[0]['text'])
        sentence_to_insert = self.dao.truncate_str(sentence_to_insert, 800)
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

    async def update_attack_time(self, request, criteria=None):
        default_error, success = dict(error='Error updating technique times.'), REST_SUCCESS.copy()
        # Do initial report checks
        report, error = await self._report_pre_check(
            request, criteria, 'update-technique-times', [UID, 'current_status', 'start_date', 'end_date'], None)
        if error:
            return default_error
        # Check all request parameters
        start_date, end_date = criteria.get('start_date'), criteria.get('end_date')
        mapping_list = criteria.get('mapping_list', [])
        report_id, r_status = report[UID], report['current_status']
        r_start_date, r_end_date = self.to_datetime_obj(report['start_date']), self.to_datetime_obj(report['end_date'])
        if not start_date:
            return dict(error='Technique Start Date missing.', alert_user=1)
        if (not mapping_list) or (not isinstance(mapping_list, list)):
            return dict(error='No Confirmed Techniques selected.', alert_user=1)
        if r_status not in [ReportStatus.NEEDS_REVIEW.value, ReportStatus.IN_REVIEW.value]:
            return default_error
        # Do date-format and range checks
        start_dict = dict(field='start_date', value=start_date, is_lower=True)
        end_dict = dict(field='end_date', value=end_date, is_upper=True)
        update_data, checks = self._pre_date_checks([start_dict, end_dict], ['start_date'], success)
        if checks:
            return checks
        start_date_conv, end_date_conv = start_dict.get(DATETIME_OBJ), end_dict.get(DATETIME_OBJ)
        updates = []  # what database updates will be carried out
        for mapping in mapping_list:
            entries = await self.dao.get('report_sentence_hits', dict(uid=mapping))
            # Check if a suitable entry to update or update_data is not already subset of entry (no updates needed)
            if not (entries and (entries[0].get('report_uid') == report_id) and entries[0].get('confirmed')
                    and entries[0].get('active_hit')) or (update_data.items() <= entries[0].items()):
                continue
            # Check that if one date in the date range is given, it fits with previously-saved/other date in range
            current_start = self.to_datetime_obj(entries[0]['start_date'])
            current_end = self.to_datetime_obj(entries[0]['end_date'])
            inv_start = start_date_conv and (not end_date_conv) and current_end and \
                        (start_date_conv > current_end.replace(tzinfo=None))
            inv_end = end_date_conv and (not start_date_conv) and current_start and \
                      (end_date_conv < current_start.replace(tzinfo=None))
            if inv_start or inv_end:
                continue
            updates.append(await self.dao.update('report_sentence_hits', where=dict(uid=mapping),
                                                 data=update_data, return_sql=True))
        # If there are updates, check if the report start/end dates should be updated
        info = '%s of %s technique(s) updated.' % (len(updates), len(mapping_list))
        if len(updates) != len(mapping_list):
            info += ' This could be because of report status; unconfirmed technique(s) and/or existing start/end dates.'
        report_info, refresh_page = '', False
        if updates:
            r_update_data = dict()
            if start_date_conv and r_start_date and (start_date_conv < r_start_date.replace(tzinfo=None)):
                r_update_data.update(dict(start_date=start_date))
            if end_date_conv and r_end_date and (end_date_conv > r_end_date.replace(tzinfo=None)):
                r_update_data.update(dict(end_date=end_date))
            if r_update_data:
                updates.append(await self.dao.update('reports', where=dict(uid=report_id),
                                                     data=r_update_data, return_sql=True))
                report_info = ' Report start/end dates have also been updated.'
                refresh_page = True
            await self.dao.run_sql_list(sql_list=updates)
        current_info = success.pop('info', '')
        info += report_info + (('\n\n' + current_info) if current_info else '')
        success.update(dict(info=info, alert_user=1, refresh_page=refresh_page, updated_attacks=bool(updates)))
        return success

    def __refang(self, ioc_text):
        """Function to remove artifacts from common defangs."""
        if not ioc_text:
            return

        ioc_text = ioc_text.replace('\n', '').replace(' ', '')
        # Make some characters consistent
        replace_periods = '[%s]+' % re.escape(''.join(self.web_svc.PERIODS))
        ioc_text = re.sub(replace_periods, '.', ioc_text)
        # 2 x single quotes in the regex below adds the single quote to the character set; do a separate remove
        remove_quotes = '[%s]+' % re.escape(''.join(set(self.web_svc.QUOTES) - {"''"}))
        ioc_text = re.sub(remove_quotes, '', ioc_text)
        ioc_text = re.sub('(%s)+' % re.escape("''"), '', ioc_text)

        ioc_text = (ioc_text.replace(',', '.')
                    .replace('[dot]', '.').replace('(dot)', '.').replace('[.]', '.').replace('(.)', '.')
                    .replace('[at]', '@').replace('(at)', '@').replace('[@]', '@').replace('(@)', '@')
                    .replace('[:]', ':').replace('(:)', ':')
                    .replace('(', '').replace(')', '').replace('[', '').replace(']', ''))

        # Replacements to make at the beginning and end of the string
        replace_start = ['*'] + self.web_svc.BULLET_POINTS + self.web_svc.HYPHENS
        replace_end = ['.'] + self.web_svc.HYPHENS
        replace_start_pattern = '^[%s]+' % re.escape(''.join(replace_start))
        replace_end_pattern = '[%s]+$' % re.escape(''.join(replace_end))

        ioc_text = re.sub(replace_start_pattern, '', ioc_text)
        # Special case: not removing but replacing leading 'hxxp'
        if ioc_text.startswith('hxxp'):
            ioc_text = ioc_text.replace('hxxp', 'http', 1)
        ioc_text = re.sub(replace_end_pattern, '', ioc_text)

        return ioc_text

    @staticmethod
    def check_if_public_ip(ip_address, clean=False):
        """Function to check if an IP address is public. Returns (True/False/None (invalid), IP address)."""
        if not ip_address:
            return None, None
        address_obj = None
        cleaned_ip = ip_address
        # Special case for 'localhost', make the string compatible with the IPv4Address class
        if clean and ip_address == 'localhost':
            cleaned_ip = '127.0.0.1'
        to_check = [('.', IPv4Address, IPv4Interface), (None, IPv6Address, IPv6Interface)]

        # Further tidying up if this is an IP address
        for replace_delimiter, address_class, interface_class in to_check:
            if clean and replace_delimiter:
                slash_pos = ip_address.rfind('/')
                prefix = ip_address[:slash_pos] if slash_pos > 0 else ip_address
                suffix = ip_address[slash_pos:] if slash_pos > 0 else ''
                # Replace any non-word character with the delimiter; then remove any trailing/leading delimiters
                cleaned_prefix = re.sub('\\W+', replace_delimiter, prefix)
                cleaned_prefix = re.sub(re.escape(replace_delimiter) + '+$', '', cleaned_prefix)
                cleaned_prefix = re.sub('^' + re.escape(replace_delimiter) + '+', '', cleaned_prefix)
                cleaned_ip = cleaned_prefix + suffix

            # Attempt Address class before Interface class
            for obj_class in [address_class, interface_class]:
                try:
                    address_obj = obj_class(cleaned_ip)
                    break
                except Exception:
                    continue
            if address_obj:
                break

        if not address_obj:
            # Don't return cleaned-changes as it is not applicable
            return None, ip_address
        return (not (address_obj.is_link_local or address_obj.is_multicast or address_obj.is_private)), cleaned_ip

    async def suggest_and_save_ioc(self, request, criteria=None):
        """Function to suggest and save a sentence's indicator-of-compromise text."""
        suggested_ioc_resp = (await self.suggest_ioc(request, criteria=criteria)) or ''
        final_response = suggested_ioc_resp
        ioc_text = None
        if isinstance(suggested_ioc_resp, str):
            ioc_text = criteria['ioc_text'] = suggested_ioc_resp
            final_response = await self.update_ioc(request, criteria=criteria)
        if isinstance(final_response, dict) and final_response.get('success') and ioc_text:
            final_response['ioc_text'] = ioc_text
        return final_response

    async def suggest_ioc(self, request, criteria=None):
        """Function to predict a sentence as an indicator of compromise."""
        default_error = dict(error='Error predicting IoC.')
        sentence_data, report_id, error = await self.check_edit_sentence_permission(
            request, criteria, default_error, 'predict-ioc', strict=True)
        if error:
            return error
        text = sentence_data['text']
        if not text:
            return REST_IGNORED
        cleaned_ioc_text = self.__refang(text)
        is_public_ip, cleaned_ioc_text = self.check_if_public_ip(cleaned_ioc_text, clean=True)
        return cleaned_ioc_text

    async def update_ioc(self, request, criteria=None, adding=False, deleting=False):
        """Function to update a sentence as an indicator of compromise."""
        if adding and deleting:
            raise ValueError('Parameters for adding and deleting are both set to True.')
        default_error, success = dict(error='Error updating IoC.'), REST_SUCCESS.copy()
        sentence_data, report_id, error = await self.check_edit_sentence_permission(
            request, criteria, default_error, 'update-ioc', strict=True)
        if error:
            return error

        table = 'report_sentence_indicators_of_compromise'
        db_query = dict(report_id=report_id, sentence_id=sentence_data[UID])

        if deleting:
            await self.dao.delete(table, db_query)
            success.update(dict(info='The selected sentence is no longer flagged as an IoC.', alert_user=1))
            return success

        text = criteria.get('ioc_text', '').strip()
        existing = await self.dao.get(table, db_query)
        if (adding and existing) or (not text):  # prevent duplicates
            return default_error
        # Don't automatically clean IoC for the user
        is_public_ip, cleaned_ip = self.check_if_public_ip(text, clean=False)

        if is_public_ip is False:  # avoid `if not` because None means not an IP address
            error_msg = ('This appears to be a link-local, multicast, or private IP address. '
                         'This cannot be flagged as an IoC. (Contact us if this is incorrect!)')
            return dict(error=error_msg, alert_user=1)

        if existing and not adding:
            if existing[0]['refanged_sentence_text'] == text:
                return REST_IGNORED
            await self.dao.update(table, where=db_query, data=dict(refanged_sentence_text=text))
            success.update(dict(info='This sentence-IoC text has been updated.', alert_user=1))
        else:
            await self.dao.insert_generate_uid(table, dict(**db_query, refanged_sentence_text=text))
            success.update(dict(info='The selected sentence has been flagged as an IoC.', alert_user=1))
        return success

    async def _pre_add_reject_attack_checks(self, request, sen_id='', sentence_dict=None, attack_id='',
                                            attack_dict=None):
        """Function to check for adding or rejecting attacks, enough sentence and attack data has been given."""
        # Check there is sentence data to access
        try:
            _, _ = sentence_dict[0]['text'], sentence_dict[0]['found_status']
            report_id = sentence_dict[0]['report_uid']
        except (KeyError, IndexError):  # sentence error (SE) occurred
            return dict(error='Error. Please quote SE%s when contacting admin.' % sen_id, alert_user=1), None
        # Check there is attack data to access
        try:
            attack_dict[0]['name'], attack_dict[0]['tid']
        except (KeyError, IndexError):  # attack-info error (AE) occurred
            return dict(error='Error. Please quote AE%s when contacting admin.' % attack_id, alert_user=1), None
        # Check permissions
        report = await self.check_report_permission(request, report_id=report_id, action='add-reject-attack')
        # Check the report status is acceptable (return a report status error (RSE) if not)
        if not await self.check_report_status_multiple(report_id=report_id,
                                                       statuses=[ReportStatus.IN_REVIEW.value,
                                                                 ReportStatus.NEEDS_REVIEW.value]):
            return dict(error='Error. Please quote RSE%s when contacting admin.' % report_id, alert_user=1), None
        return None, report

    def _pre_date_checks(self, date_dict_list, mandatory_field_list, success_response):
        """Function to carry out checks when dealing with date fields. :return data-to-save, errors"""
        update_data, converted_dates, invalid_dates = dict(), dict(), []
        # If we need to check date ranges
        lower_bound_key, upper_bound_key = None, None
        for date_dict in date_dict_list:
            date_value, date_key = date_dict.get('value'), date_dict.get('field')
            is_lower, is_upper = date_dict.get('is_lower', False), date_dict.get('is_upper', False)
            lower_bound_key = date_key if is_lower else lower_bound_key
            upper_bound_key = date_key if is_upper else upper_bound_key
            try:
                # Have reasonable date values been given (not too historic/futuristic)?
                converted_dates[date_key] = self.check_input_date(date_value)
                # Update original dictionary for further use
                date_dict[DATETIME_OBJ] = converted_dates[date_key]
            except (TypeError, ValueError):
                if date_value:  # if not blank, store this to report back to user
                    invalid_dates.append(date_value)
                elif date_key not in mandatory_field_list:  # else if blank, we will blank the value in the database
                    update_data[date_key] = None
                continue
            update_data[date_key] = date_value  # else add acceptable value to dictionary to be updated with
        # Check a sensible ordering of dates have been provided if we are testing ranges
        if lower_bound_key and upper_bound_key:
            start_date_conv, end_date_conv = converted_dates.get(lower_bound_key), converted_dates.get(upper_bound_key)
            if (start_date_conv and end_date_conv) and (end_date_conv < start_date_conv):
                return None, dict(error='Incorrect ordering of dates provided.', alert_user=1)
        # Checks have passed but update success response over invalid dates
        if invalid_dates:
            msg = 'The following dates were ignored for being too far in the past/future, and/or being in an ' \
                  'incorrect format: ' + ', '.join(str(val) for val in invalid_dates)
            success_response.update(dict(info=msg, alert_user=1))
        return update_data, None

    async def check_report_permission(self, request, report_id='', action='unspecified'):
        """Function to check a request is permitted given an action involving a report ID."""
        # If there is no report ID, the user hasn't supplied something correctly
        if not report_id:
            raise web.HTTPBadRequest()
        # Obtain the report from the db
        report = await self.data_svc.get_report_by_id(report_id=report_id, add_expiry_bool=(not self.is_local))
        try:
            report[0][UID], report[0]['date_written_str']
        except (KeyError, IndexError):
            # No report exists or db record malformed
            raise web.HTTPBadRequest()
        # Run the checker
        if not self.is_local:
            await self.web_svc.action_allowed(request, action, context=dict(report=report[0]))
        # Checks have passed, return report for further use
        return report[0]

    async def check_edit_sentence_permission(self, request, criteria=None, default_error=None, action='unspecified',
                                             strict=False):
        """Function to check a request to edit a sentence is permitted. Returns sentence (ID or data), report ID, error.
        Strict mode: when False, allows matching image-IDs to be checked, else will strictly check sentences only."""
        default_error = default_error or dict(error='Error editing sentence.')
        try:
            # Check for malformed request parameters (KeyError) or criteria being None (TypeError)
            sen_id = criteria['sentence_id']
        except (KeyError, TypeError):
            return None, None, default_error
        report_id, sentence_data = None, None
        if strict:
            sentences = await self.dao.get('report_sentences', dict(uid=sen_id))
            try:
                sentence_data = sentences[0]
                report_id, _ = sentence_data['report_uid'], sentence_data['text']
            except (KeyError, TypeError):
                return None, None, default_error
        else:
            report_id = await self.data_svc.get_report_id_from_sentence_id(sentence_id=sen_id)
        # Use this report ID to check permissions, determine its status and if we can continue
        await self.check_report_permission(request, report_id=report_id, action=action)
        if not await self.check_report_status_multiple(
                report_id=report_id, statuses=[ReportStatus.IN_REVIEW.value, ReportStatus.NEEDS_REVIEW.value]):
            return None, None, default_error
        return (sentence_data, report_id, None) if strict else (sen_id, report_id, None)

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

    @staticmethod
    def to_datetime_obj(date_val, raise_error=False):
        """Function to convert a given date into a datetime object."""
        if isinstance(date_val, datetime):
            return date_val  # nothing to do if already converted
        try:
            return datetime.strptime(date_val, '%Y-%m-%d')
        except (TypeError, ValueError) as e:
            if raise_error:
                raise e
        return None

    def add_report_expiry(self, data=None, **date_kwargs):
        """Function to generate an expiry date from today."""
        if not self.is_local:
            # Prepare expiry date as str
            expiry_date = datetime.now() + timedelta(**date_kwargs)
            expiry_date_str = expiry_date.strftime('%Y-%m-%d %H:%M:%S')
            if data:
                data.update(dict(expires_on=expiry_date_str))
            return expiry_date_str

    def check_input_date(self, date_str):
        """Function to check given a date string, it is in an acceptable format and range to be saved."""
        # Convert the given date into a datetime object to be able to do comparisons
        # Expect to raise TypeError if date_str is not a string
        given_date = self.to_datetime_obj(date_str, raise_error=True)
        # Establish the min and max date ranges we want dates to fall in
        date_now = datetime.now()
        max_date = datetime(date_now.year + 5, month=date_now.month, day=date_now.day, tzinfo=date_now.tzinfo)
        min_date = datetime(1970, month=1, day=1, tzinfo=date_now.tzinfo)
        # Raise a ValueError if the given date is not in this range
        if not (min_date < given_date < max_date):
            raise ValueError('Date `%s` outside permitted range.' % date_str)
        return given_date
