import uuid

from abc import ABC, abstractmethod


class ThreadDB(ABC):
    """A base class for DB tasks (where the SQL statements are the same across DB engines)."""
    # Constants to track which SQL functions have different names (between different DB engines)
    FUNC_STR_POS = 'string_pos'

    def __init__(self, query_param, mapped_functions=None):
        self.__query_param = query_param
        # Some DB engines interpret booleans differently, have mapped values ready; default as integers to be overridden
        self._val_as_true = 1
        self._val_as_false = 0
        # The map to keep track of SQL functions
        self._mapped_functions = dict()
        # The function to find a substring position in a string
        self._mapped_functions[self.FUNC_STR_POS] = 'INSTR'
        # Update mapped_functions if provided
        if mapped_functions is not None:
            self._mapped_functions.update(mapped_functions)

    @property
    def query_param(self):
        return self.__query_param

    @property
    def val_as_true(self):
        return self._val_as_true

    @property
    def val_as_false(self):
        return self._val_as_false

    def get_function_name(self, func_key, *args):
        """Function to retrieve a function name for this ThreadDB instance.
        Can take non-iterable args such that it returns the string `function(arg1, arg2, ...)`."""
        # Get the function name according to the mapped_functions dictionary
        func_name = self._mapped_functions.get(func_key)
        # If there is nothing to retrieve, return None
        if func_name is None:
            return None
        # If we have args, construct the string `f(a, b, ...)` (where str args - except query params - are quoted)
        if args:
            return '%s(%s)' % (func_name, ', '.join(
                ('\'%s\'' % x if (type(x) is str and x != self.query_param) else str(x)) for x in args))
        # Else if no args are supplied, just return the function name
        else:
            return func_name

    @abstractmethod
    async def build(self, schema):
        """Method to build the db given a schema."""
        pass

    @abstractmethod
    async def _execute_select(self, sql, parameters=None, single_col=False):
        """Method to connect to the db and execute an SQL SELECT query."""
        pass

    @abstractmethod
    async def _execute_insert(self, sql, data):
        """Method to connect to the db and execute an SQL INSERT statement."""
        pass

    async def get(self, table, equal=None, not_equal=None):
        """Method to return values from a db table optionally based on equals or not-equals criteria."""
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
        # After the SQL query has been formed, execute it
        return await self._execute_select(sql, parameters=qparams)

    async def get_column_as_list(self, table, column):
        """Method to return a column from a db table as a list."""
        return await self.raw_select('SELECT %s FROM %s' % (column, table), single_col=True)

    async def insert(self, table, data, return_sql=False):
        """Method to insert data into a table of the db."""
        # For the INSERT statement, construct the strings `col1, col2, ...` and `<query_param>, <query_param>, ...`
        columns = ', '.join(data.keys())
        temp = [self.query_param for i in range(len(data.values()))]
        placeholders = ', '.join(temp)
        # Construct the SQL statement using the comma-separated strings created above
        sql = 'INSERT INTO {} ({}) VALUES ({})'.format(table, columns, placeholders)
        # Return the SQL statement as-is if requested
        if return_sql:
            return tuple([sql, tuple(data.values())])
        # Else execute the SQL INSERT statement
        return await self._execute_insert(sql, data)

    async def insert_generate_uid(self, table, data, id_field='uid', return_sql=False):
        """Method to generate an ID value whilst inserting into db."""
        # Update the ID field in data to be a generated UID
        data[id_field] = str(uuid.uuid4())
        # Execute the insertion
        result = await self.insert(table, data, return_sql=return_sql)
        # Return the ID value used for insertion if not returning the SQL query itself
        return result if return_sql else data[id_field]

    async def update(self, table, where=None, data=None, return_sql=False):
        pass

    async def delete(self, table, data, return_sql=False):
        pass

    async def raw_select(self, sql, parameters=None, single_col=False):
        """Method to run a constructed SQL SELECT query."""
        return await self._execute_select(sql, parameters=parameters, single_col=single_col)

    async def run_sql_list(self, sql_list=None):
        pass
