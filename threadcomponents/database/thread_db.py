import logging
import uuid

from abc import ABC, abstractmethod
from contextlib import suppress

BACKUP_TABLE_SUFFIX = '_initial'
TABLES_WITH_BACKUPS = ['report_sentences', 'report_sentence_hits', 'original_html']
# The beginning and end strings of an SQL create statement
CREATE_BEGIN, CREATE_END = 'CREATE TABLE IF NOT EXISTS', ');'


def find_create_statement_in_schema(schema, table, log_error=True, find_closing_bracket=False):
    """Helper-method to return the start and end positions of an SQL create statement in a given schema."""
    # The possible matches when finding the CREATE statement (with a space and opening bracket or just the bracket)
    start_statements = ['%s %s (' % (CREATE_BEGIN, table), '%s %s(' % (CREATE_BEGIN, table)]
    start_pos, error = None, ValueError()
    for start_statement in start_statements:
        try:
            start_pos = schema.index(start_statement)
        except ValueError as e:
            error = e
            continue  # skip to next statement to attempt search
        break  # found starting-position so break loop
    # On errors when positions cannot be found, log the error (if we want to) and then raise the error
    # Start-position not found
    if not start_pos:
        if log_error:
            logging.error('Table `%s` missing: given schema has different or missing CREATE statement.' % table)
        raise error
    # Given a starting position, find where the table's create statement finishes
    try:
        end_pos = schema[start_pos:].index(CREATE_END)
    # End-position not found
    except ValueError as e:
        if log_error:
            logging.error('SQL error: could not find closing `%s` for table `%s` in schema.' % (CREATE_END, table))
        raise e
    # Consider the end position to be before any foreign key statements; they might not be present so ignore ValueErrors
    if not find_closing_bracket:
        table_statement = schema[start_pos:start_pos + end_pos]
        with suppress(ValueError):
            end_pos = table_statement.index('FOREIGN KEY')
    # End position is offset by the start_pos (because index() was called from start_pos)
    return start_pos, (start_pos + end_pos)


class ThreadDB(ABC):
    """A base class for DB tasks (where the SQL statements are the same across DB engines)."""
    # Constants to track which SQL functions have different names (between different DB engines)
    FUNC_STR_POS = 'string_pos'
    FUNC_TIME_NOW = 'time_now'

    def __init__(self, mapped_functions=None):
        # The map to keep track of SQL functions
        self._mapped_functions = dict()
        # The function to find a substring position in a string
        self._mapped_functions[self.FUNC_STR_POS] = 'INSTR'
        # Update mapped_functions if provided
        if mapped_functions is not None:
            self._mapped_functions.update(mapped_functions)
        # A map tp store the column names of the initial-data tables
        self._table_columns = dict()

    @property
    @abstractmethod
    def query_param(self):
        """The string representing a query parameter."""
        pass

    @property
    def backup_table_suffix(self):
        """The suffix of initial-data tables."""
        return BACKUP_TABLE_SUFFIX

    @property
    def backup_table_list(self):
        """The list of initial-data tables."""
        return TABLES_WITH_BACKUPS

    @property
    def val_as_true(self):
        """The db's value for True."""
        return 1  # default as int, 1

    @property
    def val_as_false(self):
        """The db's value for False."""
        return 0  # default as int, 0

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

    @staticmethod
    def add_column_to_schema(schema, table, column, log_error=True):
        """Function to add a column to a table in a schema and return the new schema."""
        # First, find the create-table SQL statements
        start_pos, end_pos = find_create_statement_in_schema(schema, table, log_error=log_error)
        # If the end-position is the end of the create statement, add a comma to separate from the line before
        if schema[end_pos] == ')':
            return schema[:end_pos] + ', ' + column + schema[end_pos:]
        # Else, the end-position represents the end of the list of variables for the table and a comma should follow
        else:
            return schema[:end_pos] + ' ' + column + ', ' + schema[end_pos:]

    @staticmethod
    def generate_copied_tables(schema=''):
        """Function to return a new schema that has copied structures of report-sentence tables from a given schema."""
        # The new schema to build on and return
        new_schema = ''
        # For each table that we are copying the structure of...
        for table in TABLES_WITH_BACKUPS:
            # Obtain the start and end positions of the SQL create statement for this table
            start_pos, end_pos = find_create_statement_in_schema(schema, table, find_closing_bracket=True)
            # We can now isolate just the create statement for this table
            # end_pos + len(CREATE_END) to include the end of the creation string itself (i.e. include ');' )
            create_statement = schema[start_pos:(end_pos + len(CREATE_END))]
            # Add the create statement for this table to the new schema
            new_schema += '\n\n' + create_statement
        # Now that the new schema has the tables we want copied, replace mention of the table name with '<name>_initial'
        # We want all occurrences replaced because of foreign key constraints
        for table in TABLES_WITH_BACKUPS:
            new_schema = new_schema.replace(table, '%s%s' % (table, BACKUP_TABLE_SUFFIX))
        # Return the new schema
        return new_schema.strip()

    @abstractmethod
    async def build(self, schema, is_partial=False):
        """Method to build the db given a schema."""
        pass

    @abstractmethod
    async def _get_column_names(self, sql):
        """Method to get column names for data retrieved by a given SQL statement."""
        pass

    @abstractmethod
    async def _execute_select(self, sql, parameters=None, single_col=False, on_fetch=None):
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
    async def run_sql_list(self, sql_list=None, return_success=True):
        """Method to connect to the db and execute a list of SQL statements in a single transaction."""
        pass

    async def raw_select(self, sql, parameters=None, single_col=False):
        """Method to run a constructed SQL SELECT query."""
        return await self._execute_select(sql, parameters=parameters, single_col=single_col)

    @staticmethod
    def _check_method_parameters(table, data, data_allowed_as_none=False, method_name='unspecified'):
        """Function to check parameters passed to CRUD methods."""
        # Check the table is a string
        if type(table) != str:
            raise TypeError('Non-string arg passed for table in ThreadDB.%s(): %s' % (method_name, str(table)))
        # Proceed with checks if data is non-None but allowed to be so
        if data_allowed_as_none and data is None:
            return
        # Check values passed to this method are dictionaries (column=value key-val pairs)
        if type(data) != dict:
            raise TypeError('Non-dictionary arg passed in ThreadDB.%s(table=%s): %s' % (method_name, table, str(data)))
        # If the data is not allowed to be None (or empty), check data has been provided
        if (not data_allowed_as_none) and (not len(data)):
            raise ValueError('Non-empty-dictionary must be passed in ThreadDB.%s(table=%s)' % (method_name, table))

    async def get(self, table, equal=None, not_equal=None, order_by_asc=None, order_by_desc=None):
        """Method to return values from a db table optionally based on equals or not-equals criteria."""
        # Check values passed to this method are valid
        for param in [equal, not_equal, order_by_asc, order_by_desc]:
            # Allow None values as we do checks for this but non-None values should be dictionaries
            self._check_method_parameters(table, param, data_allowed_as_none=True, method_name='get')
        # Proceed with method
        sql = 'SELECT * FROM %s' % table
        # Define all_params dictionary (for equal and not_equal to be None-checked and combined)
        # all_ordering dictionary (for ASC and DESC ordering combined) and qparams list
        all_params, all_ordering, qparams = dict(), dict(), []
        # Append to all_params equal and not_equal if not None
        all_params.update(dict(equal=equal) if equal else {})
        all_params.update(dict(not_equal=not_equal) if not_equal else {})
        # Do the same for the ordering dictionaries
        all_ordering.update(dict(asc=order_by_asc) if order_by_asc else {})
        all_ordering.update(dict(desc=order_by_desc) if order_by_desc else {})
        # For each of the equal and not_equal parameters, build SQL query
        count = 0
        for eq, criteria in all_params.items():
            for where, value in criteria.items():
                # If there is a column we want to specify WHERE criteria for
                if where is not None:
                    # If this is our first criteria we are adding, we need the WHERE keyword, else adding AND
                    sql += ' AND' if count > 0 else ' WHERE'
                    if value is None:
                        # Do a NULL check for the column
                        sql += (' %s IS%s NULL' % (where, ' NOT' if eq == 'not_equal' else ''))
                    else:
                        # Add the ! for != if this is a not-equals check
                        sql += (' %s %s= %s' % (where, '!' if eq == 'not_equal' else '', self.query_param))
                        qparams.append(value)
                    count += 1
        # For each of the ordering parameters, build the ORDER BY clause of the SQL query
        count = 0
        for order_by, criteria in all_ordering.items():
            for where, value in criteria.items():
                # If there is a column we want to specify ordering for
                if where is not None:
                    # If this is our first column we are adding, we need the ORDER BY part, else add separating comma
                    sql += ',' if count > 0 else ' ORDER BY'
                    # If the boolean value for this column to be ordered is True...
                    if value:
                        # Add column name and ASC/DESC criteria
                        sql += (' %s %s' % (where, order_by.upper()))
                    count += 1
        # After the SQL query has been formed, execute it
        return await self._execute_select(sql, parameters=qparams)

    async def get_column_as_list(self, table, column):
        """Method to return a column from a db table as a list."""
        return await self.raw_select('SELECT %s FROM %s' % (column, table), single_col=True)

    async def get_dict_value_as_key(self, table, column_key, columns):
        """Method to return a dictionary of results where the key is a column's value.
           Ideally, we'd want to use Pivot tables, but you need to know the column-values in advance."""
        def on_fetch(results):
            # Use the column-value as the key rather than the column-name
            converted = dict()
            for ix in results:
                temp_dict = dict(ix)
                temp_key = temp_dict.pop(column_key)
                converted[temp_key] = temp_dict
            return converted
        # We currently don't have a use-case for this and other clauses (WHERE, etc) so leaving as-is for now
        sql = 'SELECT %s FROM ' + table
        # Insert the columns in the SQL statement depending on its type
        # Need to add the column-key to the query, so we get the values for that column
        if isinstance(columns, str):
            sql = sql % (columns + ', ' + column_key)
        elif isinstance(columns, list):
            columns.append(column_key)
            sql = sql % ', '.join(columns)
        else:
            raise TypeError('Argument `columns` should be str or list.')
        return await self._execute_select(sql, on_fetch=on_fetch)

    async def initialise_column_names(self):
        """Method to initialise the map used to store column names for the db tables."""
        # We currently only care about storing initial data table columns for INSERT INTO SELECT statements
        for table in TABLES_WITH_BACKUPS:
            # Access no data but select all columns for the given table
            sql = 'SELECT * FROM %s LIMIT 0' % table
            # Update map with the list of columns obtained from this SQL statement
            self._table_columns[table] = await self._get_column_names(sql)

    def get_column_names_from_table(self, table):
        """Method to return the list of columns from a db table."""
        return self._table_columns.get(table, [])

    async def insert(self, table, data, return_sql=False):
        """Method to insert data into a table of the db."""
        # Check values passed to this method are valid
        self._check_method_parameters(table, data, method_name='insert')
        # For the INSERT statement, construct the strings `col1, col2, ...` and `<query_param>, <query_param>, ...`
        columns = ', '.join(data.keys())
        temp = ['NULL' if v is None else self.query_param for v in data.values()]
        placeholders = ', '.join(temp)
        # Construct the SQL statement using the comma-separated strings created above
        sql = 'INSERT INTO {} ({}) VALUES ({})'.format(table, columns, placeholders)
        # Filter out null values to match number of query parameters
        non_null = [v for v in data.values() if v is not None]
        # Return the SQL statement as-is if requested
        if return_sql:
            return tuple([sql, tuple(non_null)])
        # Else execute the SQL INSERT statement
        return await self._execute_insert(sql, non_null)

    async def insert_generate_uid(self, table, data, id_field='uid', return_sql=False):
        """Method to generate an ID value whilst inserting into db."""
        # Check values passed to this method are valid
        self._check_method_parameters(table, data, method_name='insert_generate_uid')
        # Update the ID field in data to be a generated UID
        data[id_field] = str(uuid.uuid4())
        # Execute the insertion
        result = await self.insert(table, data, return_sql=return_sql)
        # Return the ID value used for insertion if not returning the SQL query itself
        return result if return_sql else data[id_field]

    async def insert_with_backup(self, table, data, id_field='uid'):
        """Function to insert data into its relevant table and its backup (*_initial) table."""
        # Check values passed to this method are valid
        self._check_method_parameters(table, data, method_name='insert_with_backup')
        # Insert the data into the table and obtain the ID to return
        record_id = await self.insert_generate_uid(table, data, id_field=id_field)
        # Make a copy of the data to update the ID
        copied_data = dict(data)
        copied_data[id_field] = record_id
        # Insert the copied data into the backup table
        await self.insert('%s%s' % (table, BACKUP_TABLE_SUFFIX), copied_data)
        # Return the ID for the two records
        return record_id

    async def update(self, table, where=None, data=None, return_sql=False):
        """Method to update rows from a table of the db."""
        # Check values passed to this method are valid
        self._check_method_parameters(table, data, method_name='update')
        self._check_method_parameters(table, where, method_name='update')
        # The list of query parameters
        qparams = []
        # Our SQL statement and optional WHERE clause
        sql, where_suffix = 'UPDATE {} SET'.format(table), ''
        # Appending the SET terms; keep a count
        count = 0
        for k, v in data.items():
            # If this is our 2nd (or greater) SET term, separate with a comma
            sql += ',' if count > 0 else ''
            if v is None:
                # Add setting as NULL for this column
                sql += ' {} = NULL'.format(k)
            else:
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
            if wv is None:
                # Add NULL-check for this column
                where_suffix += ' {} IS NULL'.format(wk)
            else:
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
        # Check values passed to this method are valid
        self._check_method_parameters(table, data, method_name='delete')
        sql = 'DELETE FROM %s' % table
        qparams = []
        # Construct the WHERE clause using the data
        count = 0
        for k, v in data.items():
            # If this is our first criteria we are adding, we need the WHERE keyword, else adding AND
            sql += ' AND' if count > 0 else ' WHERE'
            if v is None:
                # Do a NULL check for the column
                sql += (' %s IS NULL' % k)
            else:
                # Add the ! for != if this is a not-equals check
                sql += (' %s = %s' % (k, self.query_param))
                qparams.append(v)
            count += 1
        if return_sql:
            return tuple([sql, tuple(qparams)])
        # Run the statement by passing qparams as parameters
        return await self._execute_update(sql, qparams)
