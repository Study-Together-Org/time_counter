import os
from dotenv import load_dotenv
import utilities
import models
from sqlalchemy.orm import sessionmaker

load_dotenv("dev.env")
database_name = os.getenv("database")

engine = utilities.get_engine()
Session = sessionmaker(bind=engine)
session = Session()

users = [models.User(discord_user_id=utilities.generate_discord_user_id()) for i in range(1, 11)]
session.add_all(users)

session.commit()
