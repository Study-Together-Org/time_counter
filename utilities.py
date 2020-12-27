import os
import shortuuid
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from faker import Faker
# from models import User

Faker.seed(0)
fake = Faker()

from dotenv import load_dotenv

load_dotenv("dev.env")

num_uuid = shortuuid.ShortUUID()
num_uuid.set_alphabet("0123456789")


def recreate_db(Base, engine):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def get_engine():
    return create_engine(
        f'mysql+pymysql://{os.getenv("user")}:{os.getenv("password")}@{os.getenv("host")}/{os.getenv("database")}',
        echo=True)


def get_utctime():
    now = datetime.utcnow()
    return now


def get_month_start():
    given_date = datetime.today().date()
    first_day_of_month = given_date - timedelta(days=int(given_date.strftime("%d")) - 1)
    return first_day_of_month


def round_num(num):
    return round(num, 1)


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
        total_time += get_utctime() - data[-1]["creation_time"]
        end_idx -= 1

    for idx in range(start_idx, end_idx + 1, 2):
        total_time += data[idx + 1]["creation_time"] - data[idx]["creation_time"]

    total_time = round_num(total_time.total_seconds() / 3600)
    return total_time


def generate_discord_user_id(length=18):
    return fake.random_number(digits=length, fix_len=True)
