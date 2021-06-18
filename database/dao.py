from .tram_relation import Attack
import logging


class Dao:

    def __init__(self, database):
        self.logger = logging.getLogger('DataService')
        self.db = Attack(database)

    async def build(self, schema):
        await self.db.build(schema)

    async def get(self, table, criteria=None):
        return await self.db.get(table, criteria)

    async def update(self, table, where={}, data={}):
        await self.db.update(table, where=where, data=data)

    async def insert(self, table, data):
        return await self.db.insert(table, data)

    async def insert_generate_uid(self, table, data, id_field='uid'):
        return await self.db.insert_generate_uid(table, data, id_field)

    async def delete(self, table, data):
        await self.db.delete(table, data)

    async def raw_query(self, query, one=False):
        return await self.db.raw_query(query, one)
        
    async def raw_select(self, query, parameters=None):
        return await self.db.raw_select(query, parameters=parameters)
