# NOTICE: As required by the Apache License v2.0, this notice is to state this file has been modified by Arachne Digital

import logging

# The types of database engines supported
DB_SQLITE, DB_POSTGRESQL = 'sqlite3', 'postgresql'


class Dao:
    def __init__(self, engine=None):
        self.logger = logging.getLogger('DataService')
        self.db = engine
        if engine is None:
            raise ValueError('Incorrect config for \'db-engine\'')

    @property
    def db_qparam(self):
        return self.db.query_param

    @property
    def db_true_val(self):
        return self.db.val_as_true

    @property
    def db_false_val(self):
        return self.db.val_as_false

    def db_func(self, func_key, *args):
        return self.db.get_function_name(func_key, *args)

    async def build(self, schema):
        await self.db.build(schema)

    def generate_copied_tables(self, schema):
        return self.db.generate_copied_tables(schema)

    async def get(self, table, equal=None, not_equal=None):
        return await self.db.get(table, equal=equal, not_equal=not_equal)

    async def get_column_as_list(self, table, column):
        return await self.db.get_column_as_list(table, column)

    async def update(self, table, where=None, data=None, return_sql=False):
        return await self.db.update(table, where=where, data=data, return_sql=return_sql)

    async def insert(self, table, data, return_sql=False):
        return await self.db.insert(table, data, return_sql=return_sql)

    async def insert_generate_uid(self, table, data, id_field='uid', return_sql=False):
        return await self.db.insert_generate_uid(table, data, id_field=id_field, return_sql=return_sql)

    async def insert_with_backup(self, table, data, id_field='uid'):
        return await self.db.insert_with_backup(table, data, id_field=id_field)

    async def delete(self, table, data, return_sql=False):
        return await self.db.delete(table, data, return_sql=return_sql)
        
    async def raw_select(self, query, parameters=None):
        return await self.db.raw_select(query, parameters=parameters)

    async def run_sql_list(self, sql_list=None, return_success=True):
        return await self.db.run_sql_list(sql_list=sql_list, return_success=return_success)
