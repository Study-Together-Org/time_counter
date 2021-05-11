#!/usr/bin/env python
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os, sys
import redis
from models import Action, User, DailyHours
import argparse

mode="development"

# command line arguments
parser = argparse.ArgumentParser(description="Migrate redis sets to mysql")
parser.add_argument('time', help="The time of the redis set to migrate in format hh:mm:ss")
parser.add_argument('--date', default=datetime.today().strftime('%Y-%m-%d'), help="The date of the redis set to migrate in format %Y-%m-%d. Default is today's date")
args = parser.parse_args()

sorted_set_name = f"daily_{args.date} {args.time}"
sorted_set_datetime = datetime.strptime(sorted_set_name, 'daily_%Y-%m-%d %H:%M:%S')
print(sorted_set_name, sorted_set_datetime)

echo = True

engine = create_engine(
    f'mysql+pymysql://{os.getenv("sql_user")}:{os.getenv("sql_password")}@{os.getenv("sql_host")}/{os.getenv("sql_database")}',
    echo=echo)

redis_client = redis.Redis(
    host=os.getenv("redis_host"),
    port=os.getenv("redis_port"),
    db=int(os.getenv("redis_db_num")),
    username=os.getenv("redis_username"),
    password=os.getenv("redis_password"),
    decode_responses=True
)

# insert from redis set into mysql
Session = sessionmaker(bind=engine)
session = Session()

for rank, row in enumerate(redis_client.zrangebyscore(sorted_set_name, "-inf", "inf", withscores=True)):
    # get time from in_session
    # do we need this?
    in_session_time = redis_client.hget(f"in_session_{sorted_set_name}", row[0])
    in_session_time = float(in_session_time) if in_session_time else 0

    if mode == "production":
        session.add(DailyHours(user_id=row[0], timestamp=sorted_set_datetime, study_time=round(row[1], 3), rank=rank))
    else:
        print(f"user_id={row[0]}, timestamp={sorted_set_datetime}, study_time={round(row[1], 3)}, rank={rank}")

# uncomment for production
if mode == "production":
    session.commit()
    redis_client.delete(sorted_set_name)
    redis_client.delete(f"in_session_{sorted_set_name}")
