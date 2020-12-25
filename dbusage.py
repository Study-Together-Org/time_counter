from discord.ext import commands
import os
import discord
from discord import Intents
import logging
import dbmanagement as dbm
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

client = commands.Bot(command_prefix="!", intents=Intents.all())


@client.event
async def on_ready():
    if client.pool is None:
        await client.sql.init()
    print('We have logged in as {0.user}'.format(client))


# @client.command()
# async def test(ctx):
#     # Then whenever you need to use it
#     # response = await client.sql.query("SELECT * FROM studies WHERE user_id = %s", user_id)
#     # My class manages arguments
#     # await ctx.send(str(response))
#     print("test")


@client.event
async def on_voice_state_update(member, before, after):
    response = await client.sql.query("show tables;")
    print(response)
    print()
    print(member, before, after)


@client.event
async def on_member_join(member):
    guild = member.guild
    if guild.system_channel is not None:
        to_send = 'Welcome {0.mention} to {1.name}!'.format(member, guild)
        await guild.system_channel.send(to_send)
    print(member)
    insert_new_member = f"""
        INSERT INTO User (discord_user_id)
        VALUES ({member.id});
    """

    response = await client.sql.query(insert_new_member)
    if response:
        print(response)

client.pool = None
client.sql = dbm.MySQL(client)
client.run(os.getenv('bot_token'))

