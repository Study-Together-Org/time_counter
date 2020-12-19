import aiomysql


class MySQL():
    def __init__(self, client):
        self.client = client

    async def init(self):
        if self.client.pool is None:
            self.client.pool = await aiomysql.create_pool(
                host="HOST_NAME",
                user="DB_USER",
                password="DB_PASS",
                db="DB_NAME",
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
