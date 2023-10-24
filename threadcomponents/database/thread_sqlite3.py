# NOTICE: As required by the Apache License v2.0, this notice is to state this file has been modified by Arachne Digital
# This file has been renamed from `tram_relation.py`
# To see its full history, please use `git log --follow <filename>` to view previous commits and additional contributors

import logging
import sqlite3

from .thread_db import ThreadDB

ENABLE_FOREIGN_KEYS = 'PRAGMA foreign_keys = ON;'


class ThreadSQLite(ThreadDB):
    IS_SQL_LITE = True

    def __init__(self, database):
        function_name_map = dict()
        function_name_map[self.FUNC_TIME_NOW] = 'DATETIME'
        super().__init__(mapped_functions=function_name_map)
        self.database = database

    @property
    def query_param(self):
        """Implements ThreadDB.query_param"""
        # '?' is the query parameter: https://docs.python.org/3/library/sqlite3.html#sqlite3-placeholders
        return '?'

    async def build(self, schema, is_partial=False):
        """Implements ThreadDB.build()"""
        # Ensure the foreign-keys line is prepended to the schema
        schema = ENABLE_FOREIGN_KEYS + '\n' + schema
        # Keyword arguments for when we want to log an error pending if we are building the full schema
        not_partial_log = dict(log_error=(not is_partial))
        partial_log = dict(log_error=is_partial)
        # sqlite3 does not support date fields (see 2.2. here: https://www.sqlite.org/datatype3.html)
        start_date_field, end_date_field = 'start_date TEXT', 'end_date TEXT'
        # Explanation of parameters can be found in comments in thread_postgresql._create_tables()
        schema_updates = [
            ('reports', 'expires_on TEXT', not_partial_log, is_partial),
            ('reports', 'date_written TEXT', not_partial_log, is_partial),
            ('reports', start_date_field, not_partial_log, is_partial),
            ('reports', end_date_field, not_partial_log, is_partial),
            ('report_sentence_hits', start_date_field, not_partial_log, is_partial),
            ('report_sentence_hits', end_date_field, not_partial_log, is_partial),
            ('report_sentence_hits_initial', start_date_field, partial_log, not is_partial),
            ('report_sentence_hits_initial', end_date_field, partial_log, not is_partial)
        ]
        for table, sql_field, kwargs, ignore_value_error in schema_updates:
            try:
                # Add the field from the schema_updates list
                if kwargs:
                    schema = self.add_column_to_schema(schema, table, sql_field, **kwargs)
                else:
                    schema = self.add_column_to_schema(schema, table, sql_field)
            except ValueError as e:
                if not ignore_value_error:
                    raise e
        try:  # Execute the schema's SQL statements
            with sqlite3.connect(self.database) as conn:
                cursor = conn.cursor()
                cursor.executescript(schema)
                conn.commit()
        except Exception as exc:
            logging.error('! error building db : {}'.format(exc))

    async def _get_column_names(self, sql):
        """Implements ThreadDB._get_column_names()"""
        with sqlite3.connect(self.database) as conn:
            cursor = conn.cursor()
            # Execute the SQL query
            cursor.execute(sql)
            # Return the column names from the cursor description
            return [desc[0] for desc in cursor.description]

    async def _execute_select(self, sql, parameters=None, single_col=False, on_fetch=None):
        """Implements ThreadDB._execute_select()"""
        if single_col and on_fetch:
            raise ValueError('Cannot request single-column and on_fetch transformations to be used at the same time.')
        with sqlite3.connect(self.database) as conn:
            conn.execute(ENABLE_FOREIGN_KEYS)
            # If we are returning a single column, we just want to retrieve the first part of the row (row[0])
            # else use sqlite3.Row to enable dictionary-conversions
            conn.row_factory = (lambda cur, row: row[0]) if single_col else sqlite3.Row
            cursor = conn.cursor()
            # Execute the SQL query with parameters or not
            if parameters is None:
                cursor.execute(sql)
            else:
                cursor.execute(sql, parameters)
            rows = cursor.fetchall()
            if callable(on_fetch):
                return on_fetch(rows)
            else:
                # Return the data as-is if returning a single column, else return the rows as dictionaries
                return rows if single_col else [dict(ix) for ix in rows]

    async def _execute_insert(self, sql, data):
        """Implements ThreadDB._execute_insert()"""
        with sqlite3.connect(self.database) as conn:
            conn.execute(ENABLE_FOREIGN_KEYS)
            cursor = conn.cursor()
            # Execute the SQL statement with the data to be inserted
            cursor.execute(sql, tuple(data))
            saved_id = cursor.lastrowid
            conn.commit()
            return saved_id

    async def _execute_update(self, sql, data):
        """Implements ThreadDB._execute_update()"""
        # Nothing extra do to or return:
        # just connect to the db; execute the SQL statement with the data to update; and commit
        with sqlite3.connect(self.database) as conn:
            conn.execute(ENABLE_FOREIGN_KEYS)
            cursor = conn.cursor()
            cursor.execute(sql, tuple(data))
            conn.commit()

    async def run_sql_list(self, sql_list=None, return_success=True):
        """Implements ThreadDB.run_sql_list()"""
        # Don't do anything if we don't have a list
        if not sql_list:
            return
        try:
            with sqlite3.connect(self.database) as conn:
                conn.execute(ENABLE_FOREIGN_KEYS)
                cursor = conn.cursor()
                # Else, execute each item in the list where the first part must be an SQL statement
                # followed by optional parameters
                for item in sql_list:
                    if item is None:  # skip None-items
                        continue
                    elif len(item) == 1:
                        cursor.execute(item[0])
                    elif len(item) == 2:
                        # execute() takes parameters as a tuple, ensure that is the case
                        parameters = item[1] if type(item[1]) == tuple else tuple(item[1])
                        cursor.execute(item[0], parameters)
                # Finish by committing the changes from the list
                conn.commit()
        except sqlite3.Error as e:
            logging.error('Encountered error: ' + str(e))
            return False
        return True
