import logging
from sqlalchemy.orm import sessionmaker
import os
import pandas as pd

import models
from models import Action, User, rank_categories
import discord
from discord.ext import commands
from dotenv import load_dotenv
import utilities
import redis
import numpy as np
from sqlalchemy import update

load_dotenv("dev.env")
logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

guildID = int(os.getenv("guildID"))


class Study(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.guild = None
        self.role_objs = None
        self.role_name_to_obj = None
        self.sqlalchemy_session = None
        self.redis_client = utilities.get_redis_client()

    async def get_num_rows(self, table):
        count_row_query = f"""
            SELECT COUNT(*)
            FROM {table}
        """
        num_rows = await self.bot.sql.query(count_row_query)
        return list(num_rows[0].values())[0]

    async def get_user_id(self, user):
        select_User_id = f"""
            SELECT id from user WHERE discord_user_id = {user.id}
        """
        User_id = await self.bot.sql.query(select_User_id)

        if not User_id:
            await self.on_member_join(user)
            User_id = await self.bot.sql.query(select_User_id)

        return User_id[0]["id"]

    async def get_discord_name(self, discord_user_id):
        if os.getenv("mode") == "test":
            for special_id in ["tester_human_discord_user_id", "tester_bot_token_discord_user_id"]:
                if discord_user_id == os.getenv(special_id):
                    return special_id

            return utilities.generate_username()[0]

        user = await self.bot.get_user(int(discord_user_id))
        return user.name

    async def get_info_from_leaderboard(self, sorted_set_name, start=0, end=-1):
        if start < 0:
            start = 0

        id_li = [int(i) for i in self.redis_client.zrevrange(sorted_set_name, start, end)]
        id_with_score = []

        for neighbor_id in id_li:
            res = dict()
            res["discord_user_id"] = \
                self.sqlalchemy_session.query(User.discord_user_id).filter(User.id == neighbor_id).scalar()
            res["rank"] = 1 + self.redis_client.zrevrank(sorted_set_name, neighbor_id)
            res["study_time"] = self.redis_client.zscore(sorted_set_name, neighbor_id)
            id_with_score.append(res)

        return id_with_score

    async def get_neighbor_stats(self, user_id):
        sorted_set_name = rank_categories["monthly"]
        rank = self.redis_client.zrevrank(sorted_set_name, user_id)

        if rank is None:
            self.redis_client.zadd(sorted_set_name, {user_id: 0})
            rank = self.redis_client.zrevrank(sorted_set_name, user_id)

        id_with_score = await self.get_info_from_leaderboard(sorted_set_name, rank - 5, rank + 5)

        return id_with_score

    @commands.Cog.listener()
    async def on_message(self, message):
        if os.getenv("mode") == "test" and message.author.bot:
            ctx = await self.bot.get_context(message)
            await self.bot.invoke(ctx)

    async def fetch(self):
        if not self.guild:
            self.guild = self.bot.get_guild(guildID)
        self.role_name_to_obj = {role.name: role for role in self.guild.roles}

    @commands.Cog.listener()
    async def on_ready(self):
        if self.bot.pool is None:
            await self.bot.sql.init()

        engine = utilities.get_engine()
        Session = sessionmaker(bind=engine)
        self.sqlalchemy_session = Session()

        await self.fetch()
        print('We have logged in as {0.user}'.format(self.bot))
        # game = discord.Game(f"{self.bot.month} statistics")
        # await self.bot.change_presence(status=discord.Status.online, activity=game)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        user_id = await self.get_user_id(member)

        if before.channel == after.channel:
            if before.self_video != after.self_video:
                category = ("start" if after.self_video else "end") + " video"
                video_change = Action(user_id=user_id, category=category, detail=after.channel.id,
                                      creation_time=utilities.get_time())
                self.sqlalchemy_session.add(video_change)

            if before.self_stream != after.self_stream:
                category = ("start" if after.self_stream else "end") + " stream"
                stream_change = Action(user_id=user_id, category=category, detail=after.channel.id,
                                       creation_time=utilities.get_time())
                self.sqlalchemy_session.add(stream_change)

            if before.self_mute != after.self_mute:
                category = ("start" if not after.self_mute else "end") + " voice"
                stream_change = Action(user_id=user_id, category=category, detail=after.channel.id,
                                       creation_time=utilities.get_time())
                self.sqlalchemy_session.add(stream_change)

            self.sqlalchemy_session.commit()
        else:
            for action_name, channel in [("exit channel", before.channel), ("enter channel", after.channel)]:
                if channel:
                    insert_action = f"""
                        INSERT INTO action (user_id, category, detail, creation_time)
                        VALUES ({user_id}, '{action_name}', '{channel.id}', '{utilities.get_time()}');
                    """
                    print(insert_action)
                    response = await self.bot.sql.query(insert_action)
                    if response:
                        print(response)

            entered_time = self.sqlalchemy_session.query(Action.creation_time).filter(Action.user_id == user_id).filter(
                Action.category.in_(['enter channel', 'exit channel'])).order_by(Action.creation_time.desc()).limit(
                1).scalar()

            for sorted_set_name in rank_categories.values():
                self.redis_client.zincrby(sorted_set_name,
                                          utilities.timedelta_to_hours(utilities.get_time() - entered_time), user_id)

            if self.redis_client.zscore(rank_categories["daily"], user_id) > utilities.config["business"][
                "min_streak_time"]:
                streak_name = "has_streak_today_" + str(user_id)
                if not self.redis_client.exists(streak_name):
                    await self.add_streak(user_id)
                self.redis_client.set(streak_name, 1)
                self.redis_client.expireat(streak_name, utilities.get_tomorrow_start())

    @commands.Cog.listener()
    async def on_member_join(self, member):
        insert_new_member = f"""
            INSERT INTO user (discord_user_id)
            VALUES ({member.id});
        """
        print(insert_new_member)
        response = await self.bot.sql.query(insert_new_member)
        if response:
            print(response)

    @commands.command(aliases=["rank"])
    # @profile
    async def p(self, ctx, user: discord.Member = None):
        # if the user has not specified someone else
        if not user:
            user = ctx.author

        name = user.name + "#" + user.discriminator
        user_id = await self.get_user_id(user)
        hours_cur_month = self.redis_client.zscore(rank_categories["monthly"], user_id)
        role, next_role, time_to_next_role = utilities.get_role_status(self.role_name_to_obj, hours_cur_month)

        text = f"""
        **User:** ``{name}``\n
        __Study role__ ({utilities.get_time().strftime("%B")})
        **Current study role:** {role.mention if role else "No Role"}
        **Next study role:** {next_role.mention if next_role else "``👑 Highest rank reached``"}
        **Role rank:** ``{'👑 ' if role and utilities.role_names.index(role.name) + 1 == {len(utilities.role_settings)} else ''}{utilities.role_names.index(role.name) + 1 if role else '0'}/{len(utilities.role_settings)}``
        """

        if time_to_next_role:
            text += f"**Role promotion in:** ``{(str(time_to_next_role) + 'h')}``"

        emb = discord.Embed(title=utilities.config["embed_titles"]["p"], description=text)
        await ctx.send(embed=emb)

    @commands.command(aliases=['top'])
    async def lb(self, ctx, *, page: int = None, user: discord.Member = None):
        if not page:
            # if the user has not specified someone else
            if not user:
                user = ctx.author

            user_id = await self.get_user_id(user)
            leaderboard = await self.get_neighbor_stats(user_id)
        else:
            if page < 1:
                await ctx.send("You can't look page 0 or a minus number.")
                return

            end = page * 10
            start = end - 10
            leaderboard = await self.get_info_from_leaderboard(rank_categories["monthly"], start, end)

        lb = ''

        for person in leaderboard:
            name = (await self.get_discord_name(person["discord_user_id"]))[:40]
            lb += f'`{(person["rank"] or 0):>5}.` {person["study_time"]:<06} h {name}\n'
        lb_embed = discord.Embed(title=f'{utilities.config["embed_titles"]["lb"]} ({utilities.get_month()})',
                                 description=lb)

        lb_embed.set_footer(text=f"Type !lb 3 (some number) to see placements from 31 to 40")
        await ctx.send(embed=lb_embed)

    @lb.error
    async def lb_error(self, ctx, error):
        if isinstance(error, commands.errors.BadArgument):
            await ctx.send("You provided a wrong argument, more likely you provide an invalid number for the page.")
        else:
            await ctx.send("Unknown error, please contact owner.")
            print(error)

    @commands.command()
    async def me(self, ctx, user: discord.Member = None):
        if not user:
            user = ctx.author

        name = user.name + "#" + user.discriminator
        user_id = await self.get_user_id(user)

        stats = dict()

        for sorted_set_name in rank_categories.values():
            stats[sorted_set_name] = {
                "rank": self.redis_client.zrevrank(sorted_set_name, user_id),
                "study_time": self.redis_client.zscore(sorted_set_name, user_id)
            }

        # TODO Get all time data somehow
        # overall_row = await get_overall_row(name)
        # place_total = ("#" + overall_row[0] if overall_row[0] else "No data")

        average_per_day = utilities.round_num(
            stats[rank_categories["monthly"]]["study_time"] / utilities.get_num_days_this_month())

        # streaks = await get_streaks(name)
        # currentStreak = (str(streaks[1]) if streaks else "0")
        # longestStreak = (str(streaks[2]) if streaks else "0")
        # currentStreak += " day" + ("s" if int(currentStreak) != 1 else "")
        # longestStreak += " day" + ("s" if int(longestStreak) != 1 else "")

        # TODO adjust the space
        emb = discord.Embed(
            title=utilities.config["embed_titles"]["me"],
            description=f"""
            ```css\n```\n```
            glsl\nTimeframe   Hours    Place\n\n
            Past day:   {stats[rank_categories["daily"]]["study_time"]}h #{stats[rank_categories["daily"]]["rank"]}\n
            Past week:  {stats[rank_categories["weekly"]]["study_time"]}h #{stats[rank_categories["weekly"]]["rank"]}\n
            Monthly:    {stats[rank_categories["monthly"]]["study_time"]}h #{stats[rank_categories["monthly"]]["rank"]}\n
            All-time:   {0}{0}\n\n
            Average/day ({utilities.get_month()}): {average_per_day} h\n\n
            Current study streak: {0}\n
            Longest study streak: {0}
            ```
            """)
        foot = name

        emb.set_footer(text=foot, icon_url=user.avatar_url)
        await ctx.send(embed=emb)

    async def add_streak(self, user_id):
        user = self.sqlalchemy_session.query(User).filter(User.id == user_id).all()[0]
        user.current_streak += 1
        if user.longest_streak == user.current_streak:
            user.longest_streak += 1
        self.sqlalchemy_session.commit()


def setup(bot):
    bot.add_cog(Study(bot))

    # async def botSpam(ctx):
    #     if ctx.channel.id in [666352633342197760, 695434541233602621, 715581625425068053, 699007476686651613,
    #                           674590052390535168, 738091719073202327]:
    #         return True
    #     else:
    #         m = await ctx.send(
    #             f"{ctx.author.mention} Please use that command in <#666352633342197760> or <#695434541233602621>.")
    #         await asyncio.sleep(10)
    #         await ctx.message.delete()
    #         await m.delete()
    #         return False
    #
    # bot.add_check(botSpam)
