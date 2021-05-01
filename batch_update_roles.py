import asyncio
import os
import traceback
import logging
import json

from functools import partial
import discord
from discord import Intents
from discord.ext import commands, tasks
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker

import utilities
from models import Action, User

logging.basicConfig(level=logging.INFO)

load_dotenv("dev.env")
monitored_key_name = ("test_" if os.getenv("mode") == "test" else "") + "monitored_categories"
monitored_categories = utilities.config[monitored_key_name].values()


def check_categories(channel):
    """
    Check to make sure to monitor only selected channels
    """
    if channel and channel.category_id in monitored_categories:
        return True

    return False


def get_traceback(error):
    # get data from exception
    etype = type(error)
    trace = error.__traceback__

    # the verbosity is how large of a traceback to make
    # more specifically, it's the amount of levels up the traceback goes from the exception source
    verbosity = 10

    # 'traceback' is the stdlib module, `import traceback`.
    lines = traceback.format_exception(etype, error, trace, verbosity)
    txt = '\n'.join(lines)

    return txt


async def keep_only_updated(bot, new: list):
    result = []
    for i in new:
        if not (i in bot.update_cache):
            result.append(i)

    bot.update_cache = new

    # with open("update_cache.json", "w") as f:
    #     f.write(json.dumps(new))

    return result


class Study(commands.Cog):
    def __init__(self, bot):
        self.bot = self.client = bot
        self.guild = None
        self.role_objs = None
        self.role_names = None
        self.supporter_role = None

        # TODO fix when files not existent
        self.data_change_logger = utilities.get_logger("study_executor_data_change", "data_change.log")
        self.time_counter_logger = utilities.get_logger("study_executor_time_counter", "discord.log")
        self.redis_client = utilities.get_redis_client()
        engine = utilities.get_engine()
        Session = sessionmaker(bind=engine)
        self.sqlalchemy_session = Session()
        self.timezone_session = utilities.get_timezone_session()
        self.birthtime = utilities.get_time()

    async def fetch(self):
        """
        Get discord server objects and info from its api
        Since it is only available after connecting, the bot will catch some initial commands but produce errors util this function is finished, which should be quick
        """
        if not self.guild:
            self.guild = self.bot.get_guild(utilities.get_guildID())
        self.role_names = utilities.config[("test_" if os.getenv("mode") == "test" else "") + "study_roles"]
        # supporter_role is a role for people who have denoted money
        self.supporter_role = utilities.config["other_roles"][
            ("test_" if os.getenv("mode") == "test" else "") + "supporter"]

    @commands.Cog.listener()
    async def on_command_error(self, ctx, exception):
        pass
        # commented out due to overlapping prefixes with the other bots
        # print(utilities.get_time(), exception)
        # await ctx.send(f"{exception}\nTry ~help?")

    @commands.Cog.listener()
    async def on_ready(self):
        # fetch info
        await self.fetch()

        print("Updating roles...", flush=True)

        # get the list of users with their monthly study hours
        users = self.sqlalchemy_session.query(User).all()
        # sort users by id

        monthly_session_name = utilities.get_rank_categories()["monthly"]
        users_monthly_hours = self.redis_client.zrange(monthly_session_name, 0, -1, withscores=True)

        # print(self.client.get_guild(utilities.get_guildID()).members)

        # create a dict of users with their monthly study hours set to 0
        user_dict = {user.id: 0 for user in users}

        # update each user's hours based on redis
        for user_monthly_hours in users_monthly_hours:
            user_dict[user_monthly_hours[0]] = user_monthly_hours[1]

        # turn the dictionary into a list of [key, value]
        user_list = []
        for key, value in user_dict.items():
            user_list.append([key, value])

        # get only a list of the users that have changed since the last run
        user_list = await keep_only_updated(self.bot, user_list)

        # write the updated roles for debugging
        with open("onlyUpdatedTest.json", "w") as f:
            f.write(json.dumps(user_list))

        # get the roles and reverse them
        roles = list(self.role_names.values())
        roles.reverse()

        # task for processing the user_list and updating each users roles accordingly
        def the_task(self, user_list, roles):
            count = 0
            countAddedRoles = 0
            countRemovedRoles = 0
            toUpdate = {}  # {discord.Member: {"add": [discord.Role], "remove": [discord.Role]} }

            # for each user in the list
            for user in user_list:
                count += 1

                # if the number of entries isn't two, then there is an error
                if len(user) != 2:
                    break

                # get the member with the id
                m = self.client.get_guild(utilities.get_guildID()).get_member(int(user[0]))
                print(count, len(user_list), user[0], m, flush=True)

                # if user doesn't exist, continue
                if not m: continue

                # get the user's hours
                hours = user[1]

                # for each role,
                # remove roles that the user should no longer hold
                # add roles that the user now holds
                for r in roles:
                    min_ = float(r["hours"].split("-")[0])
                    max_ = float(r["hours"].split("-")[1])
                    if min_ <= hours < max_ or (hours >= 350 and r["id"] == 676158518956654612):
                        # print("Adding if doesn't already exist", m.guild.get_role(r["id"]) in m.roles)
                        # update roles
                        if not m.guild.get_role(r["id"]) in m.roles:
                            if m not in toUpdate: toUpdate[m] = {"add": [], "remove": []}
                            toUpdate[m]["add"].append(
                                m.guild.get_role(r["id"]))  # await m.add_roles(m.guild.get_role(r["id"]))
                            countAddedRoles += 1
                    else:
                        # print("Removing role if exists", m.guild.get_role(r["id"]) in m.roles)
                        if m.guild.get_role(r["id"]) in m.roles:
                            if m not in toUpdate: toUpdate[m] = {"add": [], "remove": []}
                            toUpdate[m]["remove"].append(
                                m.guild.get_role(r["id"]))  # await m.remove_roles(m.guild.get_role(r["id"]))
                            countRemovedRoles += 1

            # print(f"Checked {count}/{total} members, {countAddedRoles} roles to add and {countRemovedRoles} roles to remove!")
            return toUpdate

        try:
            # try updating each users roles
            print("Starting processing", flush=True)
            func = partial(the_task, self, user_list, roles)
            toUpdate = await self.client.loop.run_in_executor(None, func)

            count = 0
            numPendingUpdates = len(toUpdate)
            for (k, v) in toUpdate.items():
                if k is not None:
                    print(f"{count} / {numPendingUpdates}. Updating roles of: " + k.name, flush=True)
                    print(v, flush=True)
                    await k.add_roles(*v["add"], reason="New rank")
                    await k.remove_roles(*v["remove"], reason="New rank")
                else:
                    print("Bug member is none")

                count += 1
                # print(f"Added {len(v['add'])} roles and removed {len(v['remove'])} roles.")
            print("FINISHED", len(toUpdate), flush=True)
        except Exception as e:
            print("Error", flush=True)
            print(e, flush=True)


def setup(bot):
    with open("update_cache.json", "r") as f:
        bot.update_cache = json.loads(f.read())

    bot.add_cog(Study(bot))

    async def botSpam(ctx):
        """
        Only respond in certain channels to avoid spamming
        """
        if ctx.channel.id in utilities.config["command_channels"]:
            return True
        else:
            m = await ctx.send(
                f"{ctx.author.mention} Please use that command in <#666352633342197760> or <#695434541233602621>.")
            await asyncio.sleep(10)
            await ctx.message.delete()
            await m.delete()
            return False

    bot.add_check(botSpam)


if __name__ == '__main__':
    # Potentially accept multiple prefixes
    # TODO move these prefixes to config.hjson
    prefix = os.getenv("prefix")
    prefix_2 = os.getenv("prefix_2")
    prefix_3 = os.getenv("prefix_3")
    prefixes = [prefix, prefix_2, prefix_3] if prefix_2 else prefix

    client = commands.Bot(command_prefix=prefixes, intents=Intents.all(),
                          description="Your study statistics and rankings")
    print("Loading extension", flush=True)
    client.load_extension('test_role_update')
    print("Starting bot", flush=True)
    client.run(os.getenv('bot_token'))
