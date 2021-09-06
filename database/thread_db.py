"""A base class for DB tasks (where the SQL statements are the same across DB engines)."""


class ThreadDB:
    def __init__(self, query_param):
        self.__query_param = query_param

    @property
    def query_param(self):
        return self.__query_param

    async def build(self, schema):
        pass

    async def _execute_select(self, sql, parameters=None):
        pass

    async def get(self, table, equal=None, not_equal=None):
        sql = 'SELECT * FROM %s' % table
        # Define all_params dictionary (for equal and not_equal to be None-checked and combined) and qparams list
        all_params, qparams = dict(), []
        # Append to all_params equal and not_equal if not None
        all_params.update(dict(equal=equal) if equal else {})
        all_params.update(dict(not_equal=not_equal) if not_equal else {})
        # For each of the equal and not_equal parameters, build SQL query
        for eq, criteria in all_params.items():
            where = next(iter(criteria))
            value = criteria.pop(where)
            if value is not None:
                # If this is our first criteria we are adding, we need the WHERE keyword, else adding AND
                sql += ' AND' if len(qparams) > 0 else ' WHERE'
                # Add the ! for != if this is a not-equals check
                sql += (' %s %s= %s' % (where, '!' if eq == 'not_equal' else '', self.query_param))
                qparams.append(value)
                for k, v in criteria.items():
                    sql += (' AND %s %s= %s' % (k, '!' if eq == 'not_equal' else '', self.query_param))
                    qparams.append(v)
        return await self._execute_select(sql, parameters=qparams)

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
        return await self._execute_select(sql, parameters)

    async def raw_update(self, sql):
        pass

    async def run_sql_list(self, sql_list=None):
        pass
