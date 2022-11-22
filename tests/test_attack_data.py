import os

from tests.thread_app_test import ThreadAppTest


class TestAttackData(ThreadAppTest):
    """A test suite for checking our handling of attack-data."""
    DB_TEST_FILE = os.path.join('tests', 'threadtestattackdata.db')

    async def test_attack_list(self):
        """Function to test the attack list for the dropdown was created successfully."""
        # For our test attack data, we predict 2 will not be sub attacks (no Txx.xx TID) and 1 will be
        predicted = [dict(uid='d99999', name='Drain', tid='T1029', inactive=0, parent_tid=None, parent_name=None),
                     dict(uid='f12345', name='Fire', tid='T1562', inactive=0, parent_tid=None, parent_name=None),
                     dict(uid='f32451', name='Firaga', tid='T1562.004', inactive=0, parent_tid='T1562', parent_name='Fire')]
        # The generated dropdown list to check against our prediction
        result = self.web_api.attack_dropdown_list
        for attack_dict in predicted:
            self.assertTrue(attack_dict in result, msg='Attack %s was expected but not present.' % str(attack_dict))
        # Check that inactive attacks are in the database but not in the dropdown list
        inactive_attack_all = await self.db.get('attack_uids', equal=dict(inactive=1))
        for inactive_attack in inactive_attack_all:
            self.assertFalse(inactive_attack in result, msg='Inactive attack was found in dropdown list.')

    async def test_update_attacks(self):
        """Function to test when new attacks are added to the database."""
        # Create a new attack to mock being added; confirm it is not already in the database
        new_attack = dict(uid='b12345', tid='T1489', name='Blizzard')
        attacks = await self.db.get('attack_uids')
        if (new_attack in attacks) or (new_attack in self.web_api.attack_dropdown_list):
            self.skipTest('Could not test added attacks as database has specified attack already.')
        # Mock the retrieval of current Att%ck data to be this new attack and call the update method
        self.mock_current_attack_data(attack_list=[new_attack])
        await self.web_api.fetch_and_update_attack_data()
        # Re-obtain the attacks in the database and check the new attack is in the db and dropdown-list
        attacks = await self.db.get('attack_uids')
        # Tweak original attack-dict to be how they would be in the db and dropdown-list before assertions
        in_db = dict(new_attack, inactive=0)
        in_dropdown_list = dict(new_attack, inactive=0, parent_tid=None, parent_name=None)
        self.assertTrue(in_db in attacks, 'New attack did not appear in database.')
        self.assertTrue(in_dropdown_list in self.web_api.attack_dropdown_list,
                        'New attack did not appear in web-dropdown-list.')
