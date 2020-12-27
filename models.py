import os
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import ForeignKey, Column, Integer, String
from sqlalchemy.orm import relationship
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
    __tablename__ = 'user'
    id = Column(Integer, primary_key=True)
    discord_user_id = Column(String(varchar_length))

class Action(Base):
    # How to make it just use the class name instead of hard coding the table name?
    __tablename__ = 'action'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('user.id'), nullable=False)
    category = Column(String(varchar_length), nullable=False)
    detail = Column(String(varchar_length))
    creation_time = Column(DATETIME, default=utilities.get_utctime)

    user = relationship("User", back_populates="action")

User.action = relationship("Action", order_by=Action.id, back_populates="user")


if __name__ == '__main__':
    utilities.recreate_db(Base, engine)
