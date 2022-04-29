# NOTICE: As required by the Apache License v2.0, this notice is to state this file has been modified by Arachne Digital
# This file has been renamed from `tram_relation.py`
# To see its full history, please use `git log --follow <filename>` to view previous commits and additional contributors

import logging
import sqlite3

from .thread_db import ThreadDB

ENABLE_FOREIGN_KEYS = 'PRAGMA foreign_keys = ON;'


class ThreadSQLite(ThreadDB):
    def __init__(self, database):
        super().__init__()
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
        try:
            # sqlite3 does not support date fields (see 2.2. here: https://www.sqlite.org/datatype3.html)
            # We only want to log an error if we are building the full schema
            schema = self.add_column_to_schema(schema, 'reports', 'expires_on TEXT', log_error=(not is_partial))
        except ValueError as e:
            # Partial-schemas (e.g. backup tables) will most likely raise an error so ignore these
            if not is_partial:
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
