import locale

import pandas as pd

locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
from sqlalchemy.orm import sessionmaker
from models import *

load_dotenv("dev.env")
database_name = os.getenv("database")

engine = utilities.get_engine()
Session = sessionmaker(bind=engine)
sqlalchemy_session = Session()
redis_client = utilities.get_redis_client()

df = pd.read_csv("user_files/user_stats.csv", index_col="id")
df = df[~df.index.duplicated(keep='first')]
df.fillna(0, inplace=True)
daily_name = utilities.get_rank_categories(flatten=True)["daily"]
# Optionally we could reset certain stats
# df[daily_name] = 0

# Dataframe might have weird default data types
df["current_streak"] = df["current_streak"].astype(int)
df["longest_streak"] = df["longest_streak"].astype(int)
dictionary = df.to_dict()


def insert_df():
    user_df = df[["current_streak", "longest_streak"]]
    user_df["id"] = user_df.index.astype(int)

    user_df.to_sql('user', con=engine, if_exists="append", index=False)
    sqlalchemy_session.commit()


def insert_sorted_set():
    filter_time_fn_li = [utilities.get_day_start, utilities.get_week_start, utilities.get_month_start,
                         utilities.get_earliest_start]

    category_key_names = utilities.get_rank_categories(flatten=True)
    for (category_key_name, sorted_set_name), filter_time_fn in zip(category_key_names.items(), filter_time_fn_li):
        if category_key_name not in dictionary:
            print(f"{category_key_name} missing")
            continue

        to_insert = dictionary[category_key_name]
        # TODO handle it smarter in fetch_all
        for k, v in to_insert.items():
            if type(v) != int and type(v) != float:
                to_insert[k] = locale.atoi(v)
            # Convert minutes to hours
            to_insert[k] /= 60
        redis_client.zadd(sorted_set_name, to_insert)


if __name__ == '__main__':
    utilities.recreate_db(Base)
    insert_df()
    insert_sorted_set()
