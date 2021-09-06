import logging
import os
import psycopg2

from .thread_db import ThreadDB
from getpass import getpass
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

DB_NAME = ''


def get_db_info():
    """Function to get database information from a user (launching Thread)."""
    global DB_NAME
    DB_NAME = input('Enter DB name:\n')
    username = input('Enter DB username:\n')
    password = getpass('Enter DB password:\n')
    host = input('Enter DB host (leave blank/skip for localhost):\n') or '127.0.0.1'
    return username, password, host


def build_db(schema=os.path.join('conf', 'schema.sql')):
    """The function to set up the Thread database (DB)."""
    username, password, host = get_db_info()
    # print() statements are used rather than logging for this function because it is not running via the launched app
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
            try:
                cursor.execute('CREATE DATABASE ' + DB_NAME)
                print('Database %s created.' % DB_NAME)
            # noinspection PyUnresolvedReferences
            except psycopg2.errors.DuplicateDatabase:
                print('Database %s already created.' % DB_NAME)
    # Ensure the connection closes if anything went wrong
    finally:
        if connection:
            connection.close()


def _create_tables(username, password, host, schema_file):
    """The function to create the tables in the Thread DB on the server."""
    with open(schema_file) as schema_opened:
        schema = schema_opened.read()
    # Booleans are not integers in PostgreSQL; replace any default boolean integers with True/False
    boolean_default = 'BOOLEAN DEFAULT'
    schema = schema.replace('%s 1' % boolean_default, '%s TRUE' % boolean_default)
    schema = schema.replace('%s 0' % boolean_default, '%s FALSE' % boolean_default)
    connection = None
    try:
        # Set up a connection to the specified database
        connection = psycopg2.connect(database=DB_NAME, user=username, password=password, host=host, port='5432')
        with connection:  # use 'with' here to commit transaction at the end of this block
            with connection.cursor() as cursor:
                cursor.execute(schema)  # run the parsed schema
        print('Schema %s successfully run.' % schema_file)
    # Ensure the connection closes if anything went wrong
    finally:
        if connection:
            connection.close()


class ThreadPostgreSQL(ThreadDB):

    async def build(self, schema):
        logging.warning('Re-building the database cannot be done when config \'db-engine\' is \'postgresql\'. '
                        'Please run `main.py --build-db` separately instead.')
