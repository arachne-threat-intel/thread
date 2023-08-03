import os
import random

from tests.thread_app_test import ThreadAppTest
from threadcomponents.service.rest_svc import UID as UID_KEY
from uuid import uuid4


class TestIoCs(ThreadAppTest):
    """A test suite for checking Thread's IoC functionality."""
    DB_TEST_FILE = os.path.join('tests', 'threadtestiocs.db')

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.hyphens = cls.web_svc.HYPHENS
        cls.periods = cls.web_svc.PERIODS
        cls.quotes = cls.web_svc.QUOTES
        cls.bullet_points = cls.web_svc.BULLET_POINTS

    def dirty_ip_address(self, ip_address):
        """Adds characters to an IP address which we hope will be removed."""
        leading_char_1 = random.choice(['*'] + self.bullet_points + self.hyphens)
        leading_char_2 = random.choice(['*'] + self.bullet_points + self.hyphens)
        leading_char_3 = random.choice(['*'] + self.bullet_points + self.hyphens)
        trailing_char_1 = random.choice(self.periods + self.hyphens)
        trailing_char_2 = random.choice(self.periods + self.hyphens)
        trailing_char_3 = random.choice(self.periods + self.hyphens)
        return '%s%s%s%s%s%s%s%s%s' % (leading_char_1, leading_char_2, leading_char_2, leading_char_3,
                                       ip_address, trailing_char_1, trailing_char_2, trailing_char_3, trailing_char_2)

    async def check_denied_ip_address_ioc(self, ip_address):
        """Function to test responses when an IP address cannot be flagged as an IoC."""
        report_id, report_title = str(uuid4()), 'Are You Not Entertain- Denied?'
        # Submit and analyse a test report
        text = [self.dirty_ip_address(ip_address)]
        await self.submit_test_report(dict(uid=report_id, title=report_title, url='thumbs.down'), sentences=text)

        # Get the sentence-ID to use in the endpoint
        sentences = await self.db.get('report_sentences', equal=dict(report_uid=report_id))
        sen_id = sentences[0][UID_KEY]

        # Attempt to flag this sentence as an IoC
        data = dict(index='add_indicator_of_compromise', sentence_id=sen_id)
        resp = await self.client.post('/rest', json=data)
        resp_json = await resp.json()
        # Check an unsuccessful response was sent
        error_msg, alert_user = None, None
        try:
            error_msg, alert_user = resp_json.get('error'), resp_json.get('alert_user')
        except AttributeError:
            self.fail('IP address `%s` was able to be flagged as IoC.' % ip_address)
        self.assertTrue(resp.status == 500, msg='Flagging unsuccessful IoC resulted in a non-500 response.')
        self.assertTrue('This cannot be flagged as an IoC' in error_msg,
                        msg='Error message for unsuccessful IoC is different than expected.')
        self.assertEqual(alert_user, 1, msg='User is not notified over unsuccessful IoC flagging.')

    async def test_deny_link_local_ipv4(self):
        """Function to test a link-local IPv4 address cannot be flagged as an IoC."""
        await self.check_denied_ip_address_ioc('169.254.12.32')

    async def test_deny_multicast_ipv4(self):
        """Function to test a multicast IPv4 address cannot be flagged as an IoC."""
        await self.check_denied_ip_address_ioc('240.255.255.255')

    async def test_deny_private_ipv4(self):
        """Function to test a private IPv4 address cannot be flagged as an IoC."""
        await self.check_denied_ip_address_ioc('10.16.5.5')
        await self.check_denied_ip_address_ioc('localhost')

    async def test_deny_link_local_ipv6(self):
        """Function to test a link-local IPv6 address cannot be flagged as an IoC."""
        await self.check_denied_ip_address_ioc('fe80::903a:1c1a:e802:11e4')

    async def test_deny_multicast_ipv6(self):
        """Function to test a multicast IPv6 address cannot be flagged as an IoC."""
        await self.check_denied_ip_address_ioc('ff02::fb')

    async def test_deny_private_ipv6(self):
        """Function to test a private IPv6 address cannot be flagged as an IoC."""
        await self.check_denied_ip_address_ioc('fd00::4:120')
