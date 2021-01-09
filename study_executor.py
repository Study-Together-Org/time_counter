import json
import logging
from sqlalchemy.orm import sessionmaker
import os
import pandas as pd

import models
from models import Action, User, rank_categories
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import utilities
import redis
import numpy as np
from sqlalchemy import update

load_dotenv("dev.env")
monitored_categories = utilities.config["monitored_categories"].values()


def check_categories(channel):
    if channel and channel.category_id in monitored_categories:
        return True

    return False


# async def check_categories(ctx):
#     if ctx.channel.category_id in monitored_categories:
#         return True
#
#     return False


class Study(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.guild = None
        self.role_objs = None
        self.role_name_to_obj = None
        self.supporter_role = None
        self.sqlalchemy_session = None

        self.time_counter_logger = utilities.get_logger("study_executor_time_counter", "discord.log")
        self.heartbeat_logger = utilities.get_logger("study_executor_heartbeat", "heartbeat.log")
        self.redis_client = utilities.get_redis_client()
        self.make_heartbeat.start()

    async def get_num_rows(self, table):
        count_row_query = f"""
            SELECT COUNT(*)
            FROM {table}
        """
        num_rows = await self.bot.sql.query(count_row_query)
        return list(num_rows[0].values())[0]

    async def get_discord_name(self, id):
        if os.getenv("mode") == "test":
            for special_id in ["tester_human_discord_user_id", "tester_bot_token_discord_user_id"]:
                if id == os.getenv(special_id):
                    return special_id

            return utilities.generate_username()[0]

        user = await self.bot.get_user(int(id))
        return user.name

    async def get_info_from_leaderboard(self, sorted_set_name, start=0, end=-1):
        if start < 0:
            start = 0

        id_li = [int(i) for i in self.redis_client.zrevrange(sorted_set_name, start, end)]
        id_with_score = []

        for neighbor_id in id_li:
            res = dict()
            res["discord_user_id"] = neighbor_id
            res["rank"] = await self.get_redis_rank(sorted_set_name, neighbor_id)
            res["study_time"] = await self.get_redis_score(sorted_set_name, neighbor_id)
            id_with_score.append(res)

        return id_with_score

    async def get_redis_rank(self, sorted_set_name, user_id):
        rank = self.redis_client.zrevrank(sorted_set_name, user_id)

        if rank is None:
            self.redis_client.zadd(sorted_set_name, {user_id: 0})
            rank = self.redis_client.zrevrank(sorted_set_name, user_id)

        return 1 + rank

    async def get_redis_score(self, sorted_set_name, user_id):
        score = self.redis_client.zscore(sorted_set_name, user_id)

        if score is None:
            self.redis_client.zadd(sorted_set_name, {user_id: 0})
            score = 0

        return score

    async def get_neighbor_stats(self, user_id):
        sorted_set_name = rank_categories["monthly"]
        rank = await self.get_redis_rank(sorted_set_name, user_id)

        id_with_score = await self.get_info_from_leaderboard(sorted_set_name, rank - 5, rank + 5)

        return id_with_score

    @commands.Cog.listener()
    async def on_message(self, message):
        if os.getenv("mode") == "test" and message.author.bot:
            ctx = await self.bot.get_context(message)
            await self.bot.invoke(ctx)

    async def fetch(self):
        if not self.guild:
            self.guild = self.bot.get_guild(utilities.get_guildID())

        self.role_name_to_obj = {role.name: role for role in self.guild.roles}
        self.supporter_role = self.guild.get_role(
            utilities.config["other_roles"][("test_" if os.getenv("mode") == "test" else "") + "supporter"])

    @commands.Cog.listener()
    async def on_ready(self):
        if self.bot.pool is None:
            await self.bot.sql.init()

        engine = utilities.get_engine()
        Session = sessionmaker(bind=engine)
        self.sqlalchemy_session = Session()

        await self.fetch()
        self.time_counter_logger.info(f'{utilities.get_time()} We have logged in as {self.bot.user}')
        # game = discord.Game(f"{self.bot.month} statistics")
        # await self.bot.change_presence(status=discord.Status.online, activity=game)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        await self.on_member_join(member)

        if not (check_categories(before.channel) or check_categories(after.channel)):
            return

        user_id = member.id

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
                    response = await self.bot.sql.query(insert_action)
                    if response:
                        self.time_counter_logger.error(f"{utilities.get_time()} {response}")

            entered_time = self.sqlalchemy_session.query(Action.creation_time).filter(Action.user_id == user_id).filter(
                Action.category.in_(['enter channel', 'exit channel'])).order_by(Action.creation_time.desc()).limit(
                1).scalar()

            if entered_time:
                for sorted_set_name in rank_categories.values():
                    self.redis_client.zincrby(sorted_set_name,
                                              utilities.timedelta_to_hours(utilities.get_time() - entered_time),
                                              user_id)

            if (await self.get_redis_score(rank_categories["daily"], user_id)) > utilities.config["business"][
                "min_streak_time"]:
                streak_name = "has_streak_today_" + str(user_id)
                if not self.redis_client.exists(streak_name):
                    await self.add_streak(user_id)
                self.redis_client.set(streak_name, 1)
                self.redis_client.expireat(streak_name, utilities.get_tomorrow_start())

    @commands.Cog.listener()
    async def on_member_join(self, member):
        user_sql_obj = self.sqlalchemy_session.query(User).filter(User.id == member.id).all()

        if not user_sql_obj:
            insert_new_member = f"""
                INSERT INTO user (id)
                VALUES ({member.id});
            """
            response = await self.bot.sql.query(insert_new_member)
            if response:
                self.time_counter_logger.error(f"{utilities.get_time()} {response}")

    @commands.command(aliases=["rank"])
    # @profile
    async def p(self, ctx, user: discord.Member = None):
        # if the user has not specified someone else
        if not user:
            user = ctx.author

        name = user.name + "#" + user.discriminator
        user_id = user.id

        hours_cur_month = await self.get_redis_score(rank_categories["monthly"], user_id)
        if not hours_cur_month:
            hours_cur_month = 0

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

            user_id = user.id
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
            self.time_counter_logger.error(f"{utilities.get_time()} {error}")

    @commands.command()
    async def me(self, ctx, user: discord.Member = None):
        if not user:
            user = ctx.author

        name = user.name + "#" + user.discriminator

        user_sql_obj = self.sqlalchemy_session.query(User).filter(User.id == user.id).all()[0]
        user_id = user_sql_obj.id

        stats = dict()

        for sorted_set_name in list(rank_categories.values()) + ["all_time"]:
            stats[sorted_set_name] = {
                "rank": await self.get_redis_rank(sorted_set_name, user_id),
                "study_time": await self.get_redis_score(sorted_set_name, user_id)
            }

        average_per_day = utilities.round_num(
            stats[rank_categories["monthly"]]["study_time"] / utilities.get_num_days_this_month())

        currentStreak = user_sql_obj.current_streak
        longestStreak = user_sql_obj.longest_streak
        currentStreak = str(currentStreak) + " day" + ("s" if currentStreak != 1 else "")
        longestStreak = str(longestStreak) + " day" + ("s" if longestStreak != 1 else "")

        content = f"""
```glsl
Timeframe      Hours   Place\n
Past day:   {stats[rank_categories["daily"]]["study_time"]:>7}h   #{stats[rank_categories["daily"]]["rank"]}
Past week:  {stats[rank_categories["weekly"]]["study_time"]:>7}h   #{stats[rank_categories["weekly"]]["rank"]}
Monthly:    {stats[rank_categories["monthly"]]["study_time"]:>7}h   #{stats[rank_categories["monthly"]]["rank"]}
All-time:   {stats[rank_categories["all_time"]]["study_time"]:>7}h   #{stats[rank_categories["all_time"]]["rank"]}
Average/day ({utilities.get_month()}): {average_per_day} h\n
Current study streak: {currentStreak}
Longest study streak: {longestStreak}
```
        """

        emb = discord.Embed(
            title=utilities.config["embed_titles"]["me"],
            description=content)
        foot = name

        if self.supporter_role in user.roles:
            foot = "⭐ " + foot

        emb.set_footer(text=foot, icon_url=user.avatar_url)
        await ctx.send(embed=emb)

    async def add_streak(self, user_id):
        user = self.sqlalchemy_session.query(User).filter(User.id == user_id).all()[0]
        user.current_streak += 1
        if user.longest_streak == user.current_streak:
            user.longest_streak += 1
        self.sqlalchemy_session.commit()

    @tasks.loop(seconds=int(os.getenv("heartbeat_interval_sec")))
    async def make_heartbeat(self):
        self.heartbeat_logger.info(f"{utilities.get_time()} alive")


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
    # bot.add_check(check_categories)
