import os

import hjson
from discord import Intents
from discord.ext import commands
from dotenv import load_dotenv

import utilities

load_dotenv("dev.env")

client = commands.Bot(command_prefix=os.getenv("prefix"), intents=Intents.all())

with open("config.hjson") as f:
    config = hjson.load(f)


@client.event
async def on_ready():
    guild = client.get_guild(utilities.get_guildID())
    role_names = list(config["study_roles"].keys())
    role_names.reverse()
    for role_name in role_names:
        await guild.create_role(name=role_name, hoist=True, mentionable=True)

    await client.logout()

client.run(os.getenv('bot_token'))
print("Done")
