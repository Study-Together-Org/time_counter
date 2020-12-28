import os
from dotenv import load_dotenv
import utilities
import models
from sqlalchemy.orm import sessionmaker
import pandas as pd
from faker import Faker
from collections import defaultdict
from sqlalchemy import create_engine
import numpy as np

load_dotenv("dev.env")
np.random.seed(int(os.getenv("seed")))
database_name = os.getenv("database")

engine = utilities.get_engine()
Session = sessionmaker(bind=engine)
session = Session()

user_size = 2100
action_size = user_size * 30 * 30 + 1

user_df = pd.DataFrame(columns=['discord_user_id'])
user_df['discord_user_id'] = utilities.generate_discord_user_id(user_size)

action_df = pd.DataFrame(columns=['user_id', 'category', 'detail', 'creation_time'])
# It deliberately makes the last member not have any action
action_df["user_id"] = np.random.randint(low=1, high=user_size, size=action_size)


def random_data(df):
    size = len(df)
    sample_start = np.random.randint(low=1, high=size)
    category_sample = models.action_categories[:2] * 2 * size
    df["category"] = category_sample[sample_start: sample_start + size]
    df["detail"] = "private channel 13"
    df["creation_time"] = utilities.generate_datetime(size=size)
    return df


action_df = action_df.groupby("user_id").apply(random_data)

user_df.to_sql('user', con=engine, if_exists="append", index=False)
action_df.to_sql('action', con=engine, if_exists="append", index=False)
session.commit()
