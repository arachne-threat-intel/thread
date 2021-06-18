import sqlite3
import uuid


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

    async def get(self, table, criteria=None):
        sql = 'SELECT * FROM %s' % table
        qparams = []
        if criteria:
            where = next(iter(criteria))
            value = criteria.pop(where)
            if value:
                sql += ' WHERE %s = ?' % where
                qparams.append(value)
                for k, v in criteria.items():
                    sql += ' AND %s = ?' % k
                    qparams.append(v)
        with sqlite3.connect(self.database) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql, tuple(qparams))
            rows = cursor.fetchall()
            return [dict(ix) for ix in rows]

    async def insert(self, table, data):
        with sqlite3.connect(self.database) as conn:
            cursor = conn.cursor()
            columns = ', '.join(data.keys())
            temp = ['?' for i in range(len(data.values()))]
            placeholders = ', '.join(temp)
            sql = 'INSERT INTO {} ({}) VALUES ({})'.format(table, columns, placeholders)
            cursor.execute(sql, tuple(data.values()))
            id = cursor.lastrowid
            conn.commit()
            return id

    async def insert_generate_uid(self, table, data, id_field='uid'):
        """Method to generate an ID value whilst inserting into db."""
        data[id_field] = str(uuid.uuid4())
        try:
            # Attempt this insertion with the ID field generated
            await self.insert(table, data)
        except sqlite3.IntegrityError as e:
            # If it failed because the ID was not unique, attempt once more
            if 'UNIQUE' in str(e) and table + '.' + 'uid' in str(e):
                data[id_field] = str(uuid.uuid4())
                await self.insert(table, data)
            else:
                raise e
        # Finally, return the ID value used for insertion
        return data[id_field]

    async def update(self, table, where={}, data={}):
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
        where_suffix = '' if '' else ' WHERE' + where_suffix
        # Add the WHERE clause to the SQL statement
        sql += where_suffix
        # Run the statement by passing qparams as parameters
        with sqlite3.connect(self.database) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, tuple(qparams))
            conn.commit()

    async def delete(self, table, data):
        sql = 'DELETE FROM %s' % table
        qparams = []
        where = next(iter(data))
        value = data.pop(where)
        sql += ' WHERE %s = ?' % where
        qparams.append(value)
        for k, v in data.items():
            sql += ' AND %s = ?' % k
            qparams.append(v)
        with sqlite3.connect(self.database) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, tuple(qparams))
            conn.commit()

    async def raw_query(self, query, one=False):
        with sqlite3.connect(self.database) as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            rv = cursor.fetchall()
            conn.commit()
            return rv[0] if rv else None if one else rv

    async def raw_select(self, sql, parameters=None):
        with sqlite3.connect(self.database) as conn:
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
            cursor = conn.cursor()
            cursor.execute(sql)
            conn.commit()
