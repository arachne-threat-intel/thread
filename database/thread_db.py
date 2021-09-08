import logging
import uuid

from abc import ABC, abstractmethod


class ThreadDB(ABC):
    """A base class for DB tasks (where the SQL statements are the same across DB engines)."""
    # Constants to track which SQL functions have different names (between different DB engines)
    FUNC_STR_POS = 'string_pos'

    def __init__(self, mapped_functions=None):
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
    @abstractmethod
    def query_param(self):
        pass

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

    @abstractmethod
    async def _execute_update(self, sql, data):
        """Method to connect to the db and execute an SQL UPDATE statement."""
        pass

    @abstractmethod
    async def run_sql_list(self, sql_list=None):
        """Method to connect to the db and execute a list of SQL statements in a single transaction."""
        pass

    async def raw_select(self, sql, parameters=None, single_col=False):
        """Method to run a constructed SQL SELECT query."""
        return await self._execute_select(sql, parameters=parameters, single_col=single_col)

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
            # criteria should always have items as the if-else update() calls above check this
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
        """Method to update rows from a table of the db."""
        # If there is no data to update the table with, exit method
        if data is None:
            return None
        # If no WHERE data is specified, default to an empty dictionary
        if where is None:
            where = {}
        # The list of query parameters
        qparams = []
        # Our SQL statement and optional WHERE clause
        sql, where_suffix = 'UPDATE {} SET'.format(table), ''
        # Appending the SET terms; keep a count
        count = 0
        for k, v in data.items():
            # If this is our 2nd (or greater) SET term, separate with a comma
            sql += ',' if count > 0 else ''
            # Add this current term to the SQL statement substituting the values with query parameters
            sql += ' {} = {}'.format(k, self.query_param)
            # Update qparams for this value to be substituted
            qparams.append(v)
            count += 1
        # Appending the WHERE terms; keep a count
        count = 0
        for wk, wv in where.items():
            # If this is our 2nd (or greater) WHERE term, separate with an AND
            where_suffix += ' AND' if count > 0 else ''
            # Add this current term like before
            where_suffix += ' {} = {}'.format(wk, self.query_param)
            # Update qparams for this value to be substituted
            qparams.append(wv)
            count += 1
        # Finalise WHERE clause if we had items added to it
        where_suffix = '' if where_suffix == '' else ' WHERE' + where_suffix
        # Add the WHERE clause to the SQL statement
        sql += where_suffix
        if return_sql:
            return tuple([sql, tuple(qparams)])
        # Run the statement by passing qparams as parameters
        return await self._execute_update(sql, qparams)

    async def delete(self, table, data, return_sql=False):
        """Method to delete rows from a table of the db."""
        sql = 'DELETE FROM %s' % table
        qparams = []
        # Prevent a whole table being cleared - no need for this functionality at time of writing
        if not len(data):
            logging.error('Attempting to delete all rows from table %s; this is not allowed.' % table)
            return
        # Construct the WHERE clause using the data
        where = next(iter(data))
        value = data.pop(where)
        sql += ' WHERE %s = %s' % (where, self.query_param)
        qparams.append(value)
        for k, v in data.items():
            sql += ' AND %s = %s' % (k, self.query_param)
            qparams.append(v)
        if return_sql:
            return tuple([sql, tuple(qparams)])
        # Run the statement by passing qparams as parameters
        return await self._execute_update(sql, qparams)
