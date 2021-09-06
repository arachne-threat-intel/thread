# NOTICE: As required by the Apache License v2.0, this notice is to state this file has been modified by Arachne Digital

import logging

from .thread_postgresql import ThreadPostgreSQL
from .thread_sqlite3 import ThreadSQLite

# The types of database engines supported
DB_SQLITE, DB_POSTGRESQL = 'sqlite3', 'postgresql'


class Dao:
    def __init__(self, database, engine=DB_SQLITE):
        self.logger = logging.getLogger('DataService')
        if engine == DB_SQLITE:
            self.db = ThreadSQLite(database)
        elif engine == DB_POSTGRESQL:
            self.db = ThreadPostgreSQL()
        else:
            raise ValueError('Incorrect config for \'db-engine\'')

    @property
    def db_true_val(self):
        return self.db.val_as_true

    @property
    def db_false_val(self):
        return self.db.val_as_false

    async def build(self, schema):
        await self.db.build(schema)

    async def get(self, table, equal=None, not_equal=None):
        return await self.db.get(table, equal=equal, not_equal=not_equal)

    async def update(self, table, where=None, data=None, return_sql=False):
        return await self.db.update(table, where=where, data=data, return_sql=return_sql)

    async def insert(self, table, data, return_sql=False):
        return await self.db.insert(table, data, return_sql=return_sql)

    async def insert_generate_uid(self, table, data, id_field='uid', return_sql=False):
        return await self.db.insert_generate_uid(table, data, id_field, return_sql=return_sql)

    async def delete(self, table, data, return_sql=False):
        return await self.db.delete(table, data, return_sql=return_sql)

    async def raw_query(self, query, one=False):
        return await self.db.raw_query(query, one)
        
    async def raw_select(self, query, parameters=None):
        return await self.db.raw_select(query, parameters=parameters)

    async def run_sql_list(self, sql_list=None):
        return await self.db.run_sql_list(sql_list=sql_list)
