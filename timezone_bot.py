# Original author: https://github.com/JakeStanger/Discord-Friend-Timezones/tree/6eb9537bc9c9e434549c001c1859635c82333b66

import os
import discord
import pytz
from dotenv import load_dotenv
from datetime import datetime
from discord.ext import commands
from fuzzywuzzy import process
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import json
import utilities

load_dotenv("dev.env")
session = utilities.get_timezone_session()

Base = declarative_base()


class UserZone(Base):
    __tablename__ = 'UserZone'

    id = Column(String(18), primary_key=True)
    zone = Column(String(64))


async def get_or_create(session, model, **kwargs):
    instance = session.query(model).filter_by(**kwargs).first()
    if instance:

        return instance
    else:
        instance = model(**kwargs)
        session.add(instance)
        session.commit()

        return instance


description = f"""
A bot that manages your timezone

Typical usage:
Know the 2-letter code for your country (If you don't know it, visit https://gist.github.com/pamelafox/986163)
Set it with `.tzset <your code>`
Check it with `.tzget and .time`
"""
timezone_bot = commands.Bot(command_prefix=os.getenv('timezone_prefix'), description=description)


@timezone_bot.command(name='tzset')
async def set_zone(ctx, *, timezone):
    if timezone in pytz.all_timezones:
        zone = timezone
    else:
        zone = process.extractOne(timezone, pytz.all_timezones)[0]

    user_zone = await get_or_create(session, UserZone, id=ctx.author.id)
    user_zone.zone = zone
    session.commit()

    await ctx.send("Set your time zone to **%s**" % zone)


async def query_zone(user: discord.Member):
    zone = session.query(UserZone).filter_by(id=user.id).first()

    if zone:
        return zone.zone
    else:
        return 'Not set'


async def get_zone_time(zone: str, full=False):
    if zone == 'Not set':
        return zone

    tz = pytz.timezone(zone)
    res = tz.normalize(datetime.utcnow().replace(tzinfo=pytz.utc).astimezone(tz))

    if not full:
        res = res.strftime('%H:%M')

    return res


@set_zone.error
async def info_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send('Please specify a timezone')
    else:
        print(error)


@timezone_bot.command(name='tzget')
async def get_zone(ctx, users: commands.Greedy[discord.Member]):
    if len(users) == 0:
        users = [ctx.author]

    await ctx.send('\n'.join([
        '%s: **%s**' % (user.nick or user.name,
                        await query_zone(user))
        for user in set(users)
    ]))


@timezone_bot.command(name='time')
async def get_time(ctx, users: commands.Greedy[discord.Member]):
    if len(users) == 0:
        users = [ctx.author]

    await ctx.send('\n'.join([
        '%s: **%s**' % (user.nick or user.name,
                        await get_zone_time(await query_zone(user)))
        for user in set(users)
    ]))


@timezone_bot.command(name='tzlist', help='Get a list of available timezones')
async def get_tzlist(ctx, country=None):
    if country != None and len(country) == 2:
        await ctx.send(
            f'Available timezones for {pytz.country_names[country.upper()]} are:\n{", ".join(pytz.country_timezones[country.upper()])}')
    else:
        await ctx.send(
            'Please specify a two letter country code. [List available here](https://gist.github.com/pamelafox/986163)')


if __name__ == '__main__':
    timezone_bot.run(os.getenv("timezone_token"))
