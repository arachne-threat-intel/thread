import os
import psycopg2

from .thread_db import ThreadDB
from contextlib import suppress
from getpass import getpass
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

DB_NAME = 'thread_db'


def build_db(schema=os.path.join('conf', 'schema.sql')):
    """The function to set up the Thread database (DB)."""
    username = input('Enter DB username: ')
    password = getpass('Enter DB password: ')
    host = input('Enter DB host (leave blank/skip for localhost): ') or '127.0.0.1'
    _create_db(username, password, host)
    _create_tables(username, password, host, schema)


def _create_db(username, password, host):
    """The function to create the Thread DB on the server."""
    connection = None
    try:
        # Set up a connection using inputted credentials
        connection = psycopg2.connect(database='postgres', user=username, password=password, host=host, port='5432')
        # First, check db is created - this cannot be done in a transaction so set autocommit isolation level
        connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        # Create the db on the server (ignoring if it's already created)
        with connection.cursor() as cursor:
            # noinspection PyUnresolvedReferences
            with suppress(psycopg2.errors.DuplicateDatabase):
                cursor.execute('CREATE DATABASE ' + DB_NAME)
    # Ensure the connection closes if anything went wrong
    finally:
        if connection:
            connection.close()


def _create_tables(username, password, host, schema):
    """The function to create the tables in the Thread DB on the server."""
    pass


class ThreadPostgreSQL(ThreadDB):

    async def build(self, schema):
        raise RuntimeError('build() cannot be called when config \'db-engine\' is \'postgresql\'. '
                           'Please run `main.py --build-db` separately instead.')
