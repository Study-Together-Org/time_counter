import os
import aiomysql
from dotenv import load_dotenv
load_dotenv()


class MySQL:
    def __init__(self, client):
        self.client = client

    async def init(self):
        if self.client.pool is None:
            self.client.pool = await aiomysql.create_pool(
                host=os.getenv("host"),
                user=os.getenv("user"),
                password=os.getenv("password"),
                db=os.getenv("database"),
                cursorclass=aiomysql.DictCursor,
                autocommit=True
            )

    async def query(self, sql, *params):
        # print("======= SQL Query =======")
        # print(sql, params)
        async with self.client.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                r = await cur.fetchall()
        # print(r)
        # print("=========================")
        return r  # Returns a list of fetched rows (if SELECT)
