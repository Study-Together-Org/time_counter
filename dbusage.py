import os

from discord import Intents
from discord.ext import commands
from dotenv import load_dotenv

import dbmanagement as dbm

load_dotenv("dev.env")


client = commands.Bot(command_prefix="!", intents=Intents.all())
client.load_extension('study_executor')
client.pool = None
client.sql = dbm.MySQL(client)
client.run(os.getenv('bot_token'))

print("Done")
