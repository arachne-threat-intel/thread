import os
import random

from tests.thread_app_test import ThreadAppTest
from threadcomponents.service.rest_svc import UID as UID_KEY
from uuid import uuid4


class TestIoCs(ThreadAppTest):
    """A test suite for checking Thread's IoC functionality."""
    DB_TEST_FILE = os.path.join('tests', 'threadtestiocs.db')
    TABLE = 'report_sentence_indicators_of_compromise'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.hyphens = cls.web_svc.HYPHENS
        cls.periods = cls.web_svc.PERIODS
        cls.quotes = cls.web_svc.QUOTES
        cls.bullet_points = cls.web_svc.BULLET_POINTS

    def dirty_ioc_text(self, ioc_text):
        """Adds characters to an IoC string which we hope will be removed."""
        leading_char_1 = random.choice(['*'] + self.bullet_points + self.hyphens)
        leading_char_2 = random.choice(['*'] + self.bullet_points + self.hyphens)
        leading_char_3 = random.choice(['*'] + self.bullet_points + self.hyphens)
        trailing_char_1 = random.choice(self.periods + self.hyphens)
        trailing_char_2 = random.choice(self.periods + self.hyphens)
        trailing_char_3 = random.choice(self.periods + self.hyphens)
        return '%s%s%s%s%s%s%s%s%s' % (leading_char_1, leading_char_2, leading_char_2, leading_char_3,
                                       ioc_text, trailing_char_1, trailing_char_2, trailing_char_3, trailing_char_2)

    async def check_denied_ioc(self, ioc_text, dirty_text=None):
        """Function to test responses when an IoC string cannot be flagged as an IoC."""
        report_id, report_title = str(uuid4()), 'Are You Not Entertain- Denied?'
        # Submit and analyse a test report; use dirty_text parameter when debugging previously-failed randomised strings
        text = dirty_text or [self.dirty_ioc_text(ioc_text)]
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
            self.fail('Text `%s` was able to be flagged as IoC.' % text[0])
        self.assertTrue(resp.status == 500, msg='Flagging unsuccessful IoC resulted in a non-500 response.')
        self.assertTrue('This cannot be flagged as an IoC' in error_msg,
                        msg='Error message for unsuccessful IoC is different than expected.')
        self.assertEqual(alert_user, 1, msg='User is not notified over unsuccessful IoC flagging.')

    async def check_allowed_ioc(self, ip_address, dirty_text=None, cleaned=None):
        """Function to test responses when an IoC string can be flagged as an IoC. Returns db info of IoC."""
        report_id, report_title = str(uuid4()), 'Are You Not Entertain- Allowed?'
        # Submit and analyse a test report
        text = dirty_text or [self.dirty_ioc_text(ip_address)]
        cleaned = cleaned or ip_address
        await self.submit_test_report(dict(uid=report_id, title=report_title, url='thumbs.up'), sentences=text)

        # Get the sentence-ID to use in the endpoint
        sentences = await self.db.get('report_sentences', equal=dict(report_uid=report_id))
        sen_id = sentences[0][UID_KEY]

        # Attempt to flag this sentence as an IoC
        data = dict(index='add_indicator_of_compromise', sentence_id=sen_id)
        resp = await self.client.post('/rest', json=data)
        self.assertTrue(resp.status < 300, msg='Flagging `%s` as an IoC resulted in a non-200 response.' % text[0])

        # Check IoC text is saved as expected in the db
        existing = await self.dao.get(self.TABLE, dict(report_id=report_id, sentence_id=sen_id))
        saved_ioc = existing[0]['refanged_sentence_text']
        self.assertEqual(cleaned, saved_ioc, '`%s` was not cleaned as expected before saved as IoC.' % text[0])
        return report_id, sen_id

    async def test_deny_link_local_ipv4(self):
        """Function to test a link-local IPv4 address cannot be flagged as an IoC."""
        await self.check_denied_ioc('169.254.12.32')

    async def test_deny_multicast_ipv4(self):
        """Function to test a multicast IPv4 address cannot be flagged as an IoC."""
        await self.check_denied_ioc('240.255.255.255')

    async def test_deny_private_ipv4(self):
        """Function to test a private IPv4 address cannot be flagged as an IoC."""
        await self.check_denied_ioc('10.16.5.5')
        await self.check_denied_ioc('localhost')
        some_bullet_points = self.bullet_points[4] + self.bullet_points[5] + self.bullet_points[4]
        await self.check_denied_ioc('127.0.0.1'.replace('.', some_bullet_points))

    async def test_deny_link_local_ipv6(self):
        """Function to test a link-local IPv6 address cannot be flagged as an IoC."""
        await self.check_denied_ioc('fe80::903a:1c1a:e802:11e4')

    async def test_deny_multicast_ipv6(self):
        """Function to test a multicast IPv6 address cannot be flagged as an IoC."""
        await self.check_denied_ioc('ff02::fb')

    async def test_deny_private_ipv6(self):
        """Function to test a private IPv6 address cannot be flagged as an IoC."""
        await self.check_denied_ioc('fd00::4:120/62')

    async def test_allow_public_ipv4(self):
        """Function to test a public IPv4 address can be flagged as an IoC."""
        testing = '192.30.252.0'
        await self.check_allowed_ioc(testing)
        some_bullet_points = self.bullet_points[1] + self.bullet_points[2] + self.bullet_points[3]
        await self.check_allowed_ioc(testing.replace('.', some_bullet_points), cleaned=testing)

    async def test_allow_public_ipv6(self):
        """Function to test a public IPv6 address can be flagged as an IoC."""
        await self.check_allowed_ioc('2603:1030:9:2c4::/62')

    async def test_allow_spacy_ip_address(self):
        """Function to test an IP address with whitespace can be flagged as an IoC."""
        await self.check_allowed_ioc(' 192 [.] 30 [.] 252 [.] 0 ', cleaned='192.30.252.0')

    async def test_allow_spacy_url(self):
        """Function to test a URL with whitespace can be flagged as an IoC."""
        testing = 'https://en.wikipedia.org/wiki/Barbie_(film)'.replace('_', ' ')
        await self.check_allowed_ioc(' %s ' % testing, cleaned=testing)

    async def test_url_with_hxxp(self):
        """Function to test a URL with 'hxxp' can be flagged as an IoC and is correctly edited."""
        testing = "https://en.wikipedia.org/wiki/Horse"
        await self.check_allowed_ioc(' %s ' % testing.replace('http', 'hxxp'), cleaned=testing)

    async def test_url_with_quotes(self):
        """Function to test a URL with quotes can be flagged as an IoC and is not over-edited."""
        q1, q2 = u'\u275D', u'\u275E'
        testing = f"https://en.wikipedia.org/wiki/I'm_Just_Ken?feelings={q1}kenergy{q2}&number="
        testing1 = testing + '10'
        await self.check_allowed_ioc(testing1, cleaned=testing1.replace(q1, '"').replace(q2, '"'))
        testing2 = testing + f"{q1}ten{q2}"
        await self.check_allowed_ioc(testing2, cleaned=testing2.replace(q1, '"').replace(q2, '"'))

    async def test_url_with_digits(self):
        """Function to test a URL with digits can be flagged as an IoC and is not over-edited."""
        await self.check_allowed_ioc('look192at30this252ta0da.my.ioc')

    async def test_hash_with_quotes(self):
        """Function to test a hash with quotes can be flagged as an IoC and is not over-edited."""
        await self.check_allowed_ioc('uWuHitcvVnC"du1Yo4c6hjQ==')

    async def test_allow_wildcard_url(self):
        """Function to test a wildcard URL can be flagged as an IoC."""
        await self.check_allowed_ioc('*.i-am.kenough')

    async def test_allow_non_ip_address(self):
        """Function to test regular text can be flagged as an IoC."""
        await self.check_allowed_ioc('I-want-this-to-be-my-IoC')

    async def test_deny_duplicate(self):
        """Function to test IoC entries are not duplicated."""
        report_id, sen_id = await self.check_allowed_ioc('I-want-this-to-be-my-IoC')
        data = dict(index='add_indicator_of_compromise', sentence_id=sen_id)
        await self.client.post('/rest', json=data)
        existing = await self.dao.get(self.TABLE, dict(report_id=report_id, sentence_id=sen_id))
        self.assertTrue(len(existing) == 1, msg='There are duplicate or missing IoC entries.')

    async def test_deny_empty_ioc(self):
        """Function to test cleaned text resulting in an empty string cannot be flagged as an IoC."""
        report_id, report_title = str(uuid4()), 'Are You Not Entertain- Empty?'
        # Submit and analyse a test report
        text = [self.dirty_ioc_text('')]
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
            self.fail('Special-characters IoC `%s` was able to be flagged as IoC.' % text[0])
        self.assertTrue(resp.status == 500, msg='Flagging empty IoC resulted in a non-500 response.')
        self.assertTrue('This text was cleaned and appeared to be empty afterwards' in error_msg,
                        msg='Error message for empty IoC is different than expected.')
        self.assertEqual(alert_user, 1, msg='User is not notified over flagging an empty IoC.')
