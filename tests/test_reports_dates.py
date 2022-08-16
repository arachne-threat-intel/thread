import os

from tests.thread_app_test import ThreadAppTest
from threadcomponents.service.rest_svc import ReportStatus, UID as UID_KEY
from uuid import uuid4


class TestReportDates(ThreadAppTest):
    """A test suite for checking report actions to do with date fields."""
    DB_TEST_FILE = os.path.join('tests', 'threadtestreportdates.db')

    async def test_missing_date_written(self):
        """Function to test attempting to update report dates without a date-written value."""
        report_id, report_title = str(uuid4()), 'Marvel Dance Moves 1: Praise for Peter Parker'
        # Submit and analyse a test report
        await self.submit_test_report(dict(uid=report_id, title=report_title, url='dance.moves',
                                           current_status=ReportStatus.QUEUE.value))
        # Attempt to complete this newly-analysed report
        data = dict(index='update_report_dates', report_title=report_title, date_of=None, start_date=None, end_date=None)
        resp = await self.client.post('/rest', json=data)
        resp_json = await resp.json()
        # Check an unsuccessful response was sent
        error_msg, alert_user = resp_json.get('error'), resp_json.get('alert_user')
        self.assertTrue(resp.status == 500, msg='Missing date-written resulted in a non-500 response.')
        self.assertTrue('Article Publication Date missing' in error_msg,
                        msg='Error message for missing date-written value is different than expected.')
        self.assertEqual(alert_user, 1, msg='User is not notified over missing date-written value.')

    async def test_incorrect_report_date_order(self):
        """Function to test flagging incorrect ordering of report start and end dates."""
        report_id, report_title = str(uuid4()), 'Marvel Dance Moves 2: Dance Off with Star-Lord'
        # Submit and analyse a test report
        await self.submit_test_report(dict(uid=report_id, title=report_title, url='dance.moves',
                                           current_status=ReportStatus.QUEUE.value, date_written='2022-07-29'))
        # Attempt to complete this newly-analysed report
        data = dict(index='update_report_dates', report_title=report_title, start_date='2022-01-01', end_date='2021-12-25')
        resp = await self.client.post('/rest', json=data)
        resp_json = await resp.json()
        # Check an unsuccessful response was sent
        error_msg, alert_user = resp_json.get('error'), resp_json.get('alert_user')
        self.assertTrue(resp.status == 500, msg='Invalid date ordering resulted in a non-500 response.')
        self.assertTrue('Incorrect ordering of dates provided' in error_msg,
                        msg='Error message for invalid date ordering is different than expected.')
        self.assertEqual(alert_user, 1, msg='User is not notified over invalid date ordering.')

    async def test_unsetting_report_dates(self):
        """Function to test unsetting report start and end dates."""
        report_id, report_title = str(uuid4()), 'Marvel Dance Moves 3: Zooming with Zemo'
        # Submit and analyse a test report
        await self.submit_test_report(dict(uid=report_id, title=report_title, url='dance.moves',
                                           current_status=ReportStatus.QUEUE.value, date_written='2022-07-29',
                                           start_date='2022-01-01', end_date='2022-02-02'))
        # Attempt to complete this newly-analysed report
        data = dict(index='update_report_dates', report_title=report_title, start_date=None, end_date=None)
        # Check a successful response was sent and the dates were unset
        resp = await self.client.post('/rest', json=data)
        report = await self.db.get('reports', dict(uid=report_id))
        self.assertTrue(resp.status < 300, msg='Unsetting report dates resulted in a non-200 response.')
        self.assertIsNone(report[0]['start_date'], msg='Start date not unset.')
        self.assertIsNone(report[0]['end_date'], msg='End date not unset.')

    async def test_using_same_dates_flag(self):
        """Function to test setting the same report start and end dates."""
        report_id, report_title = str(uuid4()), 'Marvel Dance Moves 4: Lunging Like Loxias'
        # Submit and analyse a test report
        await self.submit_test_report(dict(uid=report_id, title=report_title, url='dance.moves',
                                           current_status=ReportStatus.QUEUE.value, date_written='2022-07-29',
                                           start_date='2022-01-01', end_date='2022-02-02'))
        # Attempt to complete this newly-analysed report
        data = dict(index='update_report_dates', report_title=report_title, start_date='2020-01-01', same_dates=True)
        # Check a successful response was sent and the dates were unset
        resp = await self.client.post('/rest', json=data)
        report = await self.db.get('reports', dict(uid=report_id))
        self.assertTrue(resp.status < 300, msg='Updating equal report dates resulted in a non-200 response.')
        self.assertEqual(report[0]['start_date'], '2020-01-01', msg='Start date not updated correctly.')
        self.assertEqual(report[0]['end_date'], '2020-01-01', msg='End date not updated correctly.')

    async def test_updating_report_dates(self):
        """Function to test successfully setting report start and end dates."""
        report_id, report_title = str(uuid4()), 'Marvel Dance Moves 5: Stanning over Stan Lee'
        # Submit and analyse a test report
        await self.submit_test_report(dict(uid=report_id, title=report_title, url='dance.moves', date_written=None,
                                           current_status=ReportStatus.QUEUE.value, start_date=None, end_date=None))
        # Attempt to complete this newly-analysed report
        data = dict(index='update_report_dates', report_title=report_title, date_of='2022-07-29',
                    start_date='2022-01-01', end_date='2022-02-02')
        # Check a successful response was sent and the dates were unset
        resp = await self.client.post('/rest', json=data)
        report = await self.db.get('reports', dict(uid=report_id))
        self.assertTrue(resp.status < 300, msg='Updating equal report dates resulted in a non-200 response.')
        self.assertEqual(report[0]['date_written'], '2022-07-29', msg='Start date not updated correctly.')
        self.assertEqual(report[0]['start_date'], '2022-01-01', msg='Start date not updated correctly.')
        self.assertEqual(report[0]['end_date'], '2022-02-02', msg='End date not updated correctly.')

    async def test_report_dates_outside_tech_dates(self):
        """Function to test setting the report start and end dates outside of technique dates."""
        report_id, report_title = str(uuid4()), 'Kamigawa Tales: Lucky Offering'
        # Submit and analyse a test report
        await self.submit_test_report(dict(uid=report_id, title=report_title, url='kami.gawa',
                                           date_written='2022-08-16', current_status=ReportStatus.QUEUE.value),
                                      post_confirm_attack=True)
        # Mapped attacks now have default start date; attempt to set end date before this start date
        data = dict(index='update_report_dates', report_title=report_title, end_date='2020-08-16')
        resp = await self.client.post('/rest', json=data)
        resp_json = await resp.json()
        # Check an unsuccessful response was sent
        error_msg, alert_user = resp_json.get('error'), resp_json.get('alert_user')
        self.assertTrue(resp.status == 500, msg='Out-of-range report end-date resulted in a non-500 response.')
        self.assertTrue('1 confirmed technique has start/end dates outside specified range' in error_msg,
                        msg='Error message for out-of-range report end-date is different than expected.')
        self.assertEqual(alert_user, 1, msg='User is not notified over out-of-range report end-date.')

    async def test_tech_missing_start_date(self):
        """Function to test attempting to update technique dates without a start-date value."""
        report_id, report_title = str(uuid4()), 'Kamigawa Tales: Unforgiving One'
        # Submit and analyse a test report
        await self.submit_test_report(dict(uid=report_id, title=report_title, url='kami.gawa',
                                           date_written='2022-08-16', current_status=ReportStatus.QUEUE.value),
                                      post_confirm_attack=True)
        # Attempt to call rest endpoint without a start date
        data = dict(index='update_attack_time', report_title=report_title, end_date='2020-08-16', mapping_list=[])
        resp = await self.client.post('/rest', json=data)
        resp_json = await resp.json()
        # Check an unsuccessful response was sent
        error_msg, alert_user = resp_json.get('error'), resp_json.get('alert_user')
        self.assertTrue(resp.status == 500, msg='Missing technique start date resulted in a non-500 response.')
        self.assertTrue('Technique Start Date missing' in error_msg,
                        msg='Error message for missing technique start date is different than expected.')
        self.assertEqual(alert_user, 1, msg='User is not notified over missing technique start date.')

    async def test_updating_technique_dates(self):
        """Function to test successfully setting technique start and end dates."""
        report_id, report_title = str(uuid4()), 'Kamigawa Tales: Kairi, the Swirling Sky'
        # Submit and analyse a test report
        await self.submit_test_report(
            dict(uid=report_id, title=report_title, url='kami.gawa', date_written='2022-08-16', start_date='2021-08-16',
                 end_date='2023-08-16', current_status=ReportStatus.QUEUE.value), post_confirm_attack=True)
        # Update a single technique from the report with a new start and end date
        hits = await self.db.get('report_sentence_hits', dict(report_uid=report_id, confirmed=self.db.val_as_true))
        data = dict(index='update_attack_time', report_title=report_title, start_date='2023-08-16',
                    end_date='2023-12-25', mapping_list=[hits[0][UID_KEY]])
        resp = await self.client.post('/rest', json=data)
        hits = await self.db.get('report_sentence_hits', dict(report_uid=report_id, confirmed=self.db.val_as_true))
        self.assertTrue(resp.status < 300, msg='Updating technique dates resulted in a non-200 response.')
        self.assertEqual(hits[0]['start_date'], '2023-08-16', msg='Start date not updated correctly.')
        self.assertEqual(hits[0]['end_date'], '2023-12-25', msg='End date not updated correctly.')
