"""A base class for DB tasks (where the SQL statements are the same across DB engines)."""


class ThreadDB:
    def __init__(self, query_param):
        self.__query_param = query_param

    @property
    def query_param(self):
        return self.__query_param

    async def build(self, schema):
        pass

    async def get(self, table, equal=None, not_equal=None):
        pass

    async def insert(self, table, data, return_sql=False):
        pass

    async def insert_generate_uid(self, table, data, id_field='uid', return_sql=False):
        """Method to generate an ID value whilst inserting into db."""
        pass

    async def update(self, table, where=None, data=None, return_sql=False):
        pass

    async def delete(self, table, data, return_sql=False):
        pass

    async def raw_query(self, query, one=False):
        pass

    async def raw_select(self, sql, parameters=None):
        pass

    async def raw_update(self, sql):
        pass

    async def run_sql_list(self, sql_list=None):
        pass
