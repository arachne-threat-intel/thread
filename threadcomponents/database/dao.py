# NOTICE: As required by the Apache License v2.0, this notice is to state this file has been modified by Arachne Digital
# This file has been moved into a different directory
# To see its full history, please use `git log --follow <filename>` to view previous commits and additional contributors

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

    async def build(self, schema, is_partial=False):
        await self.db.build(schema, is_partial=is_partial)

    def generate_copied_tables(self, schema):
        return self.db.generate_copied_tables(schema)

    async def get(self, table, equal=None, not_equal=None, order_by_asc=None, order_by_desc=None):
        return await self.db.get(table, equal=equal, not_equal=not_equal, order_by_asc=order_by_asc,
                                 order_by_desc=order_by_desc)

    async def get_column_as_list(self, table, column):
        return await self.db.get_column_as_list(table, column)

    async def get_dict_value_as_key(self, column_key, table=None, columns=None, sql=None, sql_params=None):
        return await self.db.get_dict_value_as_key(column_key, table=table, columns=columns, sql=sql, sql_params=sql_params)

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
        
    async def raw_select(self, query, parameters=None, single_col=False):
        return await self.db.raw_select(query, parameters=parameters, single_col=single_col)

    async def run_sql_list(self, sql_list=None, return_success=True):
        return await self.db.run_sql_list(sql_list=sql_list, return_success=return_success)

    @staticmethod
    def truncate_str(value, max_length):
        """Helper method to truncate strings before saving into db."""
        if not (isinstance(max_length, int) and isinstance(value, str)):
            raise TypeError('str and int args not provided to truncate_str(value, max_length).')
        return value if len(value) < max_length else value[:(max_length - 3)] + '...'
