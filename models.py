import os
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String
from sqlalchemy.dialects.mysql import DATETIME

from dotenv import load_dotenv
import utilities

load_dotenv("dev.env")

# con = pymysql.connect(, os.getenv("user"), , autocommit=True)
database_name = os.getenv("database")
varchar_length = int(os.getenv("varchar_length"))
DATETIME = DATETIME(fsp=int(os.getenv("time_fsp")))

engine = utilities.get_engine()
Base = declarative_base()


class User(Base):
    # How to make it just use the class name instead of hard coding the table name?
    __tablename__ = 'User'
    id = Column(Integer, primary_key=True)
    discord_user_id = Column(String(varchar_length))


class Action(Base):
    # How to make it just use the class name instead of hard coding the table name?
    __tablename__ = 'Action'
    id = Column(Integer, primary_key=True)
    User_id = Column(Integer, nullable=False)
    category = Column(String(varchar_length), nullable=False)
    detail = Column(String(varchar_length))
    creation_time = Column(DATETIME, default=utilities.get_utctime)


Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
