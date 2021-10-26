import os

from threadcomponents.database.thread_sqlite3 import ThreadSQLite
from threadcomponents.service.rest_svc import ReportStatus, UID as UID_KEY
from unittest import IsolatedAsyncioTestCase
from uuid import UUID


# A test suite for checking our SQL-generating code
class TestDBSQL(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        """Any setting-up before all the test methods."""
        cls.db = ThreadSQLite(os.path.join('tests', 'threadtest.db'))
        schema_file = os.path.join('threadcomponents', 'conf', 'schema.sql')
        with open(schema_file) as schema_opened:
            cls.schema = schema_opened.read()

    async def asyncSetUp(self):
        """Any setting-up before each test method."""
        # Build the database (can't run in setUpClass() as this is an async method)
        await self.db.build(self.schema)

    async def asyncTearDown(self):
        """Any tidying-up after each test method."""
        pass

    async def test_insert(self):
        """Function to test INSERT queries are generated correctly."""
        # Test data to insert
        data = dict(title='my_report', url='report.url', current_status=ReportStatus.QUEUE.value, token=None)
        # Obtain the generated SQL
        generated = await self.db.insert('reports', data, return_sql=True)
        # The SQL we are expecting and the number of parameters we are expecting to be returned separately to the SQL
        expected = 'INSERT INTO reports (title, url, current_status, token) VALUES (?, ?, ?, NULL)'
        expected_params_len = 3
        # Test expectations are correct
        self.assertEqual(expected, generated[0])
        self.assertEqual(expected_params_len, len(generated[1]))

    async def test_insert_with_uid(self):
        """Function to test INSERT queries with generated UIDs are generated correctly."""
        # Test data to insert
        data = dict(title='my_report2', url='report2.url', current_status=ReportStatus.QUEUE.value, token=None)
        # Obtain the generated SQL
        generated = await self.db.insert_generate_uid('reports', data, return_sql=True)
        # We are now expecting 4 parameters to be returned (as the UID has been generated)
        expected_params_len = 4
        # Test expectation is correct
        self.assertEqual(expected_params_len, len(generated[1]))
        # Test valid UUID has been attached to the data; raises ValueError if invalid UUID
        self.assertTrue(data[UID_KEY] in generated[1])
        UUID(data[UID_KEY])
