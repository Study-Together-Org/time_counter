import os
import shortuuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from faker import Faker
import pandas as pd
import numpy as np
import redis
import hjson
# from models import User

from dotenv import load_dotenv

load_dotenv("dev.env")

Faker.seed(42)
fake = Faker()

num_uuid = shortuuid.ShortUUID()
num_uuid.set_alphabet("0123456789")

back_range = 61

with open("config.hjson") as f:
    config = hjson.load(f)

role_settings = config["roles"]

role_name_to_begin_hours = {role_name: float(role_info['hours'].split("-")[0]) for role_name, role_info in
                            role_settings.items()}
role_names = list(role_settings.keys())


def get_guildID():
    guildID_key_name = ("test_" if os.getenv("mode") == "test" else "") + "guildID"
    guildID = int(os.getenv(guildID_key_name))
    return guildID

def recreate_db(Base):
    redis_client = get_redis_client()
    redis_client.flushall()
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def get_engine(echo=True):
    return create_engine(
        f'mysql+pymysql://{os.getenv("sql_user")}:{os.getenv("sql_password")}@{os.getenv("sql_host")}/{os.getenv("sql_database")}',
        echo=echo)


def get_time():
    now = datetime.utcnow()
    return now


def get_num_days_this_month():
    return datetime.utcnow().day


def get_day_start():
    dt = datetime.combine(datetime.utcnow().date(), datetime.min.time())
    offset = timedelta(hours=config["business"]["update_time"])

    if datetime.utcnow() - dt < offset:
        offset -= timedelta(days=1)

    return dt + offset


def get_tomorrow_start():
    return get_day_start() + timedelta(days=1)


def get_week_start():
    return get_day_start() - timedelta(days=get_day_start().weekday() % 7)


def get_month_start():
    given_date = get_day_start()
    first_day_of_month = given_date - timedelta(days=int(given_date.strftime("%d")) - 1)
    return first_day_of_month


def get_earliest_start():
    return datetime.utcnow() - timedelta(days=back_range)


def get_month():
    return datetime.utcnow().strftime("%B")


def timedelta_to_hours(td):
    return round_num(td.total_seconds() / 3600)


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

    total_time = timedelta_to_hours(total_time)
    return total_time


def generate_random_number(size=1, length=18):
    res = [fake.random_number(digits=length, fix_len=True) for _ in range(size)]
    return res


def generate_discord_user_id(size=1, length=18):
    res = []

    if size >= 2:
        res += [int(os.getenv("tester_human_discord_user_id")), int(os.getenv("tester_bot_token_discord_user_id"))]
        size -= 2

    res += generate_random_number(size, length)

    return res


def generate_datetime(size=1, start_date=f'-{back_range}d'):
    return sorted([fake.past_datetime(start_date=start_date, tzinfo=timezone.utc) for _ in range(size)])


def generate_username(size=1):
    return [fake.user_name() for _ in range(size)]


def get_total_time_for_window(df, get_start_fn=None):
    df = df.sort_values(by=['creation_time'])
    total_time = timedelta(0)
    start_idx = 0
    end_idx = len(df)

    if len(df):
        if df["category"].iloc[0] == "exit channel":
            total_time += df["creation_time"].iloc[0] - pd.to_datetime(get_start_fn())
            start_idx = 1

        if df["category"].iloc[-1] == "enter channel":
            total_time += pd.to_datetime(get_time()) - df["creation_time"].iloc[-1]
            end_idx -= 1

    df = df.iloc[start_idx: end_idx]
    enter_df = df[df["category"] == "enter channel"]["creation_time"]
    exit_df = df[df["category"] == "exit channel"]["creation_time"]
    total_time += pd.to_timedelta((exit_df.values - enter_df.values).sum())
    total_time = timedelta_to_hours(total_time)

    if total_time < 0:
        raise Exception("study time below zero")

    return total_time


def get_redis_client():
    return redis.Redis(host=os.getenv("redis_host"), port=os.getenv("redis_port"), db=int(os.getenv("redis_db_num")),
                       decode_responses=True)


def get_role_status(role_name_to_obj, hours_cur_month):
    cur_role_name = role_names[0]
    next_role_name = role_names[1]

    for role_name, begin_hours in role_name_to_begin_hours.items():
        if begin_hours <= hours_cur_month:
            cur_role_name = role_name
        else:
            next_role_name = role_name
            break
    cur_role = role_name_to_obj[cur_role_name]
    # new members
    if hours_cur_month < role_name_to_begin_hours[cur_role_name]:
        cur_role = None

    next_role, time_to_next_role = (
        role_name_to_obj[next_role_name], role_name_to_begin_hours[next_role_name] - hours_cur_month) \
        if cur_role_name != role_names[-1] else (None, None)

    return cur_role, next_role, time_to_next_role
