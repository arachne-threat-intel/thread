import aiohttp_jinja2
import asyncio
import jinja2
import os
import random
import sqlite3

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase
from contextlib import suppress
from tests.misc import delete_db_file
from threadcomponents.database.dao import Dao
from threadcomponents.database.thread_sqlite3 import ThreadSQLite
from threadcomponents.handlers.web_api import WebAPI
from threadcomponents.service.data_svc import DataService
from threadcomponents.service.ml_svc import MLService
from threadcomponents.service.reg_svc import RegService
from threadcomponents.service.rest_svc import ReportStatus, RestService, UID as UID_KEY
from threadcomponents.service.web_svc import WebService
from unittest.mock import MagicMock, patch
from uuid import uuid4
from urllib.parse import quote


class TestReports(AioHTTPTestCase):
    """A test suite for checking report actions."""
    DB_TEST_FILE = os.path.join('tests', 'threadtestreport.db')

    @classmethod
    def setUpClass(cls):
        """Any setting-up before all the test methods."""
        cls.db = ThreadSQLite(cls.DB_TEST_FILE)
        schema_file = os.path.join('threadcomponents', 'conf', 'schema.sql')
        with open(schema_file) as schema_opened:
            cls.schema = schema_opened.read()
        cls.backup_schema = cls.db.generate_copied_tables(cls.schema)
        cls.dao = Dao(engine=cls.db)
        cls.web_svc = WebService()
        cls.reg_svc = RegService(dao=cls.dao)
        cls.data_svc = DataService(dao=cls.dao, web_svc=cls.web_svc)
        cls.ml_svc = MLService(web_svc=cls.web_svc, dao=cls.dao)
        cls.rest_svc = RestService(cls.web_svc, cls.reg_svc, cls.data_svc, cls.ml_svc, cls.dao)
        services = dict(dao=cls.dao, data_svc=cls.data_svc, ml_svc=cls.ml_svc, reg_svc=cls.reg_svc, web_svc=cls.web_svc,
                        rest_svc=cls.rest_svc)
        cls.web_api = WebAPI(services=services)
        # Duplicate resources so we can test the queue limit without causing limit-exceeding test failures elsewhere
        cls.rest_svc_with_limit = RestService(cls.web_svc, cls.reg_svc, cls.data_svc, cls.ml_svc, cls.dao,
                                              queue_limit=random.randint(1, 20))
        services.update(rest_svc=cls.rest_svc_with_limit)
        cls.web_api_with_limit = WebAPI(services=services)
        # Some test-attack data
        cls.attacks = dict(d99999='Drain', f12345='Fire', f32451='Firaga')

    @classmethod
    def tearDownClass(cls):
        """Any tidying-up after all the test methods."""
        # Delete the database so a new DB file is used in next test-run
        delete_db_file(cls.DB_TEST_FILE)

    async def setUpAsync(self):
        """Any setting-up before each test method."""
        # Build the database (can't run in setUpClass() as this is an async method)
        await self.db.build(self.schema)
        await self.db.build(self.backup_schema)
        # Insert some attack data
        a1_name, a2_name, a3_name = self.attacks.get('f12345'), self.attacks.get('f32451'), self.attacks.get('d99999')
        attack_1 = dict(uid='f12345', description='Fire spell costing 4MP', tid='T1562', name=a1_name)
        attack_2 = dict(uid='f32451', description='Stronger Fire spell costing 16MP', tid='T1562.004', name=a2_name)
        attack_3 = dict(uid='d99999', description='Absorbs HP', tid='T1029', name=a3_name)
        for attack in [attack_1, attack_2, attack_3]:
            # Ignoring Integrity Error in case other test case already has inserted this data (causing duplicate UIDs)
            with suppress(sqlite3.IntegrityError):
                await self.db.insert('attack_uids', attack)
        # Carry out pre-launch tasks except for prepare_queue(): replace the call of this to return (and do) nothing
        # We don't want multiple prepare_queue() calls so the queue does not accumulate between tests
        with patch.object(RestService, 'prepare_queue', return_value=None):
            await self.web_api.pre_launch_init()
            await self.web_api_with_limit.pre_launch_init()
        await super().setUpAsync()

    def create_patch(self, **patch_kwargs):
        """A helper method to create, start and schedule the end of a patch."""
        patcher = patch.object(**patch_kwargs)
        started_patch = patcher.start()
        self.addCleanup(patcher.stop)
        return started_patch

    async def get_application(self):
        """Overrides AioHTTPTestCase.get_application()."""
        app = web.Application()
        # Some of the routes we'll be testing
        app.router.add_route('GET', self.web_svc.get_route(WebService.HOME_KEY), self.web_api.index)
        app.router.add_route('GET', self.web_svc.get_route(WebService.EDIT_KEY), self.web_api.edit)
        app.router.add_route('GET', self.web_svc.get_route(WebService.ABOUT_KEY), self.web_api.about)
        app.router.add_route('*', self.web_svc.get_route(WebService.REST_KEY), self.web_api.rest_api)
        # A different route for limit-testing
        app.router.add_route('*', '/limit' + self.web_svc.get_route(WebService.REST_KEY),
                             self.web_api_with_limit.rest_api)
        aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(os.path.join('webapp', 'html')))
        return app

    def reset_queue(self, rest_svc=None):
        """Function to reset the queue variables from a test RestService instance."""
        # Default parameter for rest service if not provided
        rest_svc = rest_svc or self.rest_svc
        # Note all tasks in the queue object as done
        with suppress(asyncio.QueueEmpty):
            for _ in range(rest_svc.queue.qsize()):
                rest_svc.queue.get_nowait()
                rest_svc.queue.task_done()
        # Reset the other variables
        rest_svc.queue_map = dict()
        rest_svc.clean_current_tasks()

    async def test_attack_list(self):
        """Function to test the attack list for the dropdown was created successfully."""
        # For our test attack data, we predict 2 will not be sub attacks (no Txx.xx TID) and 1 will be
        predicted = [dict(uid='d99999', name='Drain', tid='T1029', parent_tid=None, parent_name=None),
                     dict(uid='f12345', name='Fire', tid='T1562', parent_tid=None, parent_name=None),
                     dict(uid='f32451', name='Firaga', tid='T1562.004', parent_tid='T1562', parent_name='Fire')]
        # The generated dropdown list to check against our prediction
        result = self.web_api.attack_dropdown_list
        for attack_dict in result:
            self.assertTrue(attack_dict in predicted, msg='Attack %s was present but not expected.' % str(attack_dict))
        for attack_dict in predicted:
            self.assertTrue(attack_dict in result, msg='Attack %s was expected but not present.' % str(attack_dict))

    async def test_about_page(self):
        """Function to test the about page loads successfully."""
        resp = await self.client.get('/about')
        self.assertTrue(resp.status == 200, msg='About page failed to load successfully.')

    async def test_home_page(self):
        """Function to test the home page loads successfully."""
        resp = await self.client.get('/')
        self.assertTrue(resp.status == 200, msg='Home page failed to load successfully.')

    async def test_edit_report_loads(self):
        """Function to test loading an edit-report page is successful."""
        # Insert a report
        report_title = 'Will this load?'
        report = dict(title=report_title, url='please.load', current_status=ReportStatus.IN_REVIEW.value)
        await self.db.insert_generate_uid('reports', report)
        # Check the report edit page loads
        resp = await self.client.get('/edit/' + quote(report_title, safe=''))
        self.assertTrue(resp.status == 200, msg='Edit-report page failed to load successfully.')

    async def test_edit_queued_report_fails(self):
        """Function to test loading an edit-report page for a queued report fails."""
        # Insert a report
        report_title = 'Queued-reports shall not pass!'
        report = dict(title=report_title, url='dont.load', current_status=ReportStatus.QUEUE.value)
        await self.db.insert_generate_uid('reports', report)
        # Check the report edit page loads
        resp = await self.client.get('/edit/' + quote(report_title, safe=''))
        self.assertTrue(resp.status == 404, msg='Viewing an edit-queued-report page resulted in a non-404 response.')

    async def test_incorrect_submission(self):
        """Function to test when a user makes a bad request to submit a report."""
        # Request data to test: one with too many titles; another with too many URLs
        test_data = [dict(index='insert_report', url=['twinkle.twinkle'], title=['Little Star', 'How I wonder?']),
                     dict(index='insert_report', url=['twinkle.twinkle', 'how.i.wonder'], title=['Little Star'])]
        # Same process for each item in test_data
        for data in test_data:
            # Check we receive an error response
            resp = await self.client.post('/rest', json=data)
            self.assertTrue(resp.status == 500, msg='Mismatched titles-URLs submission resulted in a non-500 response.')
            # Check the user receives an error message
            resp_json = await resp.json()
            error_msg, alert_user = resp_json.get('error'), resp_json.get('alert_user')
            predicted = 'Number of URLs and titles do not match, please insert same number of comma-separated items.'
            self.assertEqual(error_msg, predicted, msg='Mismatched titles-URLs submission gives different error.')
            self.assertTrue(alert_user, msg='Mismatched titles-URLs submission is not alerted to the user.')

    async def test_incorrect_rest_endpoint(self):
        """Function to test incorrect REST endpoints do not result in a server error."""
        # Two examples of bad request data to test
        invalid_index = dict(index='insert_report!!!', data='data.doesnt.matter')
        no_index_supplied = dict(woohoo='send me!')
        resp = await self.client.post('/rest', json=invalid_index)
        self.assertTrue(resp.status == 404, msg='Incorrect `index` parameter resulted in a non-404 response.')
        resp = await self.client.post('/rest', json=no_index_supplied)
        self.assertTrue(resp.status == 404, msg='Missing `index` parameter resulted in a non-404 response.')

    async def test_queue_limit(self):
        """Function to test the queue limit works correctly."""
        # Given the randomised queue limit for this test, obtain it and create a limit-exceeding amount of data
        limit = self.rest_svc_with_limit.QUEUE_LIMIT
        titles = ['title%s' % x for x in range(limit + 1)]
        urls = ['url%s' % x for x in range(limit + 1)]
        data = dict(index='insert_report', url=urls, title=titles)
        # Begin some patches
        # We are not passing valid URLs; mock verifying the URLs to raise no errors
        self.create_patch(target=WebService, attribute='verify_url', return_value=None)
        # Duplicate URL checks will raise an error with malformed URLS; mock this to raise no errors
        self.create_patch(target=WebService, attribute='urls_match', return_value=False)
        # We don't want the queue to be checked after this test; mock this to return (and do) nothing
        self.create_patch(target=RestService, attribute='check_queue', return_value=None)

        # Send off the limit-exceeding data
        resp = await self.client.post('/limit/rest', json=data)
        # Check for a positive response (as reports would have been submitted)
        self.assertTrue(resp.status == 200, msg='Bulk-report submission resulted in a non-200 response.')
        resp_json = await resp.json()
        # Check that the user is told 1 report exceeded the limit and was not added to the queue
        success, info, alert_user = resp_json.get('success'), resp_json.get('info'), resp_json.get('alert_user')
        self.assertTrue(success, msg='Bulk-report submission was not flagged as successful.')
        self.assertTrue(alert_user, msg='Bulk-report submission with exceeded-queue was not alerted to user.')
        predicted = ('1 of %s report(s) not added to the queue' % (limit + 1) in info) and \
                    ('1 exceeded queue limit' in info)
        self.assertTrue(predicted, msg='Bulk-report submission with exceeded-queue message to user is different.')
        # Check that the queue is filled to its limit
        self.assertEqual(self.rest_svc_with_limit.queue.qsize(), self.rest_svc_with_limit.QUEUE_LIMIT,
                         msg='Bulk-report submission with exceeded-queue resulted in an unfilled queue.')
        # Tidy-up for this method: reset queue limit and queue
        self.reset_queue(rest_svc=self.rest_svc_with_limit)

    async def test_malformed_csv(self):
        """Function to test the behaviour of submitting a malformed CSV."""
        # Test cases for malformed CSVs
        wrong_columns = dict(file='titles,urls\nt1,url.1\nt2,url.2\n')
        wrong_param = dict(data='title,url\nt1,url.1\nt2,url.2\n')
        too_many_columns = dict(file='title,url,title\nt1,url.1,t1\nt2,url.2,t2\n')
        urls_missing = dict(file='title,url\nt1,\nt2,\n')
        # The test cases paired with expected error messages
        tests = [(wrong_columns, 'Two columns have not been specified'), (wrong_param, 'Error inserting report(s)'),
                 (too_many_columns, 'Two columns have not been specified'),
                 (urls_missing, 'CSV is missing text in at least one row')]
        for test_data, predicted_msg in tests:
            # Call the CSV REST endpoint with the malformed data and check the response
            data = dict(index='insert_csv')
            data.update(test_data)
            resp = await self.client.post('/rest', json=data)
            resp_json = await resp.json()
            error_msg = resp_json.get('error')
            self.assertTrue(resp.status >= 400, msg='Malformed CSV data resulted in successful response.')
            self.assertTrue(predicted_msg in error_msg, msg='Malformed CSV error message formed incorrectly.')

    async def submit_test_report(self, report, fail_map_html=False):
        """A helper method to submit a test report and create some associated test-sentences."""
        # Some test sentences and expected analysed html for them
        sen1 = 'When Creating Test Data...'
        sen2 = 'i. It can be quite draining'
        html = [{'html': sen1, 'text': sen1, 'tag': 'p', 'ml_techniques_found': [], 'res_techniques_found': []},
                {'html': sen2, 'text': sen2, 'tag': 'li', 'ml_techniques_found': [('d99999', 'Drain')],
                 'res_techniques_found': []}]
        # The result of the mapping function (no html, no Article object)
        map_result = None, None
        if not fail_map_html:
            # If we are not failing the mapping stage, mock the newspaper.Article for the mapping returned object
            mocked_article = MagicMock()
            mocked_article.text = '%s\n%s' % (sen1, sen2)
            map_result = html, mocked_article
        # Patches for when RestService.start_analysis() is called
        self.create_patch(target=WebService, attribute='map_all_html', return_value=map_result)
        self.create_patch(target=DataService, attribute='ml_reg_split', return_value=([], list(self.attacks.items())))
        self.create_patch(target=MLService, attribute='build_pickle_file', return_value=(False, dict()))
        self.create_patch(target=MLService, attribute='analyze_html', return_value=html)

        # Update relevant queue and insert report in DB as these tasks would have been done before submission
        queue = self.rest_svc.get_queue_for_user()
        queue.append(report['url'])
        await self.db.insert('reports', report)
        # Mock the analysis of the report
        await self.rest_svc.start_analysis(criteria=report)

    async def test_start_analysis_success(self):
        """Function to test the behaviour of start analysis when successful."""
        report_id = str(uuid4())
        # Submit and analyse a test report
        await self.submit_test_report(dict(uid=report_id, title='Analyse This!', url='analysing.this',
                                           current_status=ReportStatus.QUEUE.value))
        # Check in the DB that the status got updated
        report_db = await self.db.get('reports', equal=dict(uid=report_id))
        self.assertEqual(report_db[0].get('current_status'), ReportStatus.NEEDS_REVIEW.value,
                         msg='Analysed report was not moved to \'Needs Review\'.')
        # Check the report did not error
        self.assertEqual(report_db[0].get('error'), self.db.val_as_false,
                         msg='Analysed report unexpectedly has its error flag as True.')
        # Check that two sentences for this report got added to the report sentences table and its backup
        sen_db = await self.db.get('report_sentences', equal=dict(report_uid=report_id))
        sen_db_backup = await self.db.get('report_sentences_initial', equal=dict(report_uid=report_id))
        self.assertEqual(len(sen_db), 2, msg='Analysed report did not create 2 sentences in DB.')
        self.assertEqual(len(sen_db_backup), 2, msg='Analysed report did not create 2 sentences in backup DB table.')

    async def test_start_analysis_error(self):
        """Function to test the behaviour of start analysis when there is an error."""
        report_id = str(uuid4())
        # Submit and analyse a test report
        await self.submit_test_report(dict(uid=report_id, title='Analyse This!', url='analysing.this',
                                           current_status=ReportStatus.QUEUE.value), fail_map_html=True)
        # Check in the DB that the status did not change
        report_db = await self.db.get('reports', equal=dict(uid=report_id))
        self.assertEqual(report_db[0].get('current_status'), ReportStatus.QUEUE.value,
                         msg='Analysed report which errors had a different status than initial \'Queue\'.')
        # Check the report has its error flagged
        self.assertEqual(report_db[0].get('error'), self.db.val_as_true,
                         msg='Analysed report which errors did not have its error flag as True.')

    async def test_set_status(self):
        """Function to test setting the status of a report."""
        report_id, report_title = str(uuid4()), 'To Set or Not to Set'
        # Submit and analyse a test report
        await self.submit_test_report(dict(uid=report_id, title=report_title, url='analysing.this',
                                           current_status=ReportStatus.QUEUE.value))
        # Attempt to complete this newly-analysed report
        data = dict(index='set_status', set_status=ReportStatus.COMPLETED.value, report_title=report_title)
        resp = await self.client.post('/rest', json=data)
        resp_json = await resp.json()
        # Check an unsuccessful response was sent
        error_msg, alert_user = resp_json.get('error'), resp_json.get('alert_user')
        self.assertTrue(resp.status == 500, msg='Completing a report too early resulted in a non-500 response.')
        self.assertTrue('unconfirmed for this report' in error_msg,
                        msg='Error message for outstanding attacks in report is different than expected.')
        self.assertEqual(alert_user, self.db.val_as_true, msg='User is not notified over unconfirmed attacks in report.')
        # Delete the sentence that has an attack
        await self.db.delete('report_sentences', dict(report_uid=report_id, found_status=self.db.val_as_true))
        # Re-attempt setting the status
        resp = await self.client.post('/rest', json=data)
        # Check a successful response was sent
        self.assertTrue(resp.status < 300, msg='Completing a report resulted in a non-200 response.')

    async def test_revert_status(self):
        """Function to test setting the status of a report back to its initial status of 'Queue'."""
        report_id, report_title = str(uuid4()), 'To Set or Not to Set: The Sequel'
        # Submit and analyse a test report
        await self.submit_test_report(dict(uid=report_id, title=report_title, url='analysing.this',
                                           current_status=ReportStatus.QUEUE.value))
        # Attempt to revert the status for this newly-analysed report back into the queue
        data = dict(index='set_status', set_status=ReportStatus.QUEUE.value, report_title=report_title)
        resp = await self.client.post('/rest', json=data)
        resp_json = await resp.json()
        # Check an unsuccessful response was sent
        error_msg = resp_json.get('error')
        self.assertTrue(resp.status == 500, msg='Setting a report status to `Queue` resulted in a non-500 response.')
        self.assertTrue(error_msg == 'Error setting status.', msg='A different error appeared for re-queueing a report.')

    async def test_add_new_attack(self):
        """Function to test adding a new attack to a sentence."""
        report_id, attack_id = str(uuid4()), 'f12345'
        # Submit and analyse a test report
        await self.submit_test_report(dict(uid=report_id, title='Analyse This!', url='analysing.this',
                                           current_status=ReportStatus.QUEUE.value))
        # Get the report sentences for this report
        sentences = await self.db.get('report_sentences', equal=dict(report_uid=report_id))
        sen_id = None
        for sen in sentences:
            # Find the sentence that has no prior-attacks for this test
            if sen.get('found_status') == self.db.val_as_false:
                sen_id = sen.get(UID_KEY)
        if not sen_id:
            self.skipTest('Could not test adding an attack as report test sentences have attacks already.')
        # Proceed to add an attack
        data = dict(index='add_attack', sentence_id=sen_id, attack_uid=attack_id)
        resp = await self.client.post('/rest', json=data)
        self.assertTrue(resp.status < 300, msg='Adding an attack to a sentence resulted in a non-200 response.')
        # Confirm this sentence is marked as a false negative (and not present in the other tables)
        tps = await self.db.get('true_positives', equal=dict(sentence_id=sen_id, attack_uid=attack_id))
        tns = await self.db.get('true_negatives', equal=dict(sentence_id=sen_id, attack_uid=attack_id))
        fps = await self.db.get('false_positives', equal=dict(sentence_id=sen_id, attack_uid=attack_id))
        fns = await self.db.get('false_negatives', equal=dict(sentence_id=sen_id, attack_uid=attack_id))
        self.assertTrue(len(fns) == 1, msg='New, accepted attack did not appear as 1 record in false negatives table.')
        self.assertTrue(len(tps) + len(tns) + len(fps) == 0,
                        msg='New, accepted attack appeared incorrectly in other table(s) (not being false negatives).')

    async def test_confirm_predicted_attack(self):
        """Function to test confirming a predicted attack of a sentence."""
        report_id, attack_id = str(uuid4()), 'd99999'
        # Submit and analyse a test report
        await self.submit_test_report(dict(uid=report_id, title='Analyse This!', url='analysing.this',
                                           current_status=ReportStatus.QUEUE.value))
        # Get the report sentences for this report
        sentences = await self.db.get('report_sentences', equal=dict(report_uid=report_id))
        sen_id = None
        for sen in sentences:
            # Find the sentence that has an attack for this test
            if sen.get('found_status') == self.db.val_as_true:
                sen_id = sen.get(UID_KEY)
        if not sen_id:
            self.skipTest('Could not test confirming an attack as report test sentences do not have attacks.')
        # Proceed to confirm an attack
        data = dict(index='add_attack', sentence_id=sen_id, attack_uid=attack_id)
        resp = await self.client.post('/rest', json=data)
        self.assertTrue(resp.status < 300, msg='Confirming an attack of a sentence resulted in a non-200 response.')
        # Confirm this sentence is marked as a true positive (and not present in the other tables)
        tps = await self.db.get('true_positives', equal=dict(sentence_id=sen_id, attack_uid=attack_id))
        tns = await self.db.get('true_negatives', equal=dict(sentence_id=sen_id, attack_uid=attack_id))
        fps = await self.db.get('false_positives', equal=dict(sentence_id=sen_id, attack_uid=attack_id))
        fns = await self.db.get('false_negatives', equal=dict(sentence_id=sen_id, attack_uid=attack_id))
        self.assertTrue(len(tps) == 1, msg='Confirmed attack did not appear as 1 record in true positives table.')
        self.assertTrue(len(tns) + len(fps) + len(fns) == 0,
                        msg='Confirmed attack appeared incorrectly in other table(s) (not being true positives).')

    async def test_reject_attack(self):
        """Function to test rejecting an attack to a sentence."""
        report_id, attack_id = str(uuid4()), 'd99999'
        # Submit and analyse a test report
        await self.submit_test_report(dict(uid=report_id, title='Analyse This!', url='analysing.this',
                                           current_status=ReportStatus.QUEUE.value))
        # Get the report sentences for this report
        sentences = await self.db.get('report_sentences', equal=dict(report_uid=report_id))
        sen_id = None
        for sen in sentences:
            # Find the sentence that has an attack for this test
            if sen.get('found_status') == self.db.val_as_true:
                sen_id = sen.get(UID_KEY)
        if not sen_id:
            self.skipTest('Could not test rejecting an attack as report test sentences do not have attacks.')
        # Proceed to reject an attack
        data = dict(index='reject_attack', sentence_id=sen_id, attack_uid=attack_id)
        resp = await self.client.post('/rest', json=data)
        self.assertTrue(resp.status < 300, msg='Rejecting an attack of a sentence resulted in a non-200 response.')
        # Confirm this sentence is marked as a false positive (and not present in the other tables)
        tps = await self.db.get('true_positives', equal=dict(sentence_id=sen_id, attack_uid=attack_id))
        tns = await self.db.get('true_negatives', equal=dict(sentence_id=sen_id, attack_uid=attack_id))
        fps = await self.db.get('false_positives', equal=dict(sentence_id=sen_id, attack_uid=attack_id))
        fns = await self.db.get('false_negatives', equal=dict(sentence_id=sen_id, attack_uid=attack_id))
        self.assertTrue(len(fps) == 1, msg='Rejected attack did not appear as 1 record in false positives table.')
        self.assertTrue(len(tps) + len(tns) + len(fns) == 0,
                        msg='Rejected attack appeared incorrectly in other table(s) (not being false positives).')

    async def test_get_sentence_info(self):
        """Function to test obtaining the data for a report sentence."""
        report_id = str(uuid4())
        # Submit and analyse a test report
        await self.submit_test_report(dict(uid=report_id, title='Analyse This!', url='analysing.this',
                                           current_status=ReportStatus.QUEUE.value))
        # Get the report sentences for this report
        sentences = await self.db.get('report_sentences', equal=dict(report_uid=report_id))
        sen_id = None
        for sen in sentences:
            # Find the sentence that has an attack for this test
            if sen.get('found_status') == self.db.val_as_true:
                sen_id = sen.get(UID_KEY)
        if not sen_id:
            self.skipTest('Could not test getting sentence data as report test sentences do not have attacks.')
        # Obtain the sentence info
        resp_context = await self.client.post('/rest', json=dict(index='sentence_context', sentence_id=sen_id))
        resp_attacks = await self.client.post('/rest', json=dict(index='confirmed_attacks', sentence_id=sen_id))
        resp_context_json = await resp_context.json()
        resp_attacks_json = await resp_attacks.json()
        # This sentence has 1 unconfirmed attack; check results reflect this
        self.assertTrue(resp_context.status < 300, msg='Obtaining sentence data resulted in a non-200 response.')
        self.assertTrue(resp_attacks.status < 300, msg='Obtaining sentence attack-data resulted in a non-200 response.')
        self.assertEqual(resp_context_json[0].get('attack_uid'), 'd99999',
                         msg='Predicted attack not associated with sentence as expected.')
        self.assertEqual(len(resp_attacks_json), 0, msg='Confirmed attacks associated with sentence unexpectedly.')
        # Confirm attack
        await self.client.post('/rest', json=dict(index='add_attack', sentence_id=sen_id, attack_uid='d99999'))
        # Confirm this doesn't change sentence context but changes confirmed attacks
        resp_context = await self.client.post('/rest', json=dict(index='sentence_context', sentence_id=sen_id))
        resp_attacks = await self.client.post('/rest', json=dict(index='confirmed_attacks', sentence_id=sen_id))
        resp_context_json = await resp_context.json()
        resp_attacks_json = await resp_attacks.json()
        self.assertTrue(resp_context.status < 300, msg='Obtaining sentence data resulted in a non-200 response.')
        self.assertTrue(resp_attacks.status < 300, msg='Obtaining sentence attack-data resulted in a non-200 response.')
        self.assertEqual(resp_context_json[0].get('attack_uid'), 'd99999',
                         msg='Confirmed attack not associated with sentence as expected.')
        self.assertTrue(len(resp_attacks_json) > 0, msg='No confirmed attacks appearing for sentence.')
        self.assertEqual(resp_attacks_json[0].get(UID_KEY), 'd99999',
                         msg='Confirmed attack not returned in confirmed attacks for sentence.')

    async def test_rollback_report(self):
        """Function to test functionality to rollback a report."""
        report_id, report_title = str(uuid4()), 'Never Gonna Rollback This Up'
        # Submit and analyse a test report
        await self.submit_test_report(dict(uid=report_id, title=report_title, url='analysing.this',
                                           current_status=ReportStatus.QUEUE.value))
        # Get the report sentences for this report
        sentences = await self.db.get('report_sentences', equal=dict(report_uid=report_id),
                                      order_by_asc=dict(sen_index=1))
        # Obtain one of the sentence IDs
        sen_id = sentences[0].get(UID_KEY)
        # Delete the sentence
        data = dict(index='remove_sentence', sentence_id=sen_id)
        await self.client.post('/rest', json=data)
        # Confirm the sentence got deleted
        new_sentences = await self.db.get('report_sentences', equal=dict(report_uid=report_id),
                                          order_by_asc=dict(sen_index=1))
        if len(sentences) - 1 != len(new_sentences) or new_sentences[0].get(UID_KEY) == sen_id:
            self.fail('Could not test report rollback as removing a sentence did not work as expected.')
        # Rollback the report
        data = dict(index='rollback_report', report_title=report_title)
        resp = await self.client.post('/rest', json=data)
        self.assertTrue(resp.status < 300, msg='Report-rollback resulted in a non-200 response.')
        # Check the DB that the number of sentences are the same
        rollback_sentences = await self.db.get('report_sentences', equal=dict(report_uid=report_id),
                                               order_by_asc=dict(sen_index=1))
        self.assertEqual(len(sentences), len(rollback_sentences),
                         msg='Report-rollback resulted in a different number of report sentences.')
        # Check that the first sentence is the one we previously deleted
        self.assertEqual(rollback_sentences[0].get(UID_KEY), sen_id,
                         msg='Report-rollback resulted in a different first sentence.')