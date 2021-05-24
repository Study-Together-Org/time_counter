# TODO test - Worry about duplicate random samples if CDCI
import random

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker

import models
from models import *

load_dotenv("../dev.env")
seed = int(utilities.config["seed"])
random.seed(seed)
np.random.seed(seed)
database_name = os.getenv("database")

engine = utilities.get_engine()
Session = sessionmaker(bind=engine)
sqlalchemy_session = Session()
redis_client = utilities.get_redis_client()

# Base = declarative_base()

# user_size = 12003
# action_size = int(1e6 / 2)  # user_size * 30 * 3 + 1
# enter_exit_proportion = 1

user_size = 210
action_size = user_size * 30 * 3 + 1


def random_data(df):
    # Note some fake data generation functions are iterative; yet it is not slow for now
    size = len(df)
    # Since a user will join, leave, join, ... instead purely random choice of these two, we just need to randomize the start
    enter_exit_population = models.action_categories[:2] * (2 + size)
    random_offset = np.random.randint(0, 2)
    # num_enter_exit = int(size * enter_exit_proportion)
    # num_else = size - num_enter_exit
    enter_exit_sample = enter_exit_population[random_offset: random_offset + size]
    # else_sample = np.random.choice(models.action_categories[2:], num_else).tolist()
    # random_categories = list(map(next, random.sample([iter(enter_exit_sample)]*num_enter_exit + [iter(else_sample)]*num_else, size)))
    df["category"] = enter_exit_sample
    df["creation_time"] = utilities.generate_datetime(size=size)
    return df


def generate_df():
    user_df = pd.DataFrame()
    user_df['id'] = utilities.generate_discord_user_id(user_size)

    action_df = pd.DataFrame(columns=['user_id', 'category', 'detail', 'creation_time'])
    # It deliberately makes the last member have 0 action as a test case
    action_df["user_id"] = np.random.choice(user_df["id"], size=action_size)

    action_df = action_df.groupby("user_id").apply(random_data)
    action_df["detail"] = utilities.generate_random_number(size=action_size)
    # "append" means not creating a new table
    user_df.to_sql('user', con=engine, if_exists="append", index=False)
    action_df.to_sql('action', con=engine, if_exists="append", index=False)
    # TODO test - generate streak data
    # I have not found an efficient way to calc streak data matching the above actions; We might have to generate independent fake data for streaks
    sqlalchemy_session.commit()


def generate_sorted_set():
    filter_time_fn_li = [utilities.get_day_start, utilities.get_week_start, utilities.get_month_start,
                         utilities.get_earliest_start]
    category_key_names = utilities.get_rank_categories().values()

    for sorted_set_name, filter_time_fn in zip(category_key_names, filter_time_fn_li):
        query = sqlalchemy_session.query(Action.user_id, Action.category, Action.creation_time) \
            .filter(Action.category.in_(['start channel', 'end channel']))

        if filter_time_fn:
            query = query.filter(Action.creation_time >= filter_time_fn())

        response = pd.read_sql(query.statement, sqlalchemy_session.bind)
        agg = response.groupby("user_id", as_index=False).apply(
            lambda x: utilities.get_total_time_for_window(x, filter_time_fn))
        agg.columns = [agg.columns[0], "study_time"]
        agg.set_index("user_id", inplace=True)
        to_insert = agg["study_time"].to_dict()
        redis_client.zadd(sorted_set_name, to_insert)

        if sorted_set_name == utilities.get_rank_categories()["monthly"]:
            if os.getenv("STUDY_TOGETHER_MODE") == "dev":
                for user_id in to_insert:
                    to_insert[user_id] += utilities.generate_random_number(length=3)[0]

            redis_client.zadd("all_time", to_insert)


if __name__ == '__main__':
    utilities.recreate_db(Base)
    generate_df()
    generate_sorted_set()
