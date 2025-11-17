import aiohttp_jinja2
import asyncio
import jinja2
import logging
import os
import random
import sqlite3

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase
from contextlib import suppress
from stix2.base import _STIXBase
from tests.misc import delete_db_file, SCHEMA_FILE

from threadcomponents.constants import UID as UID_KEY
from threadcomponents.enums import ReportStatus

from threadcomponents.database.dao import Dao
from threadcomponents.database.thread_sqlite3 import ThreadSQLite

from threadcomponents.handlers.web_api import WebAPI
from threadcomponents.reports.report_exporter import ReportExporter

from threadcomponents.service import attack_data_svc
from threadcomponents.service.attack_data_svc import AttackDataService
from threadcomponents.service.data_svc import DataService, NO_DESC
from threadcomponents.service.ml_svc import MLService
from threadcomponents.service.reg_svc import RegService
from threadcomponents.service.rest_svc import RestService
from threadcomponents.service.token_svc import TokenService
from threadcomponents.service.web_svc import WebService

from unittest.mock import MagicMock, patch


class ThreadAppTest(AioHTTPTestCase):
    """A Thread test case that involves interacting with the application."""

    DB_TEST_FILE = os.path.join("tests", "threadtest.db")
    # Any loggers to mute during test
    mute_logger_warnings = []
    mute_logger_errors = []

    @classmethod
    def setUpClass(cls):
        """Any setting-up before all the test methods."""
        super().setUpClass()
        # Log only errors to omit warnings when triggering bad/not-allowed requests and executing asyncio Tasks
        # Ignore htmldate errors as we are testing with non-existent URLs
        to_mute = [
            (cls.mute_logger_warnings + ["asyncio"], logging.ERROR),
            (cls.mute_logger_errors + ["htmldate"], logging.CRITICAL),
        ]
        for logger_names, logger_level in to_mute:
            for logger_name in logger_names:
                logger = logging.getLogger(logger_name)
                logger.setLevel(logger_level)

        cls.db = ThreadSQLite(cls.DB_TEST_FILE)
        with open(SCHEMA_FILE) as schema_opened:
            cls.schema = schema_opened.read()
        cls.backup_schema = cls.db.generate_copied_tables(cls.schema)
        cls.dao = Dao(engine=cls.db)
        cls.web_svc = WebService()
        cls.reg_svc = RegService()
        cls.data_svc = DataService(dao=cls.dao, web_svc=cls.web_svc)
        cls.token_svc = TokenService()
        cls.ml_svc = MLService(token_svc=cls.token_svc)
        cls.attack_data_svc = AttackDataService(attack_file_settings=dict(update=False))
        cls.rest_svc = RestService(
            web_svc=cls.web_svc,
            reg_svc=cls.reg_svc,
            data_svc=cls.data_svc,
            token_svc=cls.token_svc,
            ml_svc=cls.ml_svc,
            dao=cls.dao,
            attack_data_svc=cls.attack_data_svc,
        )
        services = dict(
            dao=cls.dao,
            data_svc=cls.data_svc,
            token_svc=cls.token_svc,
            ml_svc=cls.ml_svc,
            reg_svc=cls.reg_svc,
            web_svc=cls.web_svc,
            rest_svc=cls.rest_svc,
            attack_data_svc=cls.attack_data_svc,
        )
        report_exporter = ReportExporter(services=services)
        cls.web_api = WebAPI(services=services, report_exporter=report_exporter)
        # Duplicate resources so we can test the queue limit without causing limit-exceeding test failures elsewhere
        cls.rest_svc_with_limit = RestService(
            web_svc=cls.web_svc,
            reg_svc=cls.reg_svc,
            data_svc=cls.data_svc,
            ml_svc=cls.ml_svc,
            dao=cls.dao,
            token_svc=cls.token_svc,
            queue_limit=random.randint(1, 20),
            attack_data_svc=cls.attack_data_svc,
        )
        services_with_limit = dict(services)
        services_with_limit.update(rest_svc=cls.rest_svc_with_limit)
        report_exporter = ReportExporter(services=services_with_limit)
        cls.web_api_with_limit = WebAPI(services=services_with_limit, report_exporter=report_exporter)
        # Some test-attack data
        cls.attacks = dict(d99999="Drain", f12345="Fire", f32451="Firaga", s00001="requiem", s12345="Yevon")

    @classmethod
    def tearDownClass(cls):
        """Any tidying-up after all the test methods."""
        # Delete the database so a new DB file is used in next test-run
        delete_db_file(cls.DB_TEST_FILE)

    async def setUpAsync(self):
        """Any setting-up before each test method."""
        # Build the database (can't run in setUpClass() as this is an async method)
        await self.db.build(self.schema)
        await self.db.build(self.backup_schema, is_partial=True)
        # Insert some attack data
        attack_1 = dict(uid="f12345", tid="T1562", name=self.attacks.get("f12345"))
        attack_2 = dict(uid="f32451", tid="T1562.004", name=self.attacks.get("f32451"))
        attack_3 = dict(uid="d99999", tid="T1029", name=self.attacks.get("d99999"))
        attack_4 = dict(uid="s00001", tid="T1485", name=self.attacks.get("s00001"), inactive=1)
        attack_5 = dict(uid="s12345", tid="S1030", name=self.attacks.get("s12345"))

        for attack in [attack_1, attack_2, attack_3, attack_4, attack_5]:
            # Ignoring Integrity Error in case other test case already has inserted this data (causing duplicate UIDs)
            with suppress(sqlite3.IntegrityError):
                await self.db.insert("attack_uids", attack)

        # Insert some category, keyword & country data
        cat_1 = dict(uid="c010101", keyname="aerospace", name="Aerospace")
        cat_2 = dict(uid="c123456", keyname="music", name="Music")
        cat_3 = dict(uid="c898989", keyname="film", name="Film")
        cat_4 = dict(uid="c000001", keyname="rockets", name="Rockets")
        group_1 = dict(uid="apt1", name="APT1")
        group_2 = dict(uid="apt2", name="APT2")
        group_3 = dict(uid="apt3", name="APT3")
        self.data_svc.country_dict = dict(HB="Hobbiton", TA="Tatooine", WA="Wakanda")

        for cat, group in [(cat_1, group_1), (cat_2, group_2), (cat_3, group_3)]:
            with suppress(sqlite3.IntegrityError):
                await self.db.insert("categories", cat)
                await self.db.insert("keywords", group)
            self.web_svc.categories_dict[cat["keyname"]] = dict(name=cat["name"], sub_categories=[])

        self.web_svc.categories_dict["rockets"] = dict(name="Rockets", sub_categories=[], auto_select=["aerospace"])
        with suppress(sqlite3.IntegrityError):
            await self.db.insert("categories", cat_4)
            await self.db.insert(
                "categories_auto_add",
                dict(
                    uid="aa000001",
                    selected="rockets",
                    auto_add="aerospace",
                )
            )

        # Carry out pre-launch tasks except for prepare_queue(): replace the call of this to return (and do) nothing
        # We don't want multiple prepare_queue() calls so the queue does not accumulate between tests
        with patch.object(RestService, "prepare_queue", return_value=None):
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
        app.router.add_route("GET", self.web_svc.get_route(WebService.HOME_KEY), self.web_api.index)
        app.router.add_route("GET", self.web_svc.get_route(WebService.EDIT_KEY), self.web_api.edit)
        app.router.add_route("GET", self.web_svc.get_route(WebService.ABOUT_KEY), self.web_api.about)
        app.router.add_route("GET", self.web_svc.get_route(WebService.HOW_IT_WORKS_KEY), self.web_api.how_it_works)
        app.router.add_route("GET", self.web_svc.get_route(WebService.EXPORT_AFB_KEY), self.web_api.afb_export)
        app.router.add_route("*", self.web_svc.get_route(WebService.REST_KEY), self.web_api.rest_api)
        # A different route for limit-testing
        app.router.add_route(
            "*", "/limit" + self.web_svc.get_route(WebService.REST_KEY), self.web_api_with_limit.rest_api
        )
        aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(os.path.join("webapp", "html")))
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
        self.create_patch(target=WebService, attribute="verify_url", return_value=None)
        # Duplicate URL checks will raise an error with malformed URLS; mock this to raise no errors
        self.create_patch(target=WebService, attribute="urls_match", return_value=False)
        # We don't want the queue to be checked after this test; mock this to return (and do) nothing
        self.create_patch(target=RestService, attribute="check_queue", return_value=None)

    async def submit_test_report(
        self,
        report,
        sentences=None,
        attacks_found=None,
        fail_map_html=False,
        post_confirm_attack=False,
        confirm_attack="d99999",
    ):
        """A helper method to submit a test report and create some associated test-sentences."""
        if not report.get("current_status"):
            report["current_status"] = ReportStatus.QUEUE.value
        # Some test sentences and expected analysed html for them
        sentences = sentences or ["When Creating Test Data...", "i. It can be quite draining"]
        no_attack, has_attack = ([], [("d99999", "Drain")])
        attacks_found = attacks_found or []
        html = []
        for sen_index, sentence in enumerate(sentences):
            # Assign attack for this sentence if provided else for every second sentence, assign it an attack
            try:
                attack = attacks_found[sen_index]
            except IndexError:
                attack = has_attack if sen_index % 2 else no_attack
            html.append(
                {
                    "html": sentence,
                    "text": sentence,
                    "tag": "p",
                    "ml_techniques_found": attack,
                    "reg_techniques_found": [],
                }
            )
        # The result of the mapping function (no html, no Article object)
        map_result = None, None
        if not fail_map_html:
            # If we are not failing the mapping stage, mock the newspaper.Article for the mapping returned object
            mocked_article = MagicMock()
            mocked_article.text = "\n".join(sentences)
            map_result = html, mocked_article
        # Patches for when RestService.start_analysis() is called
        self.create_patch(target=WebService, attribute="map_all_html", return_value=map_result)
        self.create_patch(target=TokenService, attribute="tokenize_sentence", return_value=html)
        self.create_patch(
            target=AttackDataService, attribute="ml_and_reg_split", return_value=([], list(self.attacks.items()))
        )
        self.create_patch(target=MLService, attribute="build_pickle_file", return_value=(False, dict()))
        self.create_patch(target=MLService, attribute="analyze_html", return_value=html)

        # Update relevant queue and insert report in DB as these tasks would have been done before submission
        queue = self.rest_svc.get_queue_for_user()
        queue.append(report["url"])
        await self.db.insert("reports", report)
        # Mock the analysis of the report
        await self.rest_svc.start_analysis(criteria=report)

        if post_confirm_attack:
            # Get the report sentences for this report
            db_sentences = await self.db.get("report_sentences", equal=dict(report_uid=report[UID_KEY]))
            sen_id = None
            for sen in db_sentences:
                # Find the sentence that has an attack for this test
                if sen.get("found_status") == self.db.val_as_true:
                    sen_id = sen.get(UID_KEY)
            if not sen_id:
                return
            await self.client.post(
                "/rest", json=dict(index="add_attack", sentence_id=sen_id, attack_uid=confirm_attack)
            )

    async def confirm_report_sentence_attacks(self, report_id, sentence_index, attack_list):
        """Accepts a list of attacks for a given test-sentence index."""
        sentence = await self.db.get("report_sentences", equal=dict(report_uid=report_id, sen_index=sentence_index))

        for accept in attack_list:
            await self.client.post(
                "/rest",
                json=dict(
                    index="add_attack",
                    sentence_id=sentence[0][UID_KEY],
                    attack_uid=accept,
                ),
            )

    def mock_current_attack_data(self, attack_list=None):
        """Helper-method to mock the retrieval of the current Att%ck data by returning a specified attack-list."""
        attack_list = attack_list or []
        new_attack_list = []
        # For each attack in the given list, create an entry that follows the format from what is usually retrieved
        for attack in attack_list:
            tid = attack.get("tid", "Txxxx")
            new_attack_list.append(
                dict(
                    type="attack-pattern",
                    modified="2022-03-7T00:00:00.000Z",
                    name=attack.get("name", "No name"),
                    created="2001-07-19T00:00:00.000Z",
                    id=attack.get("uid", random.randint(0, 999999999)),
                    spec_version="2.1",
                    description=attack.get("description", NO_DESC),
                    external_references=[
                        {
                            "url": "https://attack.mitre.org/techniques/" + tid,
                            "external_id": tid,
                            "source_name": "mitre-attack",
                        }
                    ],
                    x_mitre_attack_spec_version="2.1.0",
                    x_mitre_domains=["enterprise-attack"],
                    x_mitre_version="1.0",
                )
            )
        # Mock the fetch-data method to return our mocked list
        self.create_patch(
            target=attack_data_svc, attribute="fetch_attack_stix_data_json", return_value=dict(objects=new_attack_list)
        )
        # Prevent the Stix library flagging incorrect data
        self.create_patch(target=_STIXBase, attribute="_check_property", return_value=False)
