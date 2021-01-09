import json

import pandas as pd
from sqlalchemy.orm import sessionmaker

import models
from models import *

load_dotenv("dev.env")
database_name = os.getenv("database")

engine = utilities.get_engine()
Session = sessionmaker(bind=engine)
sqlalchemy_session = Session()
redis_client = utilities.get_redis_client()

with open("user_stats.json", "rb") as f:
    user_stats = json.load(f)
    del user_stats["ID"]

df = pd.DataFrame.from_dict(user_stats, orient="index")
df.fillna(0, inplace=True)
dictionary = df.to_dict()


def insert_df():
    user_df = df[["current_streak", "longest_streak"]]
    user_df["id"] = user_df.index.astype(int)
    user_df["current_streak"] = user_df["current_streak"].astype(int)
    user_df["longest_streak"] = user_df["longest_streak"].astype(int)

    user_df.to_sql('user', con=engine, if_exists="append", index=False)
    sqlalchemy_session.commit()


def insert_sorted_set():
    filter_time_fn_li = [utilities.get_day_start, utilities.get_week_start, utilities.get_month_start,
                         utilities.get_earliest_start]

    for (category_name, sorted_set_name), filter_time_fn in zip(models.rank_categories.items(), filter_time_fn_li):
        if category_name not in dictionary:
            print(f"{category_name} missing")
            continue

        to_insert = dictionary[category_name]
        redis_client.zadd(sorted_set_name, to_insert)


if __name__ == '__main__':
    utilities.recreate_db(Base)
    insert_df()
    insert_sorted_set()
