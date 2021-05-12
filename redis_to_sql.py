#!/usr/bin/env python
import argparse
import os
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker

import utilities
from models import DailyStudyTime

load_dotenv("dev.env")

mode = "development"

# command line arguments
parser = argparse.ArgumentParser(description="Migrate redis sets to mysql")
parser.add_argument('time', help="The time of the redis set to migrate in format hh:mm:ss")
parser.add_argument('--date', default=datetime.today().strftime('%Y-%m-%d'),
                    help="The date of the redis set to migrate in format Y-m-d. Default is today's date")
args = parser.parse_args()

# get sorted_set_datetime
sorted_set_name = f"daily_{args.date} {args.time}"
sorted_set_datetime = datetime.strptime(sorted_set_name, f"daily_{os.getenv('datetime_format').split('.')[0]}")

# get engine
engine = utilities.get_engine()
# get redis client
redis_client = utilities.get_redis_client()

# get session object from engine
Session = sessionmaker(bind=engine)
session = Session()

# build to_insert list
to_insert = []
for rank, row in enumerate(redis_client.zrangebyscore(sorted_set_name, "-inf", "inf", withscores=True)):
    if mode == "production":
        to_insert.append({
            'user_id': row[0],
            'timestamp': sorted_set_datetime,
            'studytime': round(row[1], 3),
            'rank': rank
        })
    else:
        print(f"user_id={row[0]}, timestamp={sorted_set_datetime}, study_time={round(row[1], 3)}, rank={rank}")

if mode == "production":
    engine.execute(
        DailyStudyTime.__table__.insert(),
        to_insert
    )
    session.commit()
    redis_client.delete(sorted_set_name)
    redis_client.delete(f"in_session_{sorted_set_name}")
