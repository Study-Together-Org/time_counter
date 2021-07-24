import logging
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import dateparser
import hjson
import pandas as pd
import psutil
import redis
import shortuuid
from dotenv import load_dotenv
from faker import Faker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy_utils import database_exists, create_database

# scripts that import this one will assume the following statement is run
load_dotenv(f"{os.getenv('STUDY_TOGETHER_MODE')}.env")

with open(f"{os.getenv('STUDY_TOGETHER_MODE')}_config.hjson") as f:
    config = hjson.load(f)

Faker.seed(config["seed"])
fake = Faker()

num_uuid = shortuuid.ShortUUID()
num_uuid.set_alphabet("0123456789")  # uuid that only has numbers
back_range = 61

role_settings = config["study_roles"]
role_name_to_begin_hours = {role_name: float(role_info['hours'].split("-")[0]) for role_name, role_info in
                            role_settings.items()}
role_names = list(role_settings.keys())

num_intervals = 24 * 1
delta = timedelta(days=1)
interval = delta / num_intervals


def get_rank_categories(flatten=False, string=True):
    """
    In general, it's easier to convert datetime objects to strings than the other way around; this function can give both
    """
    rank_categories = {}

    if flatten:
        timepoints = get_earliest_timepoint(prefix=True, string=string)
    else:
        timepoints = get_timepoints()
        if string:
            timepoints = ["daily_" + str(timepoint) for timepoint in timepoints]

    rank_categories["daily"] = timepoints
    rank_categories["weekly"] = f"weekly_{get_week_start()}"
    rank_categories["monthly"] = f"monthly_{get_month()}"
    rank_categories["all_time"] = "all_time"

    return rank_categories


def get_logger(job_name, filename):
    logger = logging.getLogger(job_name)
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(filename=filename, encoding='utf-8', mode='a')
    handler.setFormatter(logging.Formatter('%(message)s:%(levelname)s:%(name)s:%(process)d'))
    logger.addHandler(handler)

    return logger


def get_guildID():
    guildID = int(os.getenv("guildID"))
    return guildID


def recreate_db(Base):
    redis_client = get_redis_client()
    engine = get_engine()
    redis_client.flushall()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def get_engine(echo=False):
    engine = create_engine(
        f'mysql+pymysql://{os.getenv("sql_user")}:{os.getenv("sql_password")}@{os.getenv("sql_host")}/{os.getenv("sql_database")}',
        echo=echo, pool_pre_ping=True)

    if not database_exists(engine.url):
        create_database(engine.url)

    return engine


def get_timezone_session():
    engine = create_engine(os.getenv("timezone_db"))
    session = sessionmaker(bind=engine)()
    return session


def get_time():
    now = datetime.utcnow()
    return now


def get_num_days_this_month():
    return datetime.utcnow().day


def get_day_start():
    date = datetime.combine(datetime.utcnow().date(), datetime.min.time())
    offset = timedelta(hours=config["business"]["update_time"])

    if datetime.utcnow() < date + offset:
        offset -= timedelta(days=1)

    return date + offset


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


def get_earliest_timepoint(starting_point=None, string=False, prefix=False):
    if not starting_point:
        starting_point = get_time() - delta

    offset = interval - (starting_point - datetime(1900, 1, 1)) % interval

    if offset == interval:
        offset -= interval

    earliest_timepoint = starting_point + offset
    return f"{'daily_' if prefix else ''}{earliest_timepoint}" if string else earliest_timepoint


def parse_time(timepoint, zone_obj=ZoneInfo(config["business"]["timezone"])):
    if timepoint is None:
        timepoint = ""

    if len(timepoint) > 30:
        return

    # This library is very flexible; some functions even support non-English languages
    parsed = dateparser.parse(timepoint, date_formats=["%H:%M", "%H:%m", "%h:%M", "%h:%m", "%H", "%h"])

    if not parsed:
        return

    if parsed.replace(tzinfo=zone_obj) >= datetime.now(zone_obj):
        parsed -= timedelta(days=1)
    elif parsed.replace(tzinfo=zone_obj) < datetime.now(zone_obj) - timedelta(days=1):
        parsed += timedelta(days=1)

    return parsed


def get_closest_timepoint(full_time_point, prefix=False):
    cur_time = get_time()

    if full_time_point > cur_time:
        full_time_point -= timedelta(days=1)

    timepoint_to_use = get_earliest_timepoint(full_time_point, string=True)

    return f"{'daily_' if prefix else ''}{timepoint_to_use}"


def get_timepoints():
    earliest_timepoint = get_earliest_timepoint(prefix=False)
    timepoints = [earliest_timepoint + i * interval for i in range(num_intervals)]
    return timepoints


def timedelta_to_hours(td):
    return td.total_seconds() / 3600


async def get_user_timeinfo(ctx, user, timepoint):
    from timezone_bot import query_zone
    user_timezone = await query_zone(user)

    if user_timezone == "Not set":
        await ctx.send(
            f"**You can set a time zone by following `{config['timezone_prefix']}help`**")
        user_timezone = config["business"]["timezone"]

    zone_obj = ZoneInfo(user_timezone)
    # Here the placeholder is not limited to "-"
    user_timepoint = parse_time(timepoint, zone_obj=zone_obj)

    if user_timepoint:
        user_timepoint = user_timepoint.replace(tzinfo=zone_obj)
        std_zone_obj = ZoneInfo(config["business"]["timezone"])
        utc_timepoint = user_timepoint.astimezone(std_zone_obj)
        timepoint = get_closest_timepoint(utc_timepoint.replace(tzinfo=None), prefix=False)
    else:
        timepoint = get_closest_timepoint(get_earliest_timepoint(), prefix=False)

    display_timepoint = dateparser.parse(timepoint).replace(
        tzinfo=ZoneInfo(config["business"]["timezone"]))
    display_timepoint = display_timepoint.astimezone(zone_obj).strftime(config["datetime_format"].split(".")[0])

    return "daily_" + timepoint, user_timezone, display_timepoint


def round_num(num, ndigits=None):
    if not ndigits:
        ndigits = int(os.getenv("display_num_decimal"))

    return round(num, ndigits=ndigits)


def calc_total_time(data):
    if not data:
        return 0

    total_time = timedelta(0)
    start_idx = 0
    end_idx = len(data) - 1

    if data[0]["category"] == "end channel":
        total_time += data[0]["creation_time"] - get_month_start()
        start_idx = 1

    if data[-1]["category"] == "start channel":
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
        if df["category"].iloc[0] == "end channel":
            total_time += df["creation_time"].iloc[0] - pd.to_datetime(get_start_fn())
            start_idx = 1

        if df["category"].iloc[-1] == "start channel":
            total_time += pd.to_datetime(get_time()) - df["creation_time"].iloc[-1]
            end_idx -= 1

    df = df.iloc[start_idx: end_idx]
    enter_df = df[df["category"] == "start channel"]["creation_time"]
    exit_df = df[df["category"] == "end channel"]["creation_time"]
    total_time += pd.to_timedelta((exit_df.values - enter_df.values).sum())
    total_time = timedelta_to_hours(total_time)

    if total_time < 0:
        raise Exception("study time below zero")

    return total_time


def get_redis_client():
    return redis.Redis(
        host=os.getenv("redis_host"),
        port=os.getenv("redis_port"),
        db=int(os.getenv("redis_db_num")),
        username=os.getenv("redis_username"),
        password=os.getenv("redis_password"),
        decode_responses=True
    )


def get_role_status(role_name_to_obj, hours_cur_month):
    cur_role_idx = -1

    for idx, begin_hours in enumerate(role_name_to_begin_hours.values()):
        if begin_hours <= hours_cur_month:
            cur_role_idx = idx
        else:
            break

    # new members should have None as prev_role and cur_role
    prev_role = role_name_to_obj[role_names[cur_role_idx - 1]] if cur_role_idx > 0 else None
    cur_role = role_name_to_obj[role_names[cur_role_idx]] if cur_role_idx >= 0 else None
    # assuming the default cur_role for new members is -1
    next_role_idx = cur_role_idx + 1
    next_role = role_name_to_obj[role_names[cur_role_idx + 1]] if next_role_idx < len(role_names) else None
    time_to_next_role = round_num(role_name_to_begin_hours[next_role["name"]] - hours_cur_month) if next_role_idx < len(role_names) else None

    return prev_role, cur_role, next_role, time_to_next_role


def get_last_line():
    try:
        with open('heartbeat.log', 'rb') as f:
            f.seek(-2, os.SEEK_END)
            while f.read(1) != b'\n':
                f.seek(-2, os.SEEK_CUR)
            line = f.readline().decode()
        return line
    except OSError:
        return None


def get_last_time(line):
    last_line = " ".join(line.split()[:2])
    return datetime.strptime(last_line, config["datetime_format"])


def kill_last_process(line):
    if not line:
        return

    parts = line.split()
    pid = int(parts[-1].split(":")[-1])

    try:
        process = psutil.Process(pid)

        if "time_counter.py" in " ".join(process.cmdline()):
            process.terminate()
            print(f"{pid} killed")

    except:
        pass


async def get_redis_rank(redis_client, sorted_set_name, user_id):
    rank = redis_client.zrevrank(sorted_set_name, user_id)

    if rank is None:
        redis_client.zadd(sorted_set_name, {user_id: 0})
        rank = redis_client.zrevrank(sorted_set_name, user_id)

    return 1 + rank


async def get_redis_score(redis_client, sorted_set_name, user_id):
    score = redis_client.zscore(sorted_set_name, user_id) or 0
    return round_num(score)


async def get_user_stats(redis_client, user_id, timepoint=get_earliest_timepoint(string=True, prefix=True)):
    stats = dict()
    category_key_names = list(get_rank_categories().values())

    for sorted_set_name in [timepoint] + category_key_names[1:]:
        stats[sorted_set_name] = {
            "rank": await get_redis_rank(redis_client, sorted_set_name, user_id),
            "study_time": await get_redis_score(redis_client, sorted_set_name, user_id)
        }

    return stats


def get_stats_diff(prev_stats, cur_stats):
    prev_studytime = [item["study_time"] for item in prev_stats.values()]
    cur_studytime = [item["study_time"] for item in cur_stats.values()]
    diff = [round_num(cur - prev) for prev, cur in zip(prev_studytime, cur_studytime)]

    return diff


def check_stats_diff(prev_stats, mid_stats, time_to_stay, multiplier, redis_tolerance):
    diff = get_stats_diff(prev_stats, mid_stats)
    excess = [hours * 3600 - time_to_stay * multiplier for hours in diff]
    is_all_increment_right = [0 <= hours <= redis_tolerance for hours in excess]
    return all(is_all_increment_right)


def sleep(seconds):
    # TODO (?) print decimals
    seconds = math.ceil(seconds)

    for remaining in range(seconds, 0, -1):
        sys.stdout.write("\r")
        sys.stdout.write("{:2d} seconds remaining.".format(remaining))
        sys.stdout.flush()
        import time
        time.sleep(1)


def increment_studytime(category_key_names, redis_client, user_id, in_session_incrs, std_incr=None, last_time=None):
    if std_incr is None:
        std_incr = timedelta_to_hours(get_time() - last_time)

    monthly_now = "undefined"
    all_time_now = "undefined"

    for i, sorted_set_name in enumerate(category_key_names):
        incr = in_session_incrs[i] if i < num_intervals else std_incr
        change = redis_client.zincrby(sorted_set_name, incr, user_id)
        if i == len(category_key_names) - 2:
            monthly_now = change
        elif i == len(category_key_names) - 1:
            all_time_now = change

    return monthly_now, all_time_now


def commit_or_rollback(session):
    try:
        session.commit()
    except Exception as e:
        print(e)
        session.rollback()
        raise


def get_role_id(name):
    return config["other_roles"][name]
