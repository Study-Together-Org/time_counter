import asyncio
import os
import logging

from functools import partial
from discord import Intents
from discord.ext import commands, tasks
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker

import utilities
from models import Action, User

print("WARNING: some configuration values have been placed in slightly different files; light fixes should be needed")
logging.basicConfig(level=logging.INFO)

load_dotenv("../dev.env")


# create discord bot Cog that will
# batch update all user roles on ready
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
        Since it is only available after connecting, the bot will catch some initial commands but produce errors until this function is finished, which should be quick
        """

        # set the guild of interest
        if not self.guild:
            self.guild = self.bot.get_guild(utilities.get_guildID())

        # get the relevant role names from the config file based on whether or not we are in test mode
        self.role_names = utilities.config[("test_" if os.getenv("STUDY_TOGETHER_MODE") == "dev" else "") + "study_roles"]
        # supporter_role is a role for people who have denoted money
        self.supporter_role = utilities.config["other_roles"][
            ("test_" if os.getenv("STUDY_TOGETHER_MODE") == "dev" else "") + "supporter"]


    @commands.Cog.listener()
    async def on_command_error(self, ctx, exception):
        # this bot doesn't respond to commands
        pass


    @commands.Cog.listener()
    async def on_ready(self):
        # called after the bot initializes

        # fetch initial api info
        await self.fetch()

        # start updating the roles
        print("Updating roles...", flush=True)

        # get the list of users from sql
        users = self.sqlalchemy_session.query(User).all()

        # get the users monthly hours from redis
        monthly_session_name = utilities.get_rank_categories()["monthly"]
        users_monthly_hours = self.redis_client.zrange(monthly_session_name, 0, -1, withscores=True)

        # create a dict of users with their monthly study hours set to 0
        user_dict = {user.id: 0 for user in users}

        # update each user's hours based on redis
        for user_monthly_hours in users_monthly_hours:
            user_dict[user_monthly_hours[0]] = user_monthly_hours[1]

        # turn the dictionary into a list of [user_id, hours_studied_this_month]
        user_list = []
        for key, value in user_dict.items():
            user_list.append([key, value])

        # # write the user_list to a file for debugging
        # with open("onlyUpdatedTest.json", "w") as f:
        #     f.write(json.dumps(user_list))

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
                    print("Invalid user tuple in user_list")
                    continue

                # get the member from the discord api by id
                m = self.client.get_guild(utilities.get_guildID()).get_member(int(user[0]))

                # if user doesn't exist (potentially they left the server), continue
                if not m: continue

                # get the user's hours from redis
                hours = user[1]

                # for each role,
                # remove roles that the user should no longer hold
                # add roles that the user now holds
                for r in roles:
                    # min_ and max_ are the bounds for the role of interest
                    min_ = float(r["hours"].split("-")[0])
                    max_ = float(r["hours"].split("-")[1])
                    if min_ <= hours < max_ or (hours >= 350 and r["id"] == 676158518956654612):
                        if not m.guild.get_role(r["id"]) in m.roles:
                            # if user hours are inside the bounds for this role, and the user doesn't already have this role
                            # store that the role should be added to this user in the `toUpdate` object
                            if m not in toUpdate: toUpdate[m] = {"add": [], "remove": []}
                            toUpdate[m]["add"].append(
                                m.guild.get_role(r["id"]))
                            countAddedRoles += 1
                    else:
                        if m.guild.get_role(r["id"]) in m.roles:
                            # if user hours are outside the bounds for this role, and the user has this role
                            # store that the role should be removed from this user in the `toUpdate` object
                            if m not in toUpdate: toUpdate[m] = {"add": [], "remove": []}
                            toUpdate[m]["remove"].append(
                                m.guild.get_role(r["id"]))  # await m.remove_roles(m.guild.get_role(r["id"]))
                            countRemovedRoles += 1

            # return the dict storing role update information
            return toUpdate

        try:
            # try updating each users roles
            print("Starting processing", flush=True)
            func = partial(the_task, self, user_list, roles)
            # get the update dictionary
            toUpdate = await self.client.loop.run_in_executor(None, func)

            count = 0
            numPendingUpdates = len(toUpdate)

            # apply the updates
            # this can take a while because of api rate limiting
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
    prefix = utilities.config["prefixes"]
    prefix_2 = os.getenv("prefix_2")
    prefix_3 = os.getenv("prefix_3")
    prefixes = [prefix, prefix_2, prefix_3] if prefix_2 else prefix

    client = commands.Bot(command_prefix=prefixes, intents=Intents.all(),
                          description="Your study statistics and rankings")
    print("Loading extension", flush=True)
    client.load_extension('test_role_update')
    print("Starting bot", flush=True)
    client.run(os.getenv('bot_token'))
