import os

from discord import Intents
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv("dev.env")

client = commands.Bot(command_prefix=os.getenv("prefix"), intents=Intents.all())
client.load_extension('study_executor')
client.run(os.getenv('bot_token'))
