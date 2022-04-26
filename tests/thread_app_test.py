import aiohttp_jinja2
import asyncio
import jinja2
import os
import random
import sqlite3

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase
from contextlib import suppress
from stix2.base import _STIXBase
from tests.misc import delete_db_file, SCHEMA_FILE
from threadcomponents.database.dao import Dao
from threadcomponents.database.thread_sqlite3 import ThreadSQLite
from threadcomponents.handlers.web_api import WebAPI
from threadcomponents.service import data_svc
from threadcomponents.service.data_svc import DataService, NO_DESC
from threadcomponents.service.ml_svc import MLService
from threadcomponents.service.reg_svc import RegService
from threadcomponents.service.rest_svc import RestService
from threadcomponents.service.web_svc import WebService
from unittest.mock import MagicMock, patch


class ThreadAppTest(AioHTTPTestCase):
    """A Thread test case that involves interacting with the application."""
    DB_TEST_FILE = os.path.join('tests', 'threadtest.db')

    @classmethod
    def setUpClass(cls):
        """Any setting-up before all the test methods."""
        cls.db = ThreadSQLite(cls.DB_TEST_FILE)
        with open(SCHEMA_FILE) as schema_opened:
            cls.schema = schema_opened.read()
        cls.backup_schema = cls.db.generate_copied_tables(cls.schema)
        cls.dao = Dao(engine=cls.db)
        cls.web_svc = WebService()
        cls.reg_svc = RegService(dao=cls.dao)
        cls.data_svc = DataService(dao=cls.dao, web_svc=cls.web_svc)
        cls.ml_svc = MLService(web_svc=cls.web_svc, dao=cls.dao)
        cls.rest_svc = RestService(cls.web_svc, cls.reg_svc, cls.data_svc, cls.ml_svc, cls.dao,
                                   attack_file_settings=dict(update=False))
        services = dict(dao=cls.dao, data_svc=cls.data_svc, ml_svc=cls.ml_svc, reg_svc=cls.reg_svc, web_svc=cls.web_svc,
                        rest_svc=cls.rest_svc)
        cls.web_api = WebAPI(services=services)
        # Duplicate resources so we can test the queue limit without causing limit-exceeding test failures elsewhere
        cls.rest_svc_with_limit = RestService(cls.web_svc, cls.reg_svc, cls.data_svc, cls.ml_svc, cls.dao,
                                              queue_limit=random.randint(1, 20))
        services_with_limit = dict(services)
        services_with_limit.update(rest_svc=cls.rest_svc_with_limit)
        cls.web_api_with_limit = WebAPI(services=services_with_limit)
        # Some test-attack data
        cls.attacks = dict(d99999='Drain', f12345='Fire', f32451='Firaga', s00001='requiem')

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
        a4_name = self.attacks.get('s00001')
        attack_1 = dict(uid='f12345', description='Fire spell costing 4MP', tid='T1562', name=a1_name)
        attack_2 = dict(uid='f32451', description='Stronger Fire spell costing 16MP', tid='T1562.004', name=a2_name)
        attack_3 = dict(uid='d99999', description='Absorbs HP', tid='T1029', name=a3_name)
        attack_4 = dict(uid='s00001', description='Damages all enemies', tid='T1485', name=a4_name, inactive=1)
        for attack in [attack_1, attack_2, attack_3, attack_4]:
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
        app.router.add_route('GET', self.web_svc.get_route(WebService.HOW_IT_WORKS_KEY), self.web_api.how_it_works)
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

    async def patches_on_insert(self):
        """A helper method to set up patches when an insert_* rest endpoint is tested."""
        # We are not passing valid URLs; mock verifying the URLs to raise no errors
        self.create_patch(target=WebService, attribute='verify_url', return_value=None)
        # Duplicate URL checks will raise an error with malformed URLS; mock this to raise no errors
        self.create_patch(target=WebService, attribute='urls_match', return_value=False)
        # We don't want the queue to be checked after this test; mock this to return (and do) nothing
        self.create_patch(target=RestService, attribute='check_queue', return_value=None)

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

    def mock_current_attack_data(self, attack_list=None):
        """Helper-method to mock the retrieval of the current Att%ck data by returning a specified attack-list."""
        attack_list = attack_list or []
        new_attack_list = []
        # For each attack in the given list, create an entry that follows the format from what is usually retrieved
        for attack in attack_list:
            tid = attack.get('tid', 'Txxxx')
            new_attack_list.append(dict(
                type='attack-pattern', modified='2022-03-7T00:00:00.000Z', name=attack.get('name', 'No name'),
                created='2001-07-19T00:00:00.000Z', id=attack.get('uid', random.randint(0, 999999999)),
                revoked=True, spec_version='2.1', description=attack.get('description', NO_DESC),
                external_references=[
                    {'url': 'https://attack.mitre.org/techniques/' + tid,
                     'external_id': tid, 'source_name': 'mitre-attack'}
                ],
                x_mitre_attack_spec_version='2.1.0', x_mitre_domains=['enterprise-attack'], x_mitre_version='1.0',
            ))
        # Mock the fetch-data method to return our mocked list
        self.create_patch(target=data_svc, attribute='fetch_attack_data', return_value=dict(objects=new_attack_list))
        # Prevent the Stix library flagging incorrect data
        self.create_patch(target=_STIXBase, attribute='_check_property', return_value=False)
