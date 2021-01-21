import os

import hjson
from discord import Intents
from discord.ext import commands
from dotenv import load_dotenv
import copy
import utilities
from collections import defaultdict

load_dotenv("dev.env")

client = commands.Bot(command_prefix=os.getenv("prefix"), intents=Intents.all())

with open("config.hjson") as f:
    config = hjson.load(f)


@client.event
async def on_ready():
    guild = client.get_guild(utilities.get_guildID())
    role_name_to_obj = {role.name: {"name": role.name, "mention": role.mention} for role in guild.roles}
    key_name = ("test_" if os.getenv("mode") == "test" else "") + "study_roles"

    if os.getenv("mode") == "test":
        utilities.config["test_study_roles"] = copy.deepcopy(utilities.config["study_roles"])

    for key, val in utilities.config["study_roles"].items():
        print(role_name_to_obj[key])
        utilities.config[key_name][key]["name"] = role_name_to_obj[key]["name"]
        utilities.config[key_name][key]["mention"] = role_name_to_obj[key]["mention"]

    with open("config.hjson", "w") as f:
        hjson.dump(utilities.config, f)

    await client.logout()


client.run(os.getenv('bot_token'))
print("Done")

# TODO fix - now we have to make a variable name change in utilities for avoid errrors for this script
