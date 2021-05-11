#!/usr/bin/env python
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
import os
import redis
from models import Action, User, DailyHours

timepoint = "18:00:00"
date_today = datetime.today().strftime('%Y-%m-%d')
sorted_set_name = f"{date_today} {timepoint}"
sorted_set_datetime = datetime.strptime(sorted_set_name, '%Y-%m-%d %H:%M:%S')

# this is for the set that is going out of bounds, so 24 hours ago pretty much
# we want to move the daily and in_session_daily sets to sql
# sql table called `dailyhours`

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

DailyHours.__table__.create(engine)

# # also need to handle in_session set
#
# # insert from redis set into mysql
# with Session(engine) as session:
#     for rank, row in enumerate(redis_client.zrangebyscore(sorted_set_name, "-inf", "inf", withscores=True)):
#         # session.add(DailyHours(user_id=row[0], timestamp=sorted_set_datetime, study_time=row[1], rank=rank))
#         print(user_id=row[0], timestamp=sorted_set_datetime, study_time=row[1], rank=rank)
#
#     # session.commit()
#
# # delete redis set
# # redis_client.delete(sorted_set_name)
#
