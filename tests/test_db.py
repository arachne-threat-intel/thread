import os
import sqlite3

from tests.misc import delete_db_file, SCHEMA_FILE
from threadcomponents.constants import UID as UID_KEY
from threadcomponents.enums import ReportStatus
from threadcomponents.database.thread_sqlite3 import ThreadSQLite
from unittest import IsolatedAsyncioTestCase
from uuid import UUID


class TestDBSQL(IsolatedAsyncioTestCase):
    """A test suite for checking our SQL-generating code."""

    DB_TEST_FILE = os.path.join("tests", "threadtestsql.db")

    @classmethod
    def setUpClass(cls):
        """Any setting-up before all the test methods."""
        cls.db = ThreadSQLite(cls.DB_TEST_FILE)
        with open(SCHEMA_FILE) as schema_opened:
            cls.schema = schema_opened.read()
        cls.backup_schema = cls.db.generate_copied_tables(cls.schema)

    @classmethod
    def tearDownClass(cls):
        """Any tidying-up after all the test methods."""
        # Delete the database so a new DB file is used in next test-run
        delete_db_file(cls.DB_TEST_FILE)

    async def asyncSetUp(self):
        """Any setting-up before each test method."""
        # Build the database (can't run in setUpClass() as this is an async method)
        await self.db.build(self.schema)
        await self.db.build(self.backup_schema, is_partial=True)
        await self.db.initialise_column_names()

    async def check_data_appeared_in_table(
        self, table, method_name="unspecified", found_check=None, expect_found=True, fail_msg="", **kwargs
    ):
        """
        Function to check whether or not data is found in a table.
        :param table: The table to check whether data has appeared.
        :param method_name: The test method calling this method (for logging purposes).
        :param found_check: The method to determine given a result from the database, if data is found.
        :param expect_found: If we are checking data is found in the table or not.
        :param fail_msg: The message to report on test failure.
        **kwargs should match the kwargs of ThreadDB.get()
        """
        # If we don't have a way to do the check, fail this test
        if not callable(found_check):
            message = "%s: Not provided with method to check data is%s in table." % (
                method_name,
                "" if expect_found else " not",
            )
            self.fail(message)
        # Prefix failure message with test-method calling this method
        fail_msg = "%s: %s" % (method_name, fail_msg if fail_msg else "expected " + str(expect_found))
        # Obtain the sentences for the report and initialise a 'found' flag
        results = await self.db.get(table, **kwargs)
        found = False
        # Check through the returned results to see if there is a match
        for returned in results:
            if found_check(returned):
                found = True
                break
        # Check our expectations on whether the data is found or not
        self.assertEqual(expect_found, found, msg=fail_msg)

    async def test_build(self):
        """Function to test the db built tables successfully."""
        # SQLite-specific query to obtain table names
        sql = "SELECT name FROM %s WHERE type = 'table';"
        try:
            results = await self.db.raw_select(sql % "sqlite_schema", single_col=True)
        except sqlite3.OperationalError:
            # If the above fails, try the old name for the table for the lookup
            try:
                results = await self.db.raw_select(sql % "sqlite_master", single_col=True)
            except sqlite3.OperationalError:
                # If this still fails, fail the test
                self.fail("Unable to obtain table names from schema; raw_select() may be at fault.")
        # The list of tables we are expecting to have been created
        expected = [
            "attack_uids",
            "reports",
            "report_sentences",
            "true_positives",
            "true_negatives",
            "false_positives",
            "false_negatives",
            "regex_patterns",
            "similar_words",
            "report_sentence_hits",
            "original_html",
            "report_sentences_initial",
            "report_sentence_hits_initial",
            "original_html_initial",
            "categories",
            "categories_auto_add",
            "report_categories",
            "keywords",
            "report_keywords",
            "report_countries",
            "report_all_assoc",
            "report_sentence_indicators_of_compromise",
            "report_regions",
            "report_sentence_queue_progress",
        ]
        # Check the expectations against the results
        for table in results:
            self.assertTrue(table in expected, msg="Table %s was created but not expected." % table)
        for table in expected:
            self.assertTrue(table in results, msg="Table %s was expected but not created." % table)

    async def test_insert(self):
        """Function to test INSERT statements are generated correctly."""
        # Test data to insert
        data = dict(title="my_report", url="report.url", current_status=ReportStatus.QUEUE.value, token=None)
        # Obtain the generated SQL
        generated = await self.db.insert("reports", data, return_sql=True)
        # The SQL we are expecting and the number of parameters we are expecting to be returned separately to the SQL
        expected = "INSERT INTO reports (title, url, current_status, token) VALUES (?, ?, ?, NULL)"
        expected_params_len = 3
        # Test expectations are correct
        self.assertEqual(expected, generated[0], msg="SQL statement not generated as expected.")
        self.assertEqual(expected_params_len, len(generated[1]), msg="SQL parameters not generated as expected.")

    async def test_insert_with_uid(self):
        """Function to test INSERT statements with generated UIDs are generated correctly."""
        # Test data to insert
        data = dict(title="my_report2", url="report2.url", current_status=ReportStatus.QUEUE.value, token=None)
        # Obtain the generated SQL
        generated = await self.db.insert_generate_uid("reports", data, return_sql=True)
        # We are now expecting 4 parameters to be returned (as the UID has been generated)
        expected_params_len = 4
        # Test expectation is correct
        self.assertEqual(expected_params_len, len(generated[1]), msg="SQL parameters not generated as expected.")
        # Test valid UUID has been attached to the data; raises ValueError if invalid UUID
        self.assertTrue(data[UID_KEY] in generated[1], msg="UID not passed to DB parameters.")
        UUID(data[UID_KEY])

    async def test_insert_then_update(self):
        """Function to test inserted data can be updated successfully."""

        # A small function to check given a report-record, that it matches with an initial title defined in this method
        def pre_update_found(r):
            return r.get("title") == initial_title and r.get(UID_KEY) == report_id

        # A small function to check given a report-record, that it matches with an updated title defined in this method
        def post_update_found(r):
            return r.get("title") == new_title and r.get(UID_KEY) == report_id

        # The test change we will be doing
        initial_title = "There and Back Again"
        new_title = "A Developer's Tale"
        # Insert the report data
        report = dict(title=initial_title, url="localhost.or.shire", current_status=ReportStatus.QUEUE.value)
        report_id = await self.db.insert_generate_uid("reports", report)
        # The kwargs for check_data_appeared_in_table() which are the same for all checks
        checking_args = dict(method_name="test_insert_then_update", equal=dict(uid=report_id))
        # Confirm the report got inserted
        await self.check_data_appeared_in_table(
            "reports",
            expect_found=True,
            found_check=pre_update_found,
            fail_msg="inserted data not found",
            **checking_args,
        )
        # Confirm the new_title does not appear as a report title yet
        rep_results = await self.db.get("reports", equal=dict(title=new_title))
        if rep_results:
            self.skipTest("Could not test updating table as tested updates already exist pre-update.")
        # Update the report with the new title
        await self.db.update("reports", where=dict(uid=report_id), data=dict(title=new_title))
        # Confirm old report title is not found but new report title is found
        await self.check_data_appeared_in_table(
            "reports",
            expect_found=False,
            found_check=pre_update_found,
            fail_msg="initial data found after update",
            **checking_args,
        )
        await self.check_data_appeared_in_table(
            "reports",
            expect_found=True,
            found_check=post_update_found,
            fail_msg="updated data not found",
            **checking_args,
        )

    async def test_insert_then_delete(self):
        """Function to test inserted data can be deleted successfully."""

        # A small function to check given a report-record, that it matches with a report ID defined in this method
        def report_found(r):
            return r.get(UID_KEY) == report_id

        # Insert the report data
        report = dict(title="Don't Stop Moving", url="funky.funky.beat", current_status=ReportStatus.QUEUE.value)
        report_id = await self.db.insert_generate_uid("reports", report)
        # The kwargs for check_data_appeared_in_table() which are the same for all checks
        checking_args = dict(method_name="test_insert_then_delete", equal=dict(uid=report_id))
        # Confirm the report got inserted
        await self.check_data_appeared_in_table(
            "reports", expect_found=True, found_check=report_found, fail_msg="inserted data not found", **checking_args
        )
        # Carry out the delete
        await self.db.delete("reports", dict(uid=report_id))
        # Confirm the report got deleted
        await self.check_data_appeared_in_table(
            "reports", expect_found=False, found_check=report_found, fail_msg="deleted data was found", **checking_args
        )

    async def test_select_with_no_args(self):
        """Function to test behaviour of SELECT statements with no clauses specified."""
        # Both calls should work without raising an error
        await self.db.get("reports")
        await self.db.get("reports", equal=None, not_equal=None, order_by_asc=None, order_by_desc=None)

    async def test_insert_with_backup(self):
        """Function to test inserting data with a backup works as expected."""

        # A small function to check given a sentence-record, that it matches with the sentence defined in this method
        def sentence_found(s):
            return s.get("text") == sentence and s.get(UID_KEY) == sen_id

        # Insert a report
        report = dict(
            title="Return of the Phyrexian Obliterator", url="trampled.oops", current_status=ReportStatus.QUEUE.value
        )
        report_id = await self.db.insert_generate_uid("reports", report)
        # Confirm we have no sentences for this report yet
        sen_results = await self.db.get("report_sentences", equal=dict(report_uid=report_id))
        sen_results_backup = await self.db.get("report_sentences_initial", equal=dict(report_uid=report_id))
        if sen_results or sen_results_backup:
            self.skipTest("Could not test storing new data in backup tables as new data already exists.")

        # Reports are not backed-up, so let's test a report-sentence which is backed up
        sentence = "Behold blessed perfection."
        data = dict(
            report_uid=report_id,
            text=sentence,
            html="<p>%s</p>" % sentence,
            sen_index=0,
            found_status=self.db.val_as_false,
        )
        sen_id = await self.db.insert_with_backup("report_sentences", data)
        # The kwargs for check_data_appeared_in_table() which are the same for all checks
        checking_args = dict(
            method_name="test_insert_with_backup", found_check=sentence_found, equal=dict(report_uid=report_id)
        )
        # After method is called, let's test both the report_sentences table and its back-up table have this sentence
        for table in ["report_sentences", "report_sentences_initial"]:
            error_msg = "data missing in table %s after being inserted" % table
            await self.check_data_appeared_in_table(table, expect_found=True, fail_msg=error_msg, **checking_args)
        # Confirm deleting sentence in report_sentences does not delete the backup
        await self.db.delete("report_sentences", dict(text=sentence))
        await self.check_data_appeared_in_table(
            "report_sentences",
            expect_found=False,
            fail_msg="data deleted in report_sentences but found",
            **checking_args,
        )
        await self.check_data_appeared_in_table(
            "report_sentences_initial",
            expect_found=True,
            fail_msg="data deleted in report_sentences and missing in report_sentences_initial",
            **checking_args,
        )

    async def test_insert_with_no_data(self):
        """Function to test behaviour of INSERT statements with no values specified."""
        # TypeError where data to be inserted is None (not a dictionary)
        with self.assertRaises(TypeError, msg="Expected TypeError over `None` value for report."):
            await self.db.insert("reports", None)
        # ValueError where data to be inserted is (a dictionary but) empty
        with self.assertRaises(ValueError, msg="Expected ValueError over empty value for report."):
            await self.db.insert("reports", dict())

    async def test_update_with_no_data(self):
        """Function to test behaviour of UPDATE statements with no SET clause specified."""
        # TypeError where data to be set is None (not a dictionary)
        with self.assertRaises(TypeError, msg="Expected TypeError over `None` value for `data` parameter."):
            await self.db.update("reports", where=dict(title="Nothing is True"), data=None)
        # ValueError where data to be set is (a dictionary but) empty
        with self.assertRaises(ValueError, msg="Expected ValueError over empty value for `data` parameter."):
            await self.db.update("reports", where=dict(title="Everything is Permitted; Except This"), data=dict())

    async def test_update_with_no_where(self):
        """Function to test behaviour of UPDATE statements with no WHERE clause specified."""
        # TypeError where WHERE-clause data is None (not a dictionary)
        with self.assertRaises(TypeError, msg="Expected TypeError over `None` value for `where` parameter."):
            await self.db.update("reports", where=None, data=dict(title="One title"))
        # ValueError where WHERE-clause data is (a dictionary but) empty
        with self.assertRaises(ValueError, msg="Expected ValueError over empty value for `where` parameter."):
            await self.db.update("reports", where=dict(), data=dict(title="To Rule Them All"))

    async def test_delete_with_no_where(self):
        """Function to test behaviour of DELETE statements with no WHERE clause specified."""
        # TypeError where WHERE-clause data is None (not a dictionary)
        with self.assertRaises(TypeError, msg="Expected TypeError over `None` value for report."):
            await self.db.delete("reports", None)
        # ValueError where WHERE-clause data is (a dictionary but) empty
        with self.assertRaises(ValueError, msg="Expected ValueError over empty value for report."):
            await self.db.delete("reports", dict())
