# NOTICE: As required by the Apache License v2.0, this notice is to state this file has been modified by Arachne Digital
# This file has been moved into a different directory
# To see its full history, please use `git log --follow <filename>` to view previous commits and additional contributors

import asyncio
import logging
import pandas as pd
import re

from contextlib import suppress
from functools import partial
from htmldate import find_date
from io import StringIO

from threadcomponents.constants import REST_SUCCESS, UID, URL, TITLE
from threadcomponents.enums import ReportStatus
from threadcomponents.helpers.date import check_input_date

from threadcomponents.managers.ioc_manager import IoCManager
from threadcomponents.managers.mapping_manager import MappingManager
from threadcomponents.managers.sentence_manager import SentenceManager
from threadcomponents.managers.report_manager import ReportManager

PUBLIC = "public"

# The minimum amount of tecniques for a report to not be discarded
REPORT_TECHNIQUES_MINIMUM = 5


class RestService:
    def __init__(
        self,
        web_svc,
        reg_svc,
        data_svc,
        token_svc,
        ml_svc,
        attack_data_svc,
        dao,
        queue_limit=None,
        max_tasks=1,
        sentence_limit=None,
    ):
        self.MAX_TASKS = max_tasks
        self.QUEUE_LIMIT = queue_limit
        self.SENTENCE_LIMIT = sentence_limit
        self.dao = dao
        self.data_svc = data_svc
        self.web_svc = web_svc
        self.token_svc = token_svc
        self.attack_data_svc = attack_data_svc
        self.ml_svc = ml_svc
        self.reg_svc = reg_svc
        self.is_local = self.web_svc.is_local
        self.queue_map = dict()  # map each user to their own queue

        try:
            self.queue = asyncio.Queue()  # task queue
        except RuntimeError as e:  # a RuntimeError may occur if there is no event loop
            logging.error("Encountered error %s; attempting to resolve by setting new event loop" % str(e))
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.queue = asyncio.Queue()

        self.current_tasks = []  # tasks that are currently being executed
        # A dictionary to keep track of report statuses we have seen
        self.seen_report_status = dict()

        manager_args = (
            self.web_svc,
            self.data_svc,
            self.dao,
            self.seen_report_status,
        )

        self.report_manager = ReportManager(*manager_args)
        self.sentence_manager = SentenceManager(*manager_args)
        self.mapping_manager = MappingManager(*manager_args)
        self.ioc_manager = IoCManager(*manager_args)

    async def fetch_and_update_attack_data(self):
        """Function to fetch and update the attack data."""
        # The output of the attack-data-updates from data_svc
        attack_data = self.attack_data_svc.fetch_flattened_attack_data()
        await self.data_svc.update_db_with_flattened_attack_data(attack_data=attack_data)
        self.attack_data_svc.update_json_tech_with_flattened_attack_data(attack_data=attack_data)

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
        queue = self.get_queue_for_user(token=report.get("token"))
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
        reports = await self.dao.get(
            "reports", dict(error=self.dao.db_false_val, current_status=ReportStatus.QUEUE.value)
        )
        for report in reports:
            # Sentences from this report may have previously populated other db tables
            # Being selected from the queue will begin analysis again so delete previous progress
            report_id = report[UID]
            await self.dao.delete("report_sentences", dict(report_uid=report_id))
            await self.dao.delete("report_sentence_queue_progress", dict(report_uid=report_id))
            await self.dao.delete("report_sentence_hits", dict(report_uid=report_id))
            await self.dao.delete("original_html", dict(report_uid=report_id))
            # Get the relevant queue for this user
            queue = self.get_queue_for_user(token=report.get("token"))
            # Add to the queue
            await self.queue.put(report)
            queue.append(report[URL])

    async def set_status(self, *args, **kwargs):
        return await self.report_manager.set_status(*args, **kwargs)

    async def delete_report(self, *args, **kwargs):
        return await self.report_manager.delete_report(*args, **kwargs)

    async def remove_sentence(self, *args, **kwargs):
        return await self.sentence_manager.remove_sentence(*args, **kwargs)

    async def set_report_categories(self, *args, **kwargs):
        return await self.report_manager.set_report_categories(*args, **kwargs)

    async def set_report_keywords(self, *args, **kwargs):
        return await self.report_manager.set_report_keywords(*args, **kwargs)

    async def update_report_dates(self, *args, **kwargs):
        return await self.report_manager.update_report_dates(*args, **kwargs)

    async def rollback_report(self, *args, **kwargs):
        return await self.report_manager.rollback_report(*args, **kwargs)

    async def sentence_context(self, *args, **kwargs):
        return await self.sentence_manager.sentence_context(*args, **kwargs)

    async def confirmed_attacks(self, *args, **kwargs):
        return await self.sentence_manager.confirmed_attacks(*args, **kwargs)

    async def insert_report(self, request, criteria=None):
        # Check for errors whilst updating request data with token (if applicable)
        error = await self.pre_insert_add_token(request, request_data=criteria, key="title")
        if error:
            return error

        # For both the title and url...
        for column in ["title", URL]:
            # Obtain the value from the request; return an error if an argument is missing
            value = str(criteria.get(column, "")).strip()
            if not value:
                return dict(error="Missing value for %s." % column, alert_user=1)

            # Place title and URL in list to be compatible with _insert_batch_reports()
            criteria[column] = [value]

        if criteria.get("automatically_generated"):
            criteria["automatically_generated"] = [criteria["automatically_generated"]]
        else:
            criteria["automatically_generated"] = [None]

        return await self._insert_batch_reports(request, criteria, 1, token=criteria.get("token"))

    async def insert_csv(self, request, criteria=None):
        # Check for errors whilst updating request data with token (if applicable)
        error = await self.pre_insert_add_token(request, request_data=criteria, key="file")
        if error:
            return error

        try:
            df = self.verify_csv(criteria["file"])
        except (TypeError, ValueError) as e:  # Any errors occurring from the csv-checks
            return dict(error=str(e), alert_user=1)

        return await self._insert_batch_reports(request, df, df.shape[0], token=criteria.get("token"))

    async def pre_insert_add_token(self, request, request_data=None, key=None):
        """Function to check sent request data before inserting reports and return an error if there was an issue."""
        try:
            # Check for malformed request parameters (KeyError) or criteria being None (TypeError)
            request_data[key]
        except (KeyError, TypeError):
            return dict(error="Error inserting report(s).")

        # If running locally, there are no further checks but ensure the token is None (to avoid mix of ''s and Nones)
        if self.is_local:
            request_data.update(token=None)
            return

        # If automatically generated, check associated-data is valid
        if request_data.get("automatically_generated"):
            if not await self.web_svc.auto_gen_data_is_valid(request, request_data):
                return dict(error="Report(s) not submitted. Invalid data for automatically-generated submission.")
        # If not running locally, check if the user is requesting a private submission
        elif request_data.get("private"):
            # Obtain the token to make this submission private
            username, token = await self.web_svc.get_current_arachne_user(request)
            # Update report-data with token or alert user if this was not possible
            if token:
                request_data.update(token=token)
            else:
                return dict(
                    error="Report(s) not submitted. Please ensure you are logged into Arachne for this "
                    "to be private. If this error is persistent, please contact us.",
                    alert_user=1,
                )
        # If public (no token), blank data with None (to avoid mix of empty strings and Nones)
        else:
            request_data.update(token=None)

    async def _insert_batch_reports(self, request, batch, row_count, token=None):
        # Possible responses to the request
        default_error, success = dict(error="Error inserting report(s)."), REST_SUCCESS.copy()
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
                title, url = batch["title"][row].strip(), batch[URL][row].strip()
                automatically_generated = (
                    batch["automatically_generated"][row] if "automatically_generated" in batch.keys() else None
                )
            # Check for malformed request parameters; AttributeError thrown if not strings
            except (AttributeError, KeyError):
                return default_error

            try:
                # Enforce http on urls that do not begin with http(s)
                prefix_check = re.match("^https?://", url, re.IGNORECASE)
                url = "http://" + url if prefix_check is None else url

                # Drop fragments
                if "#" in url:
                    url = url[: url.index("#")]
                await self.web_svc.verify_url(request, url=url)

            # Raised if verify_url() fails
            except (SystemError, ValueError) as ve:
                error_prefix = "URL checks failed:" if isinstance(ve, ValueError) else "System-error:"
                return dict(error=f"{error_prefix} {ve}", alert_user=1)

            # Ensure the report has a unique title
            title = await self.data_svc.get_unique_title(title)
            # Set up a temporary dictionary to represent db object
            temp_dict = dict(
                title=title,
                url=url,
                current_status=ReportStatus.QUEUE.value,
                automatically_generated=automatically_generated,
                token=token,
            )

            self.report_manager.add_report_expiry(data=temp_dict, weeks=1)
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
                temp_dict[UID] = await self.dao.insert_generate_uid("reports", temp_dict)
                # Finally, update queue and check queue when batch is finished
                await self.queue.put(temp_dict)
                queue.append(url)

        if limit_exceeded or duplicate_urls or malformed_urls or long_titles or long_urls:
            total_skipped = sum([limit_exceeded, duplicate_urls, malformed_urls, long_titles, long_urls])
            message = (
                "%s of %s " % (total_skipped, row_count)
                + "report(s) not added to the queue."
                + "\n- %s exceeded queue limit." % limit_exceeded
                + "\n- %s already in the queue/duplicate URL(s)." % duplicate_urls
                + "\n- %s malformed URL(s)." % malformed_urls
                + "\n- %s report-title(s) exceeded 200-character limit." % long_titles
                + "\n- %s URL(s) exceeded 500-character limit." % long_urls
            )
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
            raise TypeError("Could not parse file")

        # Next, check if only the columns 'title' and 'url' exist in the df
        title = "title"
        columns = list(df.columns)
        columns_error = "Two columns have not been specified ('Title','URL')"

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
            if values.map(lambda x: not isinstance(x, str)).any() or values.map(lambda x: len(x) == 0).any():
                raise ValueError("Column `%s` in CSV is missing text in at least one row" % col)

        # All previous checks passed: return the new df
        return new_df

    async def check_queue(self):
        """
        description: executes as concurrent job, manages taking jobs off the queue and executing them.
        input: nil
        output: nil
        """
        logging.info("CHECKING QUEUE")
        self.clean_current_tasks()

        while self.queue.qsize() > 0:  # while there are still tasks to do...
            logging.info("QUEUE SIZE: " + str(self.queue.qsize()))
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
                logging.error(f"Report analysis failed: {e}")
                await self.error_report(criteria, log_error=e)
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

    async def error_report(self, report, log_error=None):
        """Function to error a given report."""
        report_id = report[UID]
        await self.dao.update("reports", where=dict(uid=report_id), data=dict(error=self.dao.db_true_val))
        self.remove_report_from_queue_map(report)
        await self.remove_report_if_automatically_generated(report_id)

        if log_error:
            await self.web_svc.on_report_error(None, log_error)

    async def start_analysis(self, criteria=None):
        report_id = criteria[UID]
        logging.info("Beginning analysis for " + report_id)

        original_html, newspaper_article = await self.web_svc.map_all_html(
            criteria[URL], sentence_limit=self.SENTENCE_LIMIT
        )
        if original_html is None and newspaper_article is None:
            logging.error("Skipping report; could not download url " + criteria[URL])
            await self.error_report(criteria)
            return

        html_data = newspaper_article.text.replace("\n", "<br>")
        article = dict(title=criteria[TITLE], html_text=html_data)
        # Obtain the article date if possible
        article_date = None
        with suppress(ValueError):
            article_date = find_date(criteria[URL])
        # Check any obtained date is a sensible value to store in the database
        with suppress(TypeError, ValueError):
            check_input_date(article_date)

        # Here we build the sentence dictionary
        html_sentences = self.token_svc.tokenize_sentence(article["html_text"], sentence_limit=self.SENTENCE_LIMIT)
        if not html_sentences:
            logging.error("Skipping report; could not retrieve sentences from url " + criteria[URL])
            await self.error_report(criteria)
            return

        html_sentences = html_sentences[: self.SENTENCE_LIMIT]
        await self.dao.insert_generate_uid(
            "report_sentence_queue_progress", dict(report_uid=report_id, sentence_count=len(html_sentences))
        )

        rebuilt, model_dict = await self.ml_svc.build_pickle_file(
            self.attack_data_svc.list_of_techs, self.attack_data_svc.json_tech
        )

        ml_analyzed_html = await self.ml_svc.analyze_html(
            self.attack_data_svc.list_of_techs, model_dict, html_sentences
        )
        regex_patterns = await self.dao.get("regex_patterns")
        reg_analyzed_html = self.reg_svc.analyze_html(regex_patterns, html_sentences)

        # Merge ML and Reg hits
        analyzed_html = self.combine_ml_and_reg(ml_analyzed_html, reg_analyzed_html)

        for s_idx, sentence in enumerate(analyzed_html):
            sentence["text"] = self.dao.truncate_str(sentence["text"], 800)
            sentence["html"] = self.dao.truncate_str(sentence["html"], 900)
            if sentence["ml_techniques_found"]:
                await self.report_manager.save_ml_techniques(report_id, sentence, s_idx, tech_start_date=article_date)
            elif sentence["reg_techniques_found"]:
                await self.report_manager.save_reg_techniques(report_id, sentence, s_idx, tech_start_date=article_date)
            else:
                data = dict(
                    report_uid=report_id,
                    text=sentence["text"],
                    html=sentence["html"],
                    sen_index=s_idx,
                    found_status=self.dao.db_false_val,
                )
                await self.dao.insert_with_backup("report_sentences", data)

        for e_idx, element in enumerate(original_html):
            element["text"] = self.dao.truncate_str(element["text"], 800)
            html_element = dict(
                report_uid=report_id,
                text=element["text"],
                tag=element["tag"],
                elem_index=e_idx,
                found_status=self.dao.db_false_val,
            )
            await self.dao.insert_with_backup("original_html", html_element)

        # The report is about to be moved out of the queue
        update_data = dict(current_status=ReportStatus.NEEDS_REVIEW.value)
        # Save the article-date if we have one
        if article_date:
            update_data.update(dict(date_written=article_date))

        # Add expiry date (now + 1 week)
        self.report_manager.add_report_expiry(data=update_data, weeks=1)

        # Update card to reflect the end of queue
        await self.dao.update("reports", where=dict(uid=report_id), data=update_data)
        # Update the relevant queue for this user
        self.remove_report_from_queue_map(criteria)
        logging.info("Finished analysing report " + report_id)

        # DB tidy-up including removing report if low quality
        await self.dao.delete("report_sentence_queue_progress", dict(report_uid=report_id))
        await self.remove_report_if_low_quality(report_id)

    @staticmethod
    def combine_ml_and_reg(ml_analyzed_html, reg_analyzed_html):
        analyzed_html = []
        index = 0
        for sentence in ml_analyzed_html:
            sentence["reg_techniques_found"] = reg_analyzed_html[index]["reg_techniques_found"]
            analyzed_html.append(sentence)
            index += 1
        return analyzed_html

    async def remove_report_if_low_quality(self, report_id):
        """Function that removes report if its quality is low."""
        reports_found = await self.data_svc.get_report_by_id_or_title(by_id=True, report=report_id)
        if len(reports_found) != 1:
            return

        report = reports_found[0]
        if not report["automatically_generated"]:
            return

        unique_techniques_count = await self.data_svc.get_report_unique_techniques_count(report_id=report_id)

        # Remove report if amount of unique techniques found doesn't reach the minimum
        if unique_techniques_count < REPORT_TECHNIQUES_MINIMUM:
            await self.data_svc.remove_report_by_id(report_id=report_id)
            logging.info("Deleted report with " + str(unique_techniques_count) + " technique(s) found: " + report[URL])
            return

        logging.info(str(unique_techniques_count) + " technique(s) found for report " + report_id)

    async def remove_report_if_automatically_generated(self, report_id):
        """Function that removes a report if it has been automatically generated."""
        reports_found = await self.data_svc.get_report_by_id_or_title(by_id=True, report=report_id)
        if len(reports_found) != 1:
            return

        report = reports_found[0]
        if not report["automatically_generated"]:
            return

        await self.data_svc.remove_report_by_id(report_id=report_id)
        logging.info("Deleted skipped report: " + report[URL])

    async def add_attack(self, *args, **kwargs):
        """Function to add a mapping on a sentence."""
        return await self.mapping_manager.add_attack(*args, **kwargs)

    async def ignore_attack(self, *args, **kwargs):
        """Function to ignore a mapping on a sentence."""
        return await self.mapping_manager.ignore_attack(*args, **kwargs)

    async def reject_attack(self, *args, **kwargs):
        """Function to reject a mapping on a sentence."""
        return await self.mapping_manager.reject_attack(*args, **kwargs)

    async def update_attack_time(self, *args, **kwargs):
        return await self.mapping_manager.update_attack_time(*args, **kwargs)

    async def suggest_and_save_ioc(self, *args, **kwargs):
        """Function to suggest and save a sentence's indicator-of-compromise text."""
        return await self.ioc_manager.suggest_and_save_ioc(*args, **kwargs)

    async def suggest_ioc(self, *args, **kwargs):
        """Function to predict a sentence as an indicator of compromise."""
        return await self.ioc_manager.suggest_ioc(*args, **kwargs)

    async def update_ioc(self, *args, **kwargs):
        """Function to update a sentence as an indicator of compromise."""
        return await self.ioc_manager.update_ioc(*args, **kwargs)
