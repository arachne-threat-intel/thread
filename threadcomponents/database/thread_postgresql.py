import logging
import os
import psycopg2
import psycopg2.extras

from .thread_db import ThreadDB
from getpass import getpass
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

DB_NAME = ''


def get_db_info():
    """Function to get database information from a user (launching Thread)."""
    global DB_NAME
    DB_NAME = input('Enter name of DB:\n')
    username = input('Enter DB-server username:\n')
    password = getpass('Enter DB-server password:\n')
    host = input('Enter DB-server host (leave blank/skip for localhost):\n') or '127.0.0.1'
    port = input('Enter DB-server port (check with command `pg_lsclusters`):\n')
    return username, password, host, port


def build_db(schema=os.path.join('threadcomponents', 'conf', 'schema.sql')):
    """The function to set up the Thread database (DB)."""
    # Begin by obtaining the text from the schema file
    with open(schema) as schema_opened:
        schema_text = schema_opened.read()
    # Ask for the required DB info/credentials to proceed
    username, password, host, port = get_db_info()
    # print() statements are used rather than logging for this function because it is not running via the launched app
    # Create the database itself
    _create_db(username, password, host, port)
    # Use the schema to generate a new schema for tables that need to have a copied structure
    copied_tables_schema = ThreadDB.generate_copied_tables(schema=schema_text)
    # Proceed to build both schemas
    _create_tables(username, password, host, port, schema=schema_text)
    _create_tables(username, password, host, port, schema=copied_tables_schema, is_partial=True)
    print('Build scripts completed; don\'t forget to GRANT permissions to less-privileged users where applicable.')


def _create_db(username, password, host, port):
    """The function to create the Thread DB on the server."""
    connection = None
    try:
        # Set up a connection using inputted credentials
        connection = psycopg2.connect(database='postgres', user=username, password=password, host=host, port=port)
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


def _create_tables(username, password, host, port, schema='', is_partial=False):
    """The function to create the tables in the Thread DB on the server."""
    # Booleans are not integers in PostgreSQL; replace any default boolean integers with True/False
    boolean_default = 'BOOLEAN DEFAULT'
    schema = schema.replace('%s 1' % boolean_default, '%s TRUE' % boolean_default)
    schema = schema.replace('%s 0' % boolean_default, '%s FALSE' % boolean_default)
    try:
        # Add expiry field - we only want to log an error if we are building the full schema
        schema = ThreadDB.add_column_to_schema(schema, 'reports', 'expires_on TIMESTAMP WITH TIME ZONE',
                                               log_error=(not is_partial))
    except ValueError as e:
        # Partial-schemas (e.g. backup tables) will most likely raise an error so ignore these
        if not is_partial:
            raise e
    connection = None
    try:
        # Set up a connection to the specified database
        connection = psycopg2.connect(database=DB_NAME, user=username, password=password, host=host, port=port)
        with connection:  # use 'with' here to commit transaction at the end of this block
            with connection.cursor() as cursor:
                cursor.execute(schema)  # run the parsed schema
        print('Schema successfully run.')
    # Ensure the connection closes if anything went wrong
    finally:
        if connection:
            connection.close()


class ThreadPostgreSQL(ThreadDB):
    def __init__(self):
        # Define the PostgreSQL function to find a substring position in a string
        function_name_map = dict()
        function_name_map[self.FUNC_STR_POS] = 'STRPOS'
        function_name_map[self.FUNC_TIME_NOW] = 'NOW'
        super().__init__(mapped_functions=function_name_map)
        self.username, self.password, self.host, self.port = get_db_info()

    @property
    def query_param(self):
        """Implements ThreadDB.query_param"""
        # '%s' is the query parameter: https://www.psycopg.org/docs/usage.html#passing-parameters-to-sql-queries
        return '%s'

    # PostgreSQL doesn't use integers for booleans: override the defaults
    @property
    def val_as_true(self):
        """Overrides ThreadDB.val_as_true"""
        return 'TRUE'

    @property
    def val_as_false(self):
        """Overrides ThreadDB.val_as_false"""
        return 'FALSE'

    async def build(self, schema, is_partial=False):
        """Implements ThreadDB.build()"""
        logging.warning('Re-building the database cannot be done when config \'db-engine\' is \'postgresql\'. '
                        'Please run `main.py --build-db` separately instead.')

    def _connection_wrapper(self, method, cursor_factory=None, return_success=False):
        """A function to execute a method that requires a db connection cursor."""
        # Blank variables for the connection, the return value and if the method was successful
        connection, return_val, success = None, None, True
        try:
            # Set up the connection
            connection = psycopg2.connect(database=DB_NAME, user=self.username, password=self.password,
                                          host=self.host, port=self.port)
            with connection:
                with connection.cursor(cursor_factory=cursor_factory) as cursor:
                    # Call the method with the cursor
                    return_val = method(cursor)
        except Exception as e:
            logging.error('Encountered error: ' + str(e))
            success = False
        # Ensure the connection closes if anything went wrong
        finally:
            if connection:
                connection.close()
        # If we're returning a success-boolean, return that; else return any value obtained
        return success if return_success else return_val

    async def _get_column_names(self, sql):
        """Implements ThreadDB._get_column_names()"""
        def cursor_select(cursor):
            # Execute the SQL query
            cursor.execute(sql)
            # Return the column names from the cursor description
            return [desc[0] for desc in cursor.description]
        return self._connection_wrapper(cursor_select, cursor_factory=psycopg2.extras.DictCursor)

    async def _execute_select(self, sql, parameters=None, single_col=False, on_fetch=None):
        """Implements ThreadDB._execute_select()"""
        def cursor_select(cursor):
            # Execute the SQL query with parameters or not
            if parameters is None:
                cursor.execute(sql)
            else:
                cursor.execute(sql, parameters)
            # Return the rows as dictionaries
            rows = cursor.fetchall()
            if callable(on_fetch):
                return on_fetch(rows)
            else:
                # psycopg2.extras.DictRow can be accessed with [int]; do so if not returning dictionary objects
                return [ix[0] for ix in rows] if single_col else [dict(ix) for ix in rows]
        return self._connection_wrapper(cursor_select, cursor_factory=psycopg2.extras.DictCursor)

    async def _execute_insert(self, sql, data):
        """Implements ThreadDB._execute_insert()"""
        def cursor_insert(cursor):
            # Execute the SQL statement with the data to be inserted
            cursor.execute(sql, tuple(data))
            return cursor.lastrowid
        return self._connection_wrapper(cursor_insert)

    async def _execute_update(self, sql, data):
        """Implements ThreadDB._execute_update()"""
        # Nothing extra do to or return: just execute the SQL statement with the data to update
        def cursor_update(cursor):
            # Execute the SQL statement with the data to be inserted
            cursor.execute(sql, tuple(data))
        return self._connection_wrapper(cursor_update)

    async def get_column_as_list(self, table, column):
        """Overrides ThreadDB.get_column_as_list()"""
        # Use the array() function to return the column as an object {array: <column values>}
        results = await self.raw_select('SELECT array(SELECT %s FROM %s)' % (column, table))
        return results[0]['array']  # Let a KeyError raise if 'array' doesn't work - this means the library changed

    async def run_sql_list(self, sql_list=None, return_success=True):
        """Implements ThreadDB.run_sql_list()"""
        def cursor_multiple_execute(cursor):
            # Execute each list item where the first part must be an SQL statement followed by optional parameters
            for item in sql_list:
                if item is None:  # skip None-items
                    continue
                elif len(item) == 1:
                    cursor.execute(item[0])
                elif len(item) == 2:
                    # execute() takes parameters as a tuple, ensure that is the case
                    parameters = item[1] if type(item[1]) == tuple else tuple(item[1])
                    cursor.execute(item[0], parameters)
        # Don't do anything if we don't have a list
        if not sql_list:
            return
        return self._connection_wrapper(cursor_multiple_execute, return_success=return_success)
