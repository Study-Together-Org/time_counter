# TODO test - Worry about duplicate random samples if CDCI

import redis
import os
from dotenv import load_dotenv
import utilities
import models
from sqlalchemy.orm import sessionmaker
import pandas as pd
from faker import Faker
from collections import defaultdict
from sqlalchemy import create_engine
from models import *
import numpy as np
from sqlalchemy.ext.declarative import declarative_base

load_dotenv("dev.env")
np.random.seed(int(os.getenv("seed")))
database_name = os.getenv("database")

engine = utilities.get_engine()
Session = sessionmaker(bind=engine)
sqlalchemy_session = Session()
redis_client = utilities.get_redis_client()

# Base = declarative_base()

# user_size = 12003
# action_size = int(1e6 / 2)  # user_size * 30 * 3 + 1
user_size = 210
action_size = user_size * 30 * 3 + 1


def random_data(df):
    size = len(df)
    sample_start = np.random.randint(low=1, high=size)
    category_sample = models.action_categories[:2] * 2 * size
    df["category"] = category_sample[sample_start: sample_start + size]
    df["creation_time"] = utilities.generate_datetime(size=size)
    return df


def generate_df():
    user_df = pd.DataFrame(columns=['discord_user_id'])
    user_df['discord_user_id'] = utilities.generate_discord_user_id(user_size)

    action_df = pd.DataFrame(columns=['user_id', 'category', 'detail', 'creation_time'])
    # It deliberately makes the last member not have any action
    action_df["user_id"] = np.random.randint(low=1, high=user_size, size=action_size)

    action_df = action_df.groupby("user_id").apply(random_data)
    action_df["detail"] = "private channel 13"

    user_df.to_sql('user', con=engine, if_exists="append", index=False)
    action_df.to_sql('action', con=engine, if_exists="append", index=False)
    # TODO test - generate streak data
    sqlalchemy_session.commit()


def generate_sorted_set():
    # TODO Get all time data somehow
    filter_time_fn_li = [utilities.get_day_start, utilities.get_week_start, utilities.get_month_start, utilities.get_earliest_start]

    for sorted_set_name, filter_time_fn in zip(models.me_categories, filter_time_fn_li):
        query = sqlalchemy_session.query(Action.user_id, Action.category, Action.creation_time) \
            .filter(Action.category.in_(['enter channel', 'exit channel']))
        if filter_time_fn:
            query = query.filter(Action.creation_time >= filter_time_fn())

        response = pd.read_sql(query.statement, sqlalchemy_session.bind)
        agg = response.groupby("user_id", as_index=False).apply(lambda x: utilities.get_total_time_for_time(x, filter_time_fn))
        agg.columns = [agg.columns[0], "study_time"]
        agg.set_index("user_id", inplace=True)
        to_insert = agg["study_time"].to_dict()
        redis_client.zadd(sorted_set_name, to_insert)


if __name__ == '__main__':
    utilities.recreate_db(Base)
    generate_df()
    generate_sorted_set()
