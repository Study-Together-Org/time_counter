import os
import pymysql
from dotenv import load_dotenv
load_dotenv()

con = pymysql.connect(os.getenv("host"), os.getenv("user"), os.getenv("password"))
database_name = os.getenv("database")

try:
    with con.cursor() as cur:
        cur.execute(f'DROP DATABASE IF EXISTS {database_name}')
        cur.execute(f'CREATE DATABASE IF NOT EXISTS {database_name}')
        cur.execute(f'use {database_name}')
        create_user = """
            CREATE TABLE IF NOT EXISTS User(
               id int NOT NULL PRIMARY KEY AUTO_INCREMENT,
               discord_user_id VARCHAR(32) NOT NULL UNIQUE
            ); 
        """
        cur.execute(create_user)

        create_action = """
            CREATE TABLE IF NOT EXISTS Action(
               id int NOT NULL PRIMARY KEY,
               User_id INT NOT NULL,
               category VARCHAR(32) NOT NULL,
               detail VARCHAR(32),
               creation_time DATETIME,
               FOREIGN KEY(User_id) REFERENCES User(id)
            ); 
        """
        cur.execute(create_action)

except Exception as e:
    print("Exeception occured:{}".format(e))

finally:
    con.close()
