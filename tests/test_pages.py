import os

from tests.thread_app_test import ThreadAppTest


class TestPages(ThreadAppTest):
    """A test suite for checking Thread's pages."""
    DB_TEST_FILE = os.path.join('tests', 'threadtestpages.db')

    async def test_about_page(self):
        """Function to test the about page loads successfully."""
        resp = await self.client.get('/about')
        self.assertTrue(resp.status == 200, msg='About page failed to load successfully.')

    async def test_home_page(self):
        """Function to test the home page loads successfully."""
        resp = await self.client.get('/')
        self.assertTrue(resp.status == 200, msg='Home page failed to load successfully.')
