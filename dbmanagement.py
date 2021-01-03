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
                host=os.getenv("sql_host"),
                user=os.getenv("sql_user"),
                password=os.getenv("sql_password"),
                db=os.getenv("sql_database"),
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
