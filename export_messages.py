import discord
from discord.ext import commands
import asyncio

import os

from discord import Intents
from discord.ext import commands
from dotenv import load_dotenv

import dbmanagement as dbm

load_dotenv("dev.env")


client = commands.Bot(command_prefix="!", intents=Intents.all())

@bot.command()
async def copy(ctx):
    with open("file.txt", "w") as f:
        async for message in ctx.history(limit=1000):
            f.write(message.content + "\n")

    await ctx.send("Done!")