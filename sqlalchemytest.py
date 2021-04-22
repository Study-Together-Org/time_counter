#!/usr/bin/env python


import utilities
from models import Action, User
from sqlalchemy.orm import sessionmaker

eengine = utilities.get_engine()
Session = sessionmaker(bind=engine)
sqlalchemy_session = Session()
redis_client = utilities.get_redis_client()ngine = utilities.get_engine()
Session = sessionmaker(bind=engine)
sqlalchemy_session = Session()
redis_client = utilities.get_redis_client()

# get the list of users with their monthly study hours
users = sqlalchemy_session.query(User).all()
# sort users by id

monthly_session_name = utilities.get_rank_categories()["monthly"]
users_monthly_hours = redis_client.zrange(monthly_session_name, 0, -1)
# sort users by id? don't need to if we use dictionaries
user_dict = {}
for user in users:
    user_dict[user.id] = 0

for user_monthly_hours in users_monthly_hours:
    user_dict[user_monthly_hours[0]] = user_monthly_hours[1]

user_list = []
for key, value in user_dict.items():
    user_list.append([key, value])

# need to get the users monthly hours, this comes from redis not sql
print(user_list[0:10])
