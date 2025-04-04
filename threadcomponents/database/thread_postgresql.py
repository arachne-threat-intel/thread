import logging
import os
import psycopg

from .thread_db import ThreadDB
from getpass import getpass
from psycopg.rows import dict_row, tuple_row


def get_connection_string(host, port, database, user, password):
    """Function to get the connection-string for the database."""
    return f"host='{host or ''}' port='{port or ''}' dbname='{database}' user='{user}' password='{password}'"


def get_db_info():
    """Function to get database information from a user (launching Thread)."""
    db_name = input("Enter name of DB:\n")
    username = input("Enter DB-server username:\n")
    password = getpass("Enter DB-server password:\n")
    host = input("Enter DB-server host (leave blank/skip for localhost):\n") or "127.0.0.1"
    port = input("Enter DB-server port (check with command `pg_lsclusters`):\n")
    return db_name, username, password, host, port


def build_db(schema):
    """The function to set up the Thread database (DB)."""
    schema = schema or os.path.join("threadcomponents", "conf", "schema.sql")

    # Begin by obtaining the text from the schema file
    with open(schema) as schema_opened:
        schema_text = schema_opened.read()

    # Ask for the required DB info/credentials to proceed
    db_name, username, password, host, port = get_db_info()

    # print() statements are used rather than logging for this function because it is not running via the launched app
    # Create the database and its tables
    _create_db(db_name, username, password, host, port)

    # Use the schema to generate a new schema for tables that need to have a copied structure
    copied_tables_schema = ThreadDB.generate_copied_tables(schema=schema_text)
    _create_tables(db_name, username, password, host, port, schema=schema_text)
    _create_tables(db_name, username, password, host, port, schema=copied_tables_schema, is_partial=True)

    print("Build scripts completed; don't forget to GRANT permissions to less-privileged users where applicable.")


def _create_db(db_name, username, password, host, port):
    """The function to create the Thread DB on the server."""
    # Set up and use a connection-string using inputted credentials
    conn_info = get_connection_string(host=host, port=port, database="postgres", user=username, password=password)
    try:
        with psycopg.connect(conninfo=conn_info, autocommit=True) as connection:
            with connection.cursor() as cursor:
                try:
                    cursor.execute(f"CREATE DATABASE {db_name}")
                    print(f"Database {db_name} created.")

                except psycopg.errors.DuplicateDatabase:
                    print(f"Database {db_name} already exists.")

    except Exception as e:
        logging.error(f"Encountered error: {e}")


def _create_tables(db_name, username, password, host, port, schema="", is_partial=False):
    """The function to create the tables in the Thread DB on the server."""
    # Booleans are not integers in PostgreSQL; replace any default boolean integers with True/False
    boolean_default = "BOOLEAN DEFAULT"
    schema = schema.replace(f"{boolean_default} 1", f"{boolean_default} TRUE")
    schema = schema.replace(f"{boolean_default} 0", f"{boolean_default} FALSE")

    # Keyword arguments for when we want to log an error pending if we are building the full schema
    not_partial_log = dict(log_error=(not is_partial))
    partial_log = dict(log_error=is_partial)
    start_date_field = "start_date TIMESTAMP WITH TIME ZONE"
    end_date_field = "end_date TIMESTAMP WITH TIME ZONE"

    # (1) Table, (2) SQL statement for field, (3) whether we want to log errors, (4) whether we are ignoring ValueErrors
    schema_updates = [
        # (3) is not-partial because we only want to log an error if we are building the full schema
        # (4) is if partial because these tables are only in full schema (ignore ValueError if not full schema)
        ("reports", "expires_on TIMESTAMP WITH TIME ZONE", not_partial_log, is_partial),
        ("reports", "date_written TIMESTAMP WITH TIME ZONE", not_partial_log, is_partial),
        ("reports", start_date_field, not_partial_log, is_partial),
        ("reports", end_date_field, not_partial_log, is_partial),
        ("report_sentence_hits", start_date_field, not_partial_log, is_partial),
        ("report_sentence_hits", end_date_field, not_partial_log, is_partial),
        # (3) and (4) are inverse above because report_sentence_hits_initial is from partial schema
        ("report_sentence_hits_initial", start_date_field, partial_log, not is_partial),
        ("report_sentence_hits_initial", end_date_field, partial_log, not is_partial),
    ]

    for table, sql_field, kwargs, ignore_value_error in schema_updates:
        try:
            # Add the field from the schema_updates list
            if kwargs:
                schema = ThreadDB.add_column_to_schema(schema, table, sql_field, **kwargs)
            else:
                schema = ThreadDB.add_column_to_schema(schema, table, sql_field)
        except ValueError as e:
            if not ignore_value_error:
                raise e

    conn_info = get_connection_string(host=host, port=port, database=db_name, user=username, password=password)
    try:
        with psycopg.connect(conninfo=conn_info) as connection:
            with connection.cursor() as cursor:
                cursor.execute(schema)

        print("Schema successfully run.")

    except Exception as e:
        logging.error(f"Encountered error: {e}")


class ThreadPostgreSQL(ThreadDB):
    IS_POSTGRESQL = True
    db_name = None

    def __init__(self, db_connection_func=None):
        # Define the PostgreSQL function to find a substring position in a string
        function_name_map = dict()
        function_name_map[self.FUNC_STR_POS] = "STRPOS"
        function_name_map[self.FUNC_TIME_NOW] = "NOW"
        function_name_map[self.FUNC_DATE_TO_STR] = "TO_CHAR"
        super().__init__(mapped_functions=function_name_map)
        db_connection_func = db_connection_func if callable(db_connection_func) else get_db_info
        self.db_name, self.username, self.password, self.host, self.port = db_connection_func()

    @property
    def query_param(self):
        """Implements ThreadDB.query_param"""
        # '%s' is the query parameter: https://www.psycopg.org/docs/usage.html#passing-parameters-to-sql-queries
        return "%s"

    # PostgreSQL doesn't use integers for booleans: override the defaults
    @property
    def val_as_true(self):
        """Overrides ThreadDB.val_as_true"""
        return "TRUE"

    @property
    def val_as_false(self):
        """Overrides ThreadDB.val_as_false"""
        return "FALSE"

    async def build(self, schema, is_partial=False):
        """Implements ThreadDB.build()"""
        logging.warning(
            "Re-building the database cannot be done when config 'db-engine' is 'postgresql'. "
            "Please run `main.py --build-db` separately instead."
        )

    def _connection_wrapper(self, method, row_factory=None, return_success=False):
        """A function to execute a method that requires a db connection cursor."""

        # Blank variables for the return value and if the method was successful
        return_val, success = None, True
        conn_info = get_connection_string(
            host=self.host,
            port=self.port,
            database=self.db_name,
            user=self.username,
            password=self.password,
        )

        try:
            with psycopg.connect(conninfo=conn_info) as connection:
                with connection.cursor(row_factory=row_factory) as cursor:
                    return_val = method(cursor)

        except Exception as e:
            logging.error(f"Encountered error: {e}")
            success = False

        # If we're returning a success-boolean, return that; else return any value obtained
        return success if return_success else return_val

    async def _get_column_names(self, sql):
        """Implements ThreadDB._get_column_names()"""

        def cursor_select(cursor):
            # Execute the SQL query
            cursor.execute(sql)
            # Return the column names from the cursor description
            return [desc[0] for desc in cursor.description]

        return self._connection_wrapper(cursor_select, row_factory=dict_row)

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
                # psycopg.rows.tuple_row can be accessed with [int]; do so if not returning dictionary objects
                return [ix[0] for ix in rows] if single_col else [dict(ix) for ix in rows]

        return self._connection_wrapper(cursor_select, row_factory=tuple_row if single_col else dict_row)

    async def _execute_insert(self, sql, data):
        """Implements ThreadDB._execute_insert()"""

        def cursor_insert(cursor):
            # If needing to return newly-inserted data, update the query: https://github.com/psycopg/psycopg/issues/169
            cursor.execute(sql, tuple(data))

        return self._connection_wrapper(cursor_insert)

    async def _execute_update(self, sql, data):
        """Implements ThreadDB._execute_update()"""

        def cursor_update(cursor):
            cursor.execute(sql, tuple(data))

        return self._connection_wrapper(cursor_update)

    async def get_column_as_list(self, table, column):
        """Overrides ThreadDB.get_column_as_list()"""
        # Use the array() function to return the column as an object {array: <column values>}
        results = await self.raw_select(f"SELECT array(SELECT {column} FROM {table})")
        return results[0]["array"]  # Let a KeyError raise if 'array' doesn't work - this means the library changed

    async def run_sql_list(self, sql_list=None, return_success=True):
        # Don't do anything if we don't have a list
        if not sql_list:
            return

        def cursor_multiple_execute(cursor):
            # Execute each list item where the first part must be an SQL statement followed by optional parameters
            for item in sql_list:
                if item is None:  # skip None-items
                    continue

                if len(item) == 1:
                    cursor.execute(item[0])
                elif len(item) == 2:
                    # execute() takes parameters as a tuple, ensure that is the case
                    parameters = item[1] if isinstance(item[1], tuple) else tuple(item[1])
                    cursor.execute(item[0], parameters)

        return self._connection_wrapper(cursor_multiple_execute, return_success=return_success)
