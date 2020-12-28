import os
import shortuuid
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from faker import Faker
import pandas as pd
import numpy as np

# from models import User

Faker.seed(42)
fake = Faker()

from dotenv import load_dotenv

load_dotenv("dev.env")

num_uuid = shortuuid.ShortUUID()
num_uuid.set_alphabet("0123456789")


def recreate_db(Base, engine):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def get_engine(echo=True):
    return create_engine(
        f'mysql+pymysql://{os.getenv("user")}:{os.getenv("password")}@{os.getenv("host")}/{os.getenv("database")}',
        echo=echo)


def get_time():
    now = datetime.utcnow()
    return now


def get_month_start():
    given_date = datetime.today().date()
    first_day_of_month = given_date - timedelta(days=int(given_date.strftime("%d")) - 1)
    return first_day_of_month


def get_month():
    return datetime.utcnow().strftime("%B")


def round_num(num, ndigits=2):
    return round(num, ndigits=ndigits)


def calc_total_time(data):
    if not data:
        return 0

    total_time = timedelta(0)
    start_idx = 0
    end_idx = len(data) - 1

    if data[0]["category"] == "exit channel":
        total_time += data[0]["creation_time"] - get_month_start()
        start_idx = 1

    if data[-1]["category"] == "enter channel":
        total_time += get_time() - data[-1]["creation_time"]
        end_idx -= 1

    for idx in range(start_idx, end_idx + 1, 2):
        total_time += data[idx + 1]["creation_time"] - data[idx]["creation_time"]

    total_time = round_num(total_time.total_seconds() / 3600)
    return total_time


def generate_discord_user_id(size=1, length=18):
    return [fake.random_number(digits=length, fix_len=True) for _ in range(size)]


def generate_datetime(size=1, start_date='-30d'):
    return sorted([fake.past_datetime(start_date=start_date) for _ in range(size)])


def generate_username(size=1):
    return [fake.user_name() for i in range(size)]


def get_total_time_cur_month(df):
    df = df.sort_values(by=['creation_time'])
    total_time = timedelta(0)
    start_idx = 0
    end_idx = len(df)

    if len(df):
        if df["category"].iloc[0] == "exit channel":
            total_time += df["creation_time"].iloc[0] - pd.to_datetime(get_month_start())
            start_idx = 1

        if df["category"].iloc[-1] == "enter channel":
            total_time += pd.to_datetime(get_time()) - df["creation_time"].iloc[-1]
            end_idx -= 1

    df = df.iloc[start_idx: end_idx]
    enter_df = df[df["category"] == "enter channel"]["creation_time"]
    exit_df = df[df["category"] == "exit channel"]["creation_time"]
    total_time += pd.to_timedelta((exit_df.values - enter_df.values).sum())
    total_time = round_num(total_time.total_seconds() / 3600)

    return total_time
