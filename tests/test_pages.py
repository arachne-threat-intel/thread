import os

from tests.thread_app_test import ThreadAppTest


class TestPages(ThreadAppTest):
    """A test suite for checking Thread's pages."""
    DB_TEST_FILE = os.path.join('tests', 'threadtestpages.db')

    async def test_using_thread_page(self):
        """Function to test the Using-Thread page loads successfully."""
        resp = await self.client.get('/using-thread')
        self.assertTrue(resp.status == 200, msg='Using-Thread page failed to load successfully.')

    async def test_home_page(self):
        """Function to test the home page loads successfully."""
        resp = await self.client.get('/')
        self.assertTrue(resp.status == 200, msg='Home page failed to load successfully.')

    async def test_how_it_works_page(self):
        """Function to test the How Thread Works page loads successfully."""
        resp = await self.client.get('/how-thread-works')
        self.assertTrue(resp.status == 200, msg='How Thread Works page failed to load successfully.')
