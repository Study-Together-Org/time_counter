import os

import hjson
from discord import Intents
from discord.ext import commands
from dotenv import load_dotenv

import utilities

load_dotenv("../dev.env")

client = commands.Bot(command_prefix=utilities.config["prefixes"], intents=Intents.all())

with open("../config.hjson") as f:
    config = hjson.load(f)


@client.event
async def on_ready():
    guild = client.get_guild(utilities.get_guildID())
    monitored_categories = dict()

    for category in guild.categories:
        if category.name[0] == "🔊" or category.name in ["staff", "STAFF"]:
            monitored_categories[category.name] = category.id

    key_name = utilities.config["monitored_categories"]
    config[key_name] = monitored_categories

    with open("../config.hjson", "w") as f:
        hjson.dump(config, f)

    await client.logout()

client.run(os.getenv('bot_token'))
print("Done")
