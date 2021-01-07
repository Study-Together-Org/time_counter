import asyncio
import logging
import os
from datetime import datetime, timedelta
from time import sleep

from discord import Intents
from discord.ext import commands
from dotenv import load_dotenv

import dbmanagement as dbm
import utilities

load_dotenv("dev.env")

client = commands.Bot(command_prefix=os.getenv("prefix"), intents=Intents.all())
client.load_extension('study_executor')
client.pool = None
client.sql = dbm.MySQL(client)
client.run(os.getenv('bot_token'))
