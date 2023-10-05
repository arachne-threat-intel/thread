import os
import random

from tests.thread_app_test import ThreadAppTest
from threadcomponents.service.rest_svc import UID as UID_KEY
from uuid import uuid4


class TestIoCs(ThreadAppTest):
    """A test suite for checking Thread's IoC functionality."""
    DB_TEST_FILE = os.path.join('tests', 'threadtestiocs.db')
    TABLE = 'report_sentence_indicators_of_compromise'
    FIELD = 'refanged_sentence_text'

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

    async def create_report_with_sentence(self, text):
        """Function to create a test report with a test sentence and return the IDs of both."""
        report_id, report_title = str(uuid4()), 'Are You Not Entertain- Compromised?'
        # Submit and analyse a test report
        await self.submit_test_report(dict(uid=report_id, title=report_title, url='thumbs.down'), sentences=[text])

        # Get the sentence-ID to use in the endpoint
        sentences = await self.db.get('report_sentences', equal=dict(report_uid=report_id))
        sen_id = sentences[0][UID_KEY]
        return report_id, sen_id

    async def check_denied_ioc(self, text, suggest_and_save=False, dirty_text=None, report_id=None, sen_id=None):
        """Function to test responses when an IoC string cannot be flagged as an IoC."""
        if suggest_and_save:
            text = dirty_text or self.dirty_ioc_text(text)

        if not (report_id and sen_id):
            report_id, sen_id = await self.create_report_with_sentence(text)

        # Attempt to flag this sentence as an IoC
        if suggest_and_save:
            data = dict(index='suggest_and_save_ioc', sentence_id=sen_id)
        else:
            data = dict(index='add_indicator_of_compromise', sentence_id=sen_id, ioc_text=text)
        resp = await self.client.post('/rest', json=data)
        resp_json = await resp.json()
        # Check an unsuccessful response was sent
        error_msg, alert_user = None, None
        try:
            error_msg, alert_user = resp_json.get('error'), resp_json.get('alert_user')
        except AttributeError:
            self.fail('Text `%s` was able to be flagged as IoC.' % text)
        self.assertTrue(resp.status == 500, msg='Flagging unsuccessful IoC resulted in a non-500 response.')
        self.assertTrue('This cannot be flagged as an IoC' in error_msg,
                        msg='Error message for unsuccessful IoC is different than expected.')
        self.assertEqual(alert_user, 1, msg='User is not notified over unsuccessful IoC flagging.')

    async def check_allowed_ioc(self, text, suggest_and_save=False, dirty_text=None, cleaned=None, report_id=None,
                                sen_id=None):
        """Function to test responses when an IoC string can be flagged as an IoC. Returns db info of IoC."""
        expected_ioc = cleaned or text
        if suggest_and_save:
            text = dirty_text or self.dirty_ioc_text(text)

        if not (report_id and sen_id):
            report_id, sen_id = await self.create_report_with_sentence(text)

        # Attempt to flag this sentence as an IoC
        if suggest_and_save:
            data = dict(index='suggest_and_save_ioc', sentence_id=sen_id)
        else:
            data = dict(index='add_indicator_of_compromise', sentence_id=sen_id, ioc_text=text)
        resp = await self.client.post('/rest', json=data)
        resp_json = await resp.json()
        success_msg, alert_user = resp_json.get('info'), resp_json.get('alert_user')
        self.assertTrue(resp.status < 300, msg='Flagging `%s` as an IoC resulted in a non-200 response.' % text)
        self.assertTrue('The selected sentence has been flagged as an IoC' in success_msg,
                        msg='Message for successful IoC is different than expected.')
        self.assertEqual(alert_user, 1, msg='User is not notified over successful IoC flagging.')

        if suggest_and_save:
            ioc_text_resp = resp_json.get('ioc_text')
            self.assertEqual(ioc_text_resp, expected_ioc, msg='User is not given correct suggested-saved IoC.')

        # Check IoC text is saved as expected in the db
        existing = await self.dao.get(self.TABLE, dict(report_id=report_id, sentence_id=sen_id))
        self.assertEqual(expected_ioc, existing[0][self.FIELD], '`%s` was not saved as an IoC.' % expected_ioc)
        return report_id, sen_id

    async def check_suggested_ioc(self, ioc_text, dirty_text=None, cleaned=None):
        """Function to test responses when an IoC string is suggested."""
        # Use dirty_text parameter when debugging previously-failed randomised strings
        text = dirty_text or self.dirty_ioc_text(ioc_text)
        report_id, sen_id = await self.create_report_with_sentence(text)

        cleaned = cleaned or ioc_text
        # Request the suggested IoC-text for this sentence
        data = dict(index='suggest_indicator_of_compromise', sentence_id=sen_id)
        resp = await self.client.post('/rest', json=data)
        suggested_ioc = await resp.json()
        self.assertTrue(resp.status < 300, msg='Suggesting IoC from `%s` resulted in a non-200 response.' % text)
        self.assertEqual(cleaned, suggested_ioc, '`%s` was not cleaned as expected.' % text)

    async def test_deny_link_local_ipv4(self):
        """Function to test a link-local IPv4 address cannot be flagged as an IoC."""
        await self.check_denied_ioc('169.254.12.32')

    async def test_deny_multicast_ipv4(self):
        """Function to test a multicast IPv4 address cannot be flagged as an IoC."""
        await self.check_denied_ioc('240.255.255.255')

    async def test_deny_private_ipv4(self):
        """Function to test a private IPv4 address cannot be flagged as an IoC."""
        await self.check_denied_ioc('10.16.5.5')

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
        await self.check_allowed_ioc('192.30.252.0')

    async def test_suggest_ip_address(self):
        """Function to test suggesting a string with an IP address returns the IP address."""
        testing = '127.0.0.1'
        some_bullet_points = self.bullet_points[4] + self.bullet_points[5] + self.bullet_points[4]
        await self.check_suggested_ioc(testing.replace('.', some_bullet_points), cleaned=testing)

    async def test_allow_public_ipv6(self):
        """Function to test a public IPv6 address can be flagged as an IoC."""
        await self.check_allowed_ioc('2603:1030:9:2c4::/62')

    async def test_clean_spacy_ip_address(self):
        """Function to test a string of an IP address with whitespace is suggested as just the IP address."""
        await self.check_suggested_ioc(' 192 [.] 30 [.] 252 [.] 0 ', cleaned='192.30.252.0')

    async def test_clean_spacy_url(self):
        """Function to test a string of a URL with whitespace is suggested as just the URL."""
        link = 'https://en.wikipedia.org/wiki/Barbie?life=plastic#fantastic'
        testing = ' https : // en . wikipedia . org / wiki / Barbie ? life = plastic #fantastic '
        await self.check_suggested_ioc(testing, cleaned=link)

    async def test_clean_url_with_hxxp(self):
        """Function to test a URL with 'hxxp' is cleaned when suggested IoC text is requested."""
        testing = "https://en.wikipedia.org/wiki/Horse"
        await self.check_suggested_ioc(' %s ' % testing.replace('http', 'hxxp'), cleaned=testing)

    async def test_clean_url_with_quotes(self):
        """Function to test a URL with quotes is cleaned when suggested IoC text is requested."""
        q1, q2 = u'\u275D', u'\u275E'
        testing = f"{q1}https://en.wikipedia.org/wiki/I'm_Just_Ken{q2}"
        await self.check_suggested_ioc(testing, cleaned=testing.replace(q1, '').replace(q2, ''))

    async def test_clean_url_with_digits(self):
        """Function to test a URL with digits is not over-edited when suggested IoC text is requested."""
        await self.check_suggested_ioc('look192at30this252ta0da.my.ioc')

    async def test_clean_hash(self):
        """Function to test a hash is not over-edited when suggested IoC text is requested."""
        await self.check_suggested_ioc('uWuHitcvVnCdu1Yo4c6hjQ==')

    async def test_allow_non_ip_address(self):
        """Function to test regular text can be flagged as an IoC."""
        await self.check_allowed_ioc('I-want-this-to-be-my-IoC')

    async def test_clean_defanged_url(self):
        """Function to test a defanged URL is cleaned when suggested IoC text is requested."""
        await self.check_suggested_ioc('watch[.]me[@]dance(dot)the[dot]night(.)away',
                                       cleaned='watch.me@dance.the.night.away')
        await self.check_suggested_ioc('https [ : ] // dance ( dot ) the [ dot ] night ( . ) away',
                                       cleaned='https://dance.the.night.away')

    async def test_deny_duplicate(self):
        """Function to test IoC entries are not duplicated."""
        testing = 'I-want-to-be-your-canary'
        replacement = 'I-want-this-to-be-my-IoC'
        report_id, sen_id = await self.check_allowed_ioc(testing)
        data = dict(index='add_indicator_of_compromise', sentence_id=sen_id, ioc_text=replacement)
        await self.client.post('/rest', json=data)

        existing = await self.dao.get(self.TABLE, dict(report_id=report_id, sentence_id=sen_id))
        saved_ioc = existing[0][self.FIELD]
        self.assertTrue(len(existing) == 1, msg='There are duplicate or missing IoC entries.')
        self.assertNotEqual(saved_ioc, replacement, msg='The IoC was unexpectedly updated.')
        self.assertEqual(saved_ioc, testing, msg='The IoC was unexpectedly updated.')

    async def test_update_ioc_text(self):
        """Function to test when a user updates IoC text."""
        testing = 'pink!'
        replacement = 'red!'
        report_id, sen_id = await self.check_allowed_ioc(testing)
        data = dict(index='update_indicator_of_compromise', sentence_id=sen_id, ioc_text=replacement)
        resp = await self.client.post('/rest', json=data)
        resp_json = await resp.json()

        existing = await self.dao.get(self.TABLE, dict(report_id=report_id, sentence_id=sen_id))
        saved_ioc = existing[0][self.FIELD]
        self.assertTrue(len(existing) == 1, msg='There are duplicate or missing IoC entries.')
        self.assertNotEqual(saved_ioc, testing, msg='The IoC was not updated.')
        self.assertEqual(saved_ioc, replacement, msg='The IoC was not updated.')

        success_msg, alert_user = resp_json.get('info'), resp_json.get('alert_user')
        self.assertTrue(resp.status < 300, msg='Updating IoC-text resulted in a non-200 response.')
        self.assertTrue('This sentence-IoC text has been updated' in success_msg,
                        msg='Message for updating IoC-text is different than expected.')
        self.assertEqual(alert_user, 1, msg='User is not notified over successful IoC-text update.')

    async def test_update_ioc_text_with_empty_string(self):
        """Function to test when a user updates IoC text with an empty string."""
        async def check_not_updated(replacement):
            data = dict(index='update_indicator_of_compromise', sentence_id=sen_id, ioc_text=replacement)
            await self.client.post('/rest', json=data)
            existing = await self.dao.get(self.TABLE, dict(report_id=report_id, sentence_id=sen_id))
            saved_ioc = existing[0][self.FIELD]
            self.assertTrue(len(existing) == 1, msg='There are duplicate or missing IoC entries.')
            self.assertNotEqual(saved_ioc, replacement, msg='The IoC was unexpectedly updated.')
            self.assertEqual(saved_ioc, testing, msg='The IoC was unexpectedly updated.')

        testing = '~feel-the-kenergy~'
        report_id, sen_id = await self.check_allowed_ioc(testing)
        await check_not_updated('')
        await check_not_updated('      ')

    async def test_remove_ioc(self):
        """Function to test when a user removes IoC flag."""
        report_id, sen_id = await self.check_allowed_ioc('beach~~~')
        data = dict(index='remove_indicator_of_compromise', sentence_id=sen_id)
        resp = await self.client.post('/rest', json=data)
        resp_json = await resp.json()

        existing = await self.dao.get(self.TABLE, dict(report_id=report_id, sentence_id=sen_id))
        self.assertTrue(len(existing) == 0, msg='IoC-flag on sentence was not removed.')

        success_msg, alert_user = resp_json.get('info'), resp_json.get('alert_user')
        self.assertTrue(resp.status < 300, msg='Removing IoC-flag resulted in a non-200 response.')
        self.assertTrue('The selected sentence is no longer flagged as an IoC' in success_msg,
                        msg='Message for removing IoC-flag is different than expected.')
        self.assertEqual(alert_user, 1, msg='User is not notified over successful IoC-flag removal.')

    async def test_sentence_context_returns_ioc(self):
        """Function to test sentence-data includes IoC text."""
        testing = '*I-am-Kenough*'
        report_id, sen_id = await self.check_allowed_ioc(testing)

        data = dict(index='sentence_context', sentence_id=sen_id)
        resp = await self.client.post('/rest', json=data)
        sen_data = await resp.json()
        self.assertEqual(sen_data['ioc'], testing, msg='IoC-text is not returned with sentence-context.')

        data = dict(index='remove_indicator_of_compromise', sentence_id=sen_id)
        await self.client.post('/rest', json=data)

        data = dict(index='sentence_context', sentence_id=sen_id)
        resp = await self.client.post('/rest', json=data)
        sen_data = await resp.json()
        self.assertFalse(sen_data['ioc'], msg='IoC-text from sentence-context is not empty after removal.')

    async def test_suggest_and_save_ioc(self):
        """Function to test suggest-and-save IoC."""
        await self.check_allowed_ioc('d414d90f656356636d6d632c8bae3731', suggest_and_save=True)

    async def test_error_suggest_and_save_does_not_override_valid_ioc(self):
        """Function to test an unsuccessful suggest-and-save IoC does not affect previous IoC text."""
        valid_ioc = 'f6d49fcb5f29fbe24a0424fa610d62b3'
        denied_ioc = self.dirty_ioc_text('240.255.255.255')

        # Create and save a sentence which would be invalid as an IoC but give it valid IoC text
        report_id, sen_id = await self.create_report_with_sentence(denied_ioc)
        await self.check_allowed_ioc(valid_ioc, report_id=report_id, sen_id=sen_id)

        # Check suggest-&-save does not save initial invalid IoC-sentence as an IoC
        await self.check_denied_ioc(None, suggest_and_save=True, dirty_text=denied_ioc,
                                    report_id=report_id, sen_id=sen_id)

        # Check initially-saved valid IoC has not been changed in the db
        existing = await self.dao.get(self.TABLE, dict(report_id=report_id, sentence_id=sen_id))
        self.assertEqual(valid_ioc, existing[0][self.FIELD], 'IoC value changed after suggest-&-save.')
