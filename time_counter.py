import asyncio
import os
import discord
from discord import Intents
from datetime import datetime, timedelta, timezone
from discord.ext import commands, tasks
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker

import utilities
from models import Action, User

load_dotenv("dev.env")
monitored_key_name = ("test_" if os.getenv("mode") == "test" else "") + "monitored_categories"
monitored_categories = utilities.config[monitored_key_name].values()


def check_categories(channel):
    if channel and channel.category_id in monitored_categories:
        return True

    return False


class Study(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.guild = None
        self.role_objs = None
        self.role_name_to_obj = None
        self.supporter_role = None
        self.sqlalchemy_session = None

        # TODO fix when files not existent
        self.time_counter_logger = utilities.get_logger("study_executor_time_counter", "discord.log")
        self.heartbeat_logger = utilities.get_logger("study_executor_heartbeat", "heartbeat.log")
        self.redis_client = utilities.get_redis_client()
        self.make_heartbeat.start()

    async def fetch(self):
        if not self.guild:
            self.guild = self.bot.get_guild(utilities.get_guildID())

        self.role_name_to_obj = {role.name: role for role in self.guild.roles}
        self.supporter_role = self.guild.get_role(
            utilities.config["other_roles"][("test_" if os.getenv("mode") == "test" else "") + "supporter"])

    async def get_discord_name(self, user_id):
        if os.getenv("mode") == "test":
            for special_id in ["tester_human_discord_user_id", "tester_bot_token_discord_user_id"]:
                if user_id == os.getenv(special_id):
                    return special_id

            return utilities.generate_username()[0]

        user = self.bot.get_user(int(user_id))
        return f"{user.name} #{user.discriminator}"

    async def get_info_from_leaderboard(self, sorted_set_name, start=0, end=-1):
        if start < 0:
            start = 0

        id_li = [int(i) for i in self.redis_client.zrevrange(sorted_set_name, start, end)]
        id_with_score = []

        for neighbor_id in id_li:
            res = dict()
            res["discord_user_id"] = neighbor_id
            res["rank"] = await utilities.get_redis_rank(self.redis_client, sorted_set_name, neighbor_id)
            res["study_time"] = await utilities.get_redis_score(self.redis_client, sorted_set_name, neighbor_id)
            id_with_score.append(res)

        return id_with_score

    async def get_neighbor_stats(self, sorted_set_name, user_id):
        rank = await utilities.get_redis_rank(self.redis_client, sorted_set_name, user_id)
        id_with_score = await self.get_info_from_leaderboard(sorted_set_name, rank - 5, rank + 5)

        return id_with_score

    def get_last_record(self, user_id, categories):
        last_record = self.sqlalchemy_session.query(Action) \
            .filter(Action.user_id == user_id) \
            .filter(Action.category.in_(categories)) \
            .order_by(Action.creation_time.desc()).limit(1).first()

        return last_record

    def sync_voice_status_change(self, user_id, channel, category_type, category_offset):
        cur_time = utilities.get_time()
        categories = [i + " " + category_type for i in ["end", "start"]]
        cur_category = categories[category_offset]
        last_record = self.get_last_record(user_id, categories)

        # data recovery
        if last_record:
            # For case:
            # last: start id_1
            # cur: end id_2
            if last_record.detail != channel.id and categories.index(last_record.category):
                # Add end for last
                last_category_offset = categories.index(last_record.category)
                cur_time += timedelta(microseconds=1)
                record = Action(user_id=user_id, category=categories[1 - last_category_offset],
                                detail=last_record.detail,
                                creation_time=cur_time)
                self.sqlalchemy_session.add(record)
                if category_offset == 0:
                    # Add start for cur
                    # A bit inelegant when a user with video on switches to another channel
                    cur_time += timedelta(microseconds=1)
                    record = Action(user_id=user_id, category=categories[last_category_offset], detail=channel.id,
                                    creation_time=cur_time)
                    self.sqlalchemy_session.add(record)
            # For case:
            # start(end) id_1
            # start(end) id_1

            # end id_1
            # end id_2
            elif last_record.category == cur_category:
                cur_time += timedelta(microseconds=1)
                record = Action(user_id=user_id, category=categories[1 - category_offset], detail=last_record.detail,
                                creation_time=cur_time)
                self.sqlalchemy_session.add(record)

        cur_time += timedelta(microseconds=1)
        record = Action(user_id=user_id, category=cur_category, detail=channel.id,
                        creation_time=cur_time)
        self.sqlalchemy_session.add(record)
        self.sqlalchemy_session.commit()

        return last_record.creation_time if last_record else cur_time

    async def add_streak(self, user_id):
        user = self.sqlalchemy_session.query(User).filter(User.id == user_id).first()
        user.current_streak += 1
        if user.longest_streak < user.current_streak:
            user.longest_streak += 1
        self.sqlalchemy_session.commit()

    async def update_streak(self, rank_categories, user_id):
        if (await utilities.get_redis_score(self.redis_client, rank_categories["daily"], user_id)) > \
            utilities.config["business"][
                "min_streak_time"]:
            streak_name = "has_streak_today_" + str(user_id)
            if not self.redis_client.exists(streak_name):
                await self.add_streak(user_id)
            self.redis_client.set(streak_name, 1)
            self.redis_client.expireat(streak_name, utilities.get_tomorrow_start())

    def get_in_session_incr(self, past_in_session_time, last_record_time):
        cur_time = utilities.get_time()
        incr = utilities.timedelta_to_hours(cur_time - last_record_time) - past_in_session_time

        if incr < 0:
            self.time_counter_logger.info(f'incr lower than 0 {incr}')

        return incr

    async def update_stats(self, ctx):
        user = ctx.author

        if not (user.voice and user.voice.channel.category.id in monitored_categories):
            return

        user_id = user.id
        last_record = self.get_last_record(user_id, ["start channel", "end channel"])

        if last_record and last_record.category == "start channel":
            past_in_session_time = self.redis_client.hget("in_session", user_id)
            past_in_session_time = float(past_in_session_time) if past_in_session_time else 0
            incr = self.get_in_session_incr(past_in_session_time, last_record.creation_time)
            self.redis_client.hset("in_session", user_id, incr + past_in_session_time)
            category_key_names = utilities.get_rank_categories().values()
            utilities.increment_studytime(category_key_names, self.redis_client, user_id, incr=incr)
            rank_categories = utilities.get_rank_categories()
            await self.update_streak(rank_categories, user_id)

    @tasks.loop(seconds=int(os.getenv("heartbeat_interval_sec")))
    async def make_heartbeat(self):
        self.heartbeat_logger.info(f"{utilities.get_time()} alive")

    @commands.Cog.listener()
    async def on_message(self, message):
        if os.getenv("mode") == "test" and message.author.bot:
            ctx = await self.bot.get_context(message)
            await self.bot.invoke(ctx)

    @commands.Cog.listener()
    async def on_ready(self):
        engine = utilities.get_engine()
        Session = sessionmaker(bind=engine)
        self.sqlalchemy_session = Session()

        await self.fetch()
        self.time_counter_logger.info(f'{utilities.get_time()} Ready: logged in as {self.bot.user}')

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        await self.on_member_join(member)

        if not (check_categories(before.channel) or check_categories(after.channel)):
            return

        user_id = member.id

        if before.self_video != after.self_video:
            self.sync_voice_status_change(user_id, after.channel, "video", bool(after.self_video))

        if before.self_stream != after.self_stream:
            self.sync_voice_status_change(user_id, after.channel, "stream", bool(after.self_stream))

        if before.self_mute != after.self_mute:
            self.sync_voice_status_change(user_id, after.channel, "voice", not bool(after.self_mute))

        rank_categories = utilities.get_rank_categories()
        category_key_names = rank_categories.values()

        if before.channel != after.channel:
            for category_offset, channel in enumerate([before.channel, after.channel]):
                if channel:
                    self.sync_voice_status_change(user_id, channel, "channel", category_offset)
            if before.channel:
                # after data recovery we should have a sensible start channel record
                last_record = self.get_last_record(user_id, ["start channel"])
                past_in_session_time = self.redis_client.hget("in_session", user_id)
                past_in_session_time = float(past_in_session_time) if past_in_session_time else 0
                self.redis_client.hset("in_session", user_id, 0)
                cur_time = utilities.get_time()
                incr = utilities.timedelta_to_hours(cur_time - last_record.creation_time) - past_in_session_time
                utilities.increment_studytime(category_key_names, self.redis_client, user_id, incr=incr)
            await self.update_streak(rank_categories, user_id)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if not self.sqlalchemy_session:
            return

        user_sql_obj = self.sqlalchemy_session.query(User).filter(User.id == member.id).all()

        if not user_sql_obj:
            to_insert = User(id=member.id)
            self.sqlalchemy_session.add(to_insert)
            self.sqlalchemy_session.commit()

    @commands.command(aliases=["rank"])
    @commands.before_invoke(update_stats)
    async def p(self, ctx, user: discord.Member = None):
        # if the user has not specified someone else
        if not user:
            user = ctx.author

        name = f"{user.name} #{user.discriminator}"
        user_id = user.id
        rank_categories = utilities.get_rank_categories()

        hours_cur_month = await utilities.get_redis_score(self.redis_client, rank_categories["monthly"], user_id)
        if not hours_cur_month:
            hours_cur_month = 0

        role, next_role, time_to_next_role = utilities.get_role_status(self.role_name_to_obj, hours_cur_month)
        # TODO update user roles

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
    @commands.before_invoke(update_stats)
    async def lb(self, ctx, *, page: int = None, user: discord.Member = None):
        rank_categories = utilities.get_rank_categories()

        if not page:
            # if the user has not specified someone else
            if not user:
                user = ctx.author

            user_id = user.id
            leaderboard = await self.get_neighbor_stats(rank_categories["monthly"], user_id)
        else:
            if page < 1:
                await ctx.send("You can't look page 0 or a minus number.")
                return

            end = page * 10
            start = end - 10
            leaderboard = await self.get_info_from_leaderboard(rank_categories["monthly"], start, end)

        text = ''

        for person in leaderboard:
            name = (await self.get_discord_name(person["discord_user_id"]))[:40]
            text += f'`{(person["rank"] or 0):>5}.` {person["study_time"]:<06} h {name}\n'
        lb_embed = discord.Embed(title=f'{utilities.config["embed_titles"]["lb"]} ({utilities.get_month()})',
                                 description=text)

        lb_embed.set_footer(text=f"Type !text 3 (some number) to see placements from 31 to 40")
        await ctx.send(embed=lb_embed)

    # @lb.error
    # async def lb_error(self, ctx, error):
    #     if isinstance(error, commands.errors.BadArgument):
    #         await ctx.send("You provided a wrong argument, more likely you provide an invalid number for the page.")

    @commands.command()
    @commands.before_invoke(update_stats)
    async def me(self, ctx, user: discord.Member = None):
        if not user:
            user = ctx.author
        rank_categories = utilities.get_rank_categories()
        name = user.name + "#" + user.discriminator
        user_sql_obj = self.sqlalchemy_session.query(User).filter(User.id == user.id).first()
        stats = await utilities.get_user_stats(self.redis_client, user.id)
        average_per_day = utilities.round_num(
            stats[rank_categories["monthly"]]["study_time"] / utilities.get_num_days_this_month())

        currentStreak = user_sql_obj.current_streak if user_sql_obj else 0
        longestStreak = user_sql_obj.longest_streak if user_sql_obj else 0
        currentStreak = str(currentStreak) + " day" + ("s" if currentStreak != 1 else "")
        longestStreak = str(longestStreak) + " day" + ("s" if longestStreak != 1 else "")

        num_nums_var_name = ("test_" if os.getenv("mode") == "test" else "") + "display_num_decimal"
        num_nums = int(os.getenv(num_nums_var_name)) + 5
        text = f"""
```glsl
Timeframe         Hours    Place\n
Daily:         {stats[rank_categories["daily"]]["study_time"]:>{num_nums}}h   #{stats[rank_categories["daily"]]["rank"]}
Weekly:        {stats[rank_categories["weekly"]]["study_time"]:>{num_nums}}h   #{stats[rank_categories["weekly"]]["rank"]}
Monthly:       {stats[rank_categories["monthly"]]["study_time"]:>{num_nums}}h   #{stats[rank_categories["monthly"]]["rank"]}
All-time:      {stats[rank_categories["all_time"]]["study_time"]:>{num_nums}}h   #{stats[rank_categories["all_time"]]["rank"]}
Average/day ({utilities.get_month()}): {average_per_day} h\n
Current study streak: {currentStreak}
Longest study streak: {longestStreak}
```
        """

        emb = discord.Embed(
            title=utilities.config["embed_titles"]["me"],
            description=text)
        foot = name

        if self.supporter_role in user.roles:
            foot = "⭐ " + foot

        emb.set_footer(text=foot, icon_url=user.avatar_url)
        await ctx.send(embed=emb)


def setup(bot):
    bot.add_cog(Study(bot))

    async def botSpam(ctx):
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
    client = commands.Bot(command_prefix=os.getenv("prefix"), intents=Intents.all())
    client.load_extension('time_counter')
    client.run(os.getenv('bot_token'))
