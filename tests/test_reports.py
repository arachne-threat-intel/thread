import os

from tests.thread_app_test import ThreadAppTest
from threadcomponents.service.rest_svc import ReportStatus, UID as UID_KEY
from uuid import uuid4
from urllib.parse import quote


class TestReports(ThreadAppTest):
    """A test suite for checking report actions."""
    DB_TEST_FILE = os.path.join('tests', 'threadtestreport.db')

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

    async def test_incorrect_rest_endpoint(self):
        """Function to test incorrect REST endpoints do not result in a server error."""
        # Two examples of bad request data to test
        invalid_index = dict(index='insert_report!!!', data='data.doesnt.matter')
        no_index_supplied = dict(woohoo='send me!')
        resp = await self.client.post('/rest', json=invalid_index)
        self.assertTrue(resp.status == 404, msg='Incorrect `index` parameter resulted in a non-404 response.')
        resp = await self.client.post('/rest', json=no_index_supplied)
        self.assertTrue(resp.status == 404, msg='Missing `index` parameter resulted in a non-404 response.')

    async def test_update_queue(self):
        """Function to test the queue is updated with a single submission."""
        # Request data to test
        test_data = dict(index='insert_report', url='twinkle.twinkle', title='Little Star')
        # Check internal queues before submission
        q1 = self.rest_svc.queue
        q2 = self.rest_svc.queue_map
        initial_queue_size_1 = q1.qsize()
        initial_queue_size_2 = len(q2.get('public', []))
        # Begin relevant patches
        await self.patches_on_insert()
        # Check submitting a single report is successful
        resp = await self.client.post('/rest', json=test_data)
        self.assertTrue(resp.status < 300, msg='A single report submission resulted in a non-200 response.')
        # Check the internal queues after this submission
        new_queue_size_1 = q1.qsize()
        new_queue_size_2 = len(q2.get('public', []))
        self.assertEqual(new_queue_size_1, initial_queue_size_1 + 1, msg='rest_svc.queue updated incorrectly.')
        self.assertEqual(new_queue_size_2, initial_queue_size_2 + 1, msg='rest_svc.queue_map updated incorrectly.')

    async def test_queue_limit(self):
        """Function to test the queue limit works correctly."""
        # Given the randomised queue limit for this test, obtain it and create a limit-exceeding amount of data
        limit = self.rest_svc_with_limit.QUEUE_LIMIT
        # Populate some test reports that will exceed the queue's limit
        csv_str = 'title,url\n'
        for n in range(limit + 1):
            title, url = ('title%s' % n), ('url%s' % n)
            csv_str = csv_str + title + ',' + url + '\n'
        data = dict(index='insert_csv', file=csv_str)
        # Begin relevant patches
        await self.patches_on_insert()

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
        uneven_columns = dict(file='title,url\nt1,url.1\nt2,url.2,url.3\n')
        urls_missing = dict(file='title,url\nt1,\nt2,\n')
        empty_val = dict(file='title,url\n    ,url.1\nt2,url.2\n')
        # The test cases paired with expected error messages
        col_error = 'Two columns have not been specified'
        missing_text = 'CSV is missing text in at least one row'
        tests = [(wrong_columns, col_error), (too_many_columns, col_error), (wrong_param, 'Error inserting report(s)'),
                 (uneven_columns, 'Could not parse file'), (urls_missing, missing_text), (empty_val, missing_text)]
        for test_data, predicted_msg in tests:
            # Call the CSV REST endpoint with the malformed data and check the response
            data = dict(index='insert_csv')
            data.update(test_data)
            resp = await self.client.post('/rest', json=data)
            resp_json = await resp.json()
            error_msg = resp_json.get('error')
            self.assertTrue(resp.status >= 400, msg='Malformed CSV data resulted in successful response.')
            self.assertTrue(predicted_msg in error_msg, msg='Malformed CSV error message formed incorrectly.')

    async def test_empty_parameters(self):
        """Function to test the behaviour of submitting a report with empty parameters."""
        # Request data to test
        full_test_data = dict(index='insert_report', url='twinkle.twinkle.2', title='How I Wonder')
        # Begin relevant patches
        await self.patches_on_insert()
        for argument in ['url', 'title']:
            # Replace parameter with empty string
            test_data = dict(full_test_data)
            test_data[argument] = '    '
            # Submit the report and test outcome
            resp = await self.client.post('/rest', json=test_data)
            resp_json = await resp.json()
            error_msg = resp_json.get('error')
            predicted_msg = 'Missing value for %s.' % argument
            self.assertTrue(resp.status >= 400, msg='Empty %s resulted in successful response.' % argument)
            self.assertTrue(predicted_msg in error_msg, msg='Error message formed incorrectly for empty %s.' % argument)

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

    async def test_add_invalid_attack(self):
        """Function to test adding an invalid attack to a sentence."""
        report_id, attack_id = str(uuid4()), 's00001'
        # Submit and analyse a test report
        await self.submit_test_report(dict(uid=report_id, title='Analyse This!', url='analysing.this',
                                           current_status=ReportStatus.QUEUE.value))
        # Pick any sentence from this report
        sentences = await self.db.get('report_sentences', equal=dict(report_uid=report_id))
        sen_id = sentences[0][UID_KEY]
        # Proceed to add an attack
        data = dict(index='add_attack', sentence_id=sen_id, attack_uid=attack_id)
        resp = await self.client.post('/rest', json=data)
        resp_json = await resp.json()
        # Check an unsuccessful response was sent
        error_msg = resp_json.get('error')
        self.assertTrue(resp.status == 500, msg='Adding an invalid attack resulted in a non-500 response.')
        self.assertTrue("'requiem' is not in the current Att%ck framework" in error_msg,
                        msg='A different error appeared for adding an invalid attack to a report-sentence.')

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
