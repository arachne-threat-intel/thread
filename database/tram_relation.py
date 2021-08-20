# NOTICE: As required by the Apache License v2.0, this notice is to state this file has been modified by Arachne Digital

import sqlite3
import uuid

ENABLE_FOREIGN_KEYS = 'PRAGMA foreign_keys = ON'


class Attack:

    def __init__(self, database):
        self.database = database

    # TODO check any execute() calls have parameters where strings have been formatted
    # e.g. sql += (' AND %s = "%s"' % (k, v)) in get()

    async def build(self, schema):
        try:
            with sqlite3.connect(self.database) as conn:
                cursor = conn.cursor()
                cursor.executescript(schema)
                conn.commit()
        except Exception as exc:
            print('! error building db : {}'.format(exc))

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
                sql += (' %s %s= ?' % (where, '!' if eq == 'not_equal' else ''))
                qparams.append(value)
                for k, v in criteria.items():
                    sql += (' AND %s %s= ?' % (k, '!' if eq == 'not_equal' else ''))
                    qparams.append(v)
        with sqlite3.connect(self.database) as conn:
            conn.execute(ENABLE_FOREIGN_KEYS)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql, tuple(qparams))
            rows = cursor.fetchall()
            return [dict(ix) for ix in rows]

    async def insert(self, table, data, return_sql=False):
        columns = ', '.join(data.keys())
        temp = ['?' for i in range(len(data.values()))]
        placeholders = ', '.join(temp)
        sql = 'INSERT INTO {} ({}) VALUES ({})'.format(table, columns, placeholders)
        if return_sql:
            return tuple([sql, tuple(data.values())])
        with sqlite3.connect(self.database) as conn:
            conn.execute(ENABLE_FOREIGN_KEYS)
            cursor = conn.cursor()
            cursor.execute(sql, tuple(data.values()))
            saved_id = cursor.lastrowid
            conn.commit()
            return saved_id

    async def insert_generate_uid(self, table, data, id_field='uid', return_sql=False):
        """Method to generate an ID value whilst inserting into db."""
        data[id_field] = str(uuid.uuid4())
        try:
            # Attempt this insertion with the ID field generated
            result = await self.insert(table, data, return_sql=return_sql)
        except sqlite3.IntegrityError as e:
            # If it failed because the ID was not unique, attempt once more
            if 'UNIQUE' in str(e) and table + '.' + 'uid' in str(e):
                data[id_field] = str(uuid.uuid4())
                result = await self.insert(table, data, return_sql=return_sql)
            else:
                raise e
        # Finally, return the ID value used for insertion
        return result if return_sql else data[id_field]

    async def update(self, table, where=None, data=None, return_sql=False):
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
            # Add this current term to the SQL statement leaving a ? for the value
            sql += ' {} = ?'.format(k)
            # Update qparams for this value to be substituted
            qparams.append(v)
            count += 1
        # Appending the WHERE terms; keep a count
        count = 0
        for wk, wv in where.items():
            # If this is our 2nd (or greater) WHERE term, separate with an AND
            where_suffix += ' AND' if count > 0 else ''
            # Add this current term like before
            where_suffix += ' {} = ?'.format(wk)
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
        with sqlite3.connect(self.database) as conn:
            conn.execute(ENABLE_FOREIGN_KEYS)
            cursor = conn.cursor()
            cursor.execute(sql, tuple(qparams))
            conn.commit()

    async def delete(self, table, data, return_sql=False):
        sql = 'DELETE FROM %s' % table
        qparams = []
        where = next(iter(data))
        value = data.pop(where)
        sql += ' WHERE %s = ?' % where
        qparams.append(value)
        for k, v in data.items():
            sql += ' AND %s = ?' % k
            qparams.append(v)
        if return_sql:
            return tuple([sql, tuple(qparams)])
        with sqlite3.connect(self.database) as conn:
            conn.execute(ENABLE_FOREIGN_KEYS)
            cursor = conn.cursor()
            cursor.execute(sql, tuple(qparams))
            conn.commit()

    async def raw_query(self, query, one=False):
        with sqlite3.connect(self.database) as conn:
            conn.execute(ENABLE_FOREIGN_KEYS)
            cursor = conn.cursor()
            cursor.execute(query)
            rv = cursor.fetchall()
            conn.commit()
            return rv[0] if rv else None if one else rv

    async def raw_select(self, sql, parameters=None):
        with sqlite3.connect(self.database) as conn:
            conn.execute(ENABLE_FOREIGN_KEYS)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if parameters is None:
                cursor.execute(sql)
            else:
                cursor.execute(sql, parameters)
            rows = cursor.fetchall()
            return [dict(ix) for ix in rows]

    async def raw_update(self, sql):
        with sqlite3.connect(self.database) as conn:
            conn.execute(ENABLE_FOREIGN_KEYS)
            cursor = conn.cursor()
            cursor.execute(sql)
            conn.commit()

    async def run_sql_list(self, sql_list=None):
        # Don't do anything if we don't have a list
        if not sql_list:
            return
        with sqlite3.connect(self.database) as conn:
            conn.execute(ENABLE_FOREIGN_KEYS)
            cursor = conn.cursor()
            # Else, execute each item in the list where the first part must be an SQL statement
            # followed by optional parameters
            for item in sql_list:
                if len(item) == 1:
                    cursor.execute(item[0])
                elif len(item) == 2:
                    # execute() takes parameters as a tuple, ensure that is the case
                    parameters = item[1] if type(item[1]) == tuple else tuple(item[1])
                    cursor.execute(item[0], parameters)
            # Finish by committing the changes from the list
            conn.commit()
