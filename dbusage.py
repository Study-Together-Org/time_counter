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


# action_categories = [
#     "enter channel", "exit channel", "start screenshare", "end screenshare", "start video", "end video", "start voice",
#     "end voice", "start timer", "end timer"
# ]

def get_utctime():
    from datetime import datetime
    now = datetime.now()
    formatted_date = now.strftime('%Y-%m-%d %H:%M:%S.%f')
    return formatted_date


async def get_User_id(discord_id):
    select_User_id = f"""
        SELECT id from User WHERE discord_user_id = {discord_id} LIMIT 1
    """
    User_id = await client.sql.query(select_User_id)
    return User_id[0]["id"]


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
    User_id = await get_User_id(member.id)
    for action_name, channel in [("exit channel", before.channel), ("enter channel", after.channel)]:
        if channel:
            insert_action = f"""
                INSERT INTO Action (User_id, category, detail, creation_time)
                VALUES ({User_id}, '{action_name}', '{channel.id}', '{get_utctime()}');
            """
            print(insert_action)
            response = await client.sql.query(insert_action)
            if response:
                print(response)


@client.event
async def on_member_join(member):
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
