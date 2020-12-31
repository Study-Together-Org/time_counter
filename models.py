import os
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import ForeignKey, Column, INTEGER, String
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.mysql import DATETIME, FLOAT, INTEGER

from dotenv import load_dotenv
import utilities

load_dotenv("dev.env")

# con = pymysql.connect(, os.getenv("user"), , autocommit=True)
database_name = os.getenv("database")
varchar_length = int(os.getenv("varchar_length"))
DATETIME = DATETIME(fsp=int(os.getenv("time_fsp")))
Base = declarative_base()

action_categories = [
    "enter channel", "exit channel", "start screenshare", "end screenshare", "start video", "end video", "start voice",
    "end voice", "start timer", "end timer"
]
me_categories = ["daily", "weekly", "monthly", "all_time"]


class User(Base):
    # How to make it just use the class name instead of hard coding the table name?
    __tablename__ = 'user'
    id = Column(INTEGER, primary_key=True)
    discord_user_id = Column(String(varchar_length), unique=True)
    longest_streak = Column(INTEGER, server_default="0")
    current_streak = Column(INTEGER, server_default="0")


class Action(Base):
    # How to make it just use the class name instead of hard coding the table name?
    __tablename__ = 'action'
    id = Column(INTEGER, primary_key=True)
    user_id = Column(INTEGER, ForeignKey('user.id'), nullable=False, index=True)
    category = Column(String(varchar_length), nullable=False)
    detail = Column(String(varchar_length))
    creation_time = Column(DATETIME, default=utilities.get_time)

    user = relationship("User", back_populates="action")


# This most be in global scope for correct models
User.action = relationship("Action", order_by=Action.id, back_populates="user")

if __name__ == '__main__':
    utilities.recreate_db(Base)
