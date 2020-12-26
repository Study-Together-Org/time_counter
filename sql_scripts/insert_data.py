import os
import pymysql
from dotenv import load_dotenv
import utilities

load_dotenv("../dev.env")
con = pymysql.connect(os.getenv("host"), os.getenv("user"), os.getenv("password"), autocommit=True)
database_name = os.getenv("database")

try:
    with con.cursor() as cur:
        cur.execute(f'use {database_name}')

        for i in range(1, 11):
            create_user = f"""
                INSERT INTO User (discord_user_id)
                VALUES ({utilities.generate_discord_user_id()});
            """
            print(create_user)
            cur.execute(create_user)

except Exception as e:
    print("Exeception occured:{}".format(e))

finally:
    con.close()
