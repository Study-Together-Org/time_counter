import asyncio
import os
from datetime import timedelta

import discord
from discord import Intents
from discord.ext import commands, tasks
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker

import utilities
from models import Action, User

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


class Study(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.guild = None
        self.role_objs = None
        self.role_name_to_obj = None
        self.supporter_role = None

        # TODO fix when files not existent
        self.time_counter_logger = utilities.get_logger("study_executor_time_counter", "discord.log")
        self.heartbeat_logger = utilities.get_logger("study_executor_heartbeat", "heartbeat.log")
        self.redis_client = utilities.get_redis_client()
        engine = utilities.get_engine()
        Session = sessionmaker(bind=engine)
        self.sqlalchemy_session = Session()
        self.timezone_session = utilities.get_timezone_session()
        self.make_heartbeat.start()
        self.birthtime = utilities.get_time()

    async def fetch(self):
        """
        Get discord server objects and info from its api
        Since it is only available after connecting, the bot will catch some initial commands but produce errors util this function is finished, which should be quick
        """
        if not self.guild:
            self.guild = self.bot.get_guild(utilities.get_guildID())
        self.role_name_to_obj = utilities.config[("test_" if os.getenv("mode") == "test" else "") + "study_roles"]
        # supporter_role is a role for people who have denoted money
        self.supporter_role = self.guild.get_role(
            utilities.config["other_roles"][("test_" if os.getenv("mode") == "test" else "") + "supporter"])

    async def get_discord_name(self, user_id):
        # In test mode, we might have fake data with fake ids. It is necessary to generate fake user info as well.
        if os.getenv("mode") == "test":
            for special_id in ["tester_human_discord_user_id", "tester_bot_token_discord_user_id"]:
                if user_id == os.getenv(special_id):
                    return special_id

            return utilities.generate_username()[0]

        # Handle deleted users
        user = self.bot.get_user(int(user_id)) or await self.bot.fetch_user(int(user_id))
        return f"{user.name} #{user.discriminator}" if user else "(account deleted)"

    def handle_in_session(self, user_id, reset):
        """
        When a user issues commands, we want to show up-to-date info even if there is no "voice_state_update"
        """
        # after data recovery we should have a sensible start channel record
        last_record = self.get_last_record(user_id, ["start channel"])
        cur_time = utilities.get_time()
        last_record_time = last_record.creation_time if last_record else cur_time

        rank_categories = utilities.get_rank_categories(string=False)
        rank_categories_val = list(rank_categories.values())
        string_rank_categories = list(utilities.get_rank_categories(string=True).values())
        in_session_names = ["in_session_" + str(in_session) for in_session in string_rank_categories[0]]
        category_key_names = string_rank_categories[0] + string_rank_categories[1:]
        in_session_incrs = []
        std_incr = None

        for in_session, in_session_name in zip(rank_categories_val[0], in_session_names):
            past_in_session_time = self.redis_client.hget(in_session_name, user_id)
            past_in_session_time = float(past_in_session_time) if past_in_session_time else 0
            base_time = max(last_record_time, in_session)
            incr = utilities.timedelta_to_hours(cur_time - base_time) - past_in_session_time
            # Max necessary since an enter channel (or other voice status change) update/sync might be called earlier than the exit one
            incr = max(incr, 0)
            in_session_incrs.append(incr)
            new_val = 0 if reset else incr + past_in_session_time

            if in_session_name[-8:] == str(utilities.config["business"]["update_time"]) + ":00:00":
                # standard incr is what gets used for monthly and weekly. In other words, official incr is one of the sets of stats
                std_incr = utilities.timedelta_to_hours(cur_time - last_record_time) - past_in_session_time
                new_val = 0 if reset else std_incr + past_in_session_time

            self.redis_client.hset(in_session_name, user_id, new_val)

        utilities.increment_studytime(category_key_names, self.redis_client, user_id,
                                      in_session_incrs=in_session_incrs, std_incr=std_incr)

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
        rank -= 1  # Use 0 index
        id_with_score = await self.get_info_from_leaderboard(sorted_set_name, rank - 5, rank + 5)

        return id_with_score

    def get_last_record(self, user_id, categories):
        last_record = self.sqlalchemy_session.query(Action) \
            .filter(Action.user_id == user_id) \
            .filter(Action.category.in_(categories)) \
            .order_by(Action.creation_time.desc()).limit(1).first()

        return last_record

    def sync_db(self, user_id, channel, category_type, category_offset):
        cur_time = utilities.get_time()
        categories = [i + " " + category_type for i in ["end", "start"]]
        cur_category = categories[category_offset]
        last_record = self.get_last_record(user_id, categories)

        # Heuristic data recovery if users have voice_state_update when the bot is down
        # See all possible scenarios in test_bot.py
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

        # Users might jump to non-monitored channels
        if check_categories(channel):
            record = Action(user_id=user_id, category=cur_category, detail=channel.id,
                            creation_time=cur_time)
            self.sqlalchemy_session.add(record)

        utilities.commit_or_rollback(self.sqlalchemy_session)

        return last_record.creation_time if last_record else cur_time

    async def add_streak(self, user_id, reset=False):
        user = self.sqlalchemy_session.query(User).filter(User.id == user_id).first()
        if reset:
            user.current_streak = 0
        else:
            user.current_streak += 1

        if user.longest_streak < user.current_streak:
            user.longest_streak = user.current_streak
        utilities.commit_or_rollback(self.sqlalchemy_session)

    async def update_streak(self, user_id):
        today = utilities.get_day_start()
        cur_studytime = await utilities.get_redis_score(self.redis_client, "daily_" + str(today), user_id)
        threshold = utilities.config["business"]["min_streak_time"]

        # A user must study for some minimal time to be considered having studied in a time interval
        if cur_studytime >= threshold:
            # We use a auto-expiring key to implement a fluid streak system - as long as user has studied in the past 24 hours, today the user will have streak
            # Note this grants users a grace period of 1 day
            streak_name = "has_streak_today_" + str(user_id)

            if not self.redis_client.exists(streak_name):
                yesterday = today - timedelta(days=1)
                yesterday_str = "daily_" + str(yesterday)

                # TODO: fix - will have to be 2 or find some way to do this if Redis has no logs
                # Make sure there has been a day since the start of the bot in case there is no logs in Redis (database gets reset)
                if yesterday - self.birthtime < timedelta(days=1):
                    reset = False
                else:
                    reset = (await utilities.get_redis_score(self.redis_client, yesterday_str, user_id)) < threshold

                await self.add_streak(user_id, reset)

            self.redis_client.set(streak_name, 1)
            self.redis_client.expireat(streak_name, utilities.get_tomorrow_start())

    async def update_stats(self, ctx, user):
        # Only update stats if a user is in a monitored channel when issuing the command
        if not user.bot and (not user.voice or user.voice.channel.category.id not in monitored_categories):
            return

        user_id = user.id
        last_record = self.get_last_record(user_id, ["start channel", "end channel"])

        if last_record and last_record.category == "start channel":
            self.handle_in_session(user_id, reset=False)
            await self.update_streak(user_id)

    @tasks.loop(seconds=int(os.getenv("heartbeat_interval_sec")))
    async def make_heartbeat(self):
        self.heartbeat_logger.info(f"{utilities.get_time()} alive")

    @commands.Cog.listener()
    async def on_message(self, message):
        """
        This is just a workaround for the distest library to work (using bots to automatically test other bots; see test_bots.py)
        """
        if os.getenv("mode") == "test" and message.author.bot:
            ctx = await self.bot.get_context(message)
            await self.bot.invoke(ctx)

    @commands.Cog.listener()
    async def on_ready(self):
        await self.fetch()
        self.time_counter_logger.info(f'{utilities.get_time()} Ready: logged in as {self.bot.user}')

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        await self.on_member_join(member)

        if not (check_categories(before.channel) or check_categories(after.channel)):
            return

        user_id = member.id

        if before.self_video != after.self_video:
            self.sync_db(user_id, after.channel, "video", bool(after.self_video))

        if before.self_stream != after.self_stream:
            self.sync_db(user_id, after.channel, "stream", bool(after.self_stream))

        if before.self_mute != after.self_mute:
            self.sync_db(user_id, after.channel, "voice", not bool(after.self_mute))

        if before.channel != after.channel:
            # If a user leaves a channel by joining another one; the database needs 2 logs
            for category_offset, channel in enumerate([before.channel, after.channel]):
                if channel:
                    self.sync_db(user_id, channel, "channel", category_offset)

            if before.channel:
                self.handle_in_session(user_id, reset=True)

            # Only both with streak update on channel change
            # Assumption - a user won't be in a monitored channel with no voice_state_update for more than a day + the grace period (see update_streak)
            await self.update_streak(user_id)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if self.sqlalchemy_session:
            user_sql_obj = self.sqlalchemy_session.query(User).filter(User.id == member.id).all()

            if not user_sql_obj:
                to_insert = User(id=member.id)
                self.sqlalchemy_session.add(to_insert)
                utilities.commit_or_rollback(self.sqlalchemy_session)

    @commands.command(aliases=["P", "rank"])
    async def p(self, ctx, user: discord.Member = None):
        """
        Displays your role placement for this month (use '~help p' to see more)

        examples: '~p'

        To specify a user
        examples: '~p @chooseyourfriend'
        """

        # if the user has not specified someone else

        if not user:
            user = ctx.author

        await self.update_stats(ctx, user)

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
        **Current study role:** {role["mention"] if role else "No Role"}
        **Next study role:** {next_role["mention"] if next_role else "``👑 Highest rank reached``"}
        **Role rank:** ``{'👑 ' if role and utilities.role_names.index(role["name"]) + 1 == {len(utilities.role_settings)} else ''}{utilities.role_names.index(role["name"]) + 1 if role else '0'}/{len(utilities.role_settings)}``
        """

        if time_to_next_role:
            text += f"**Role promotion in:** ``{(str(time_to_next_role) + 'h')}``"

        emb = discord.Embed(title=utilities.config["embed_titles"]["p"], description=text)
        await ctx.send(embed=emb)

    @commands.command(aliases=["LB", "top", "l", "L"])
    async def lb(self, ctx, timepoint=None, page: int = -1, user: discord.Member = None):
        """
        Displays statistics for people with similar studytime (use '~help lb' to see more)
        By default the ranking is monthly, you can specify a start time (in the last 24 hours).
        Currently, the available starting points are hours. If we include half past hours, '~lb 10:14' will become '~lb 10:30'

        To specify a starting time, use any of the following formats "%H:%M", "%H:%m", "%h:%M", "%h:%m", "%H", "%h"
        examples: '~lb 9' or '~lb 9pm'

        To specify a page, specify the page number where each page has 10 members; use '-' as a placeholder to get monthly ranking
        examples: '~lb 9 2' or '~lb - 3'
        
        To specify a time and a user, use '-1' as a placeholder for page
        examples: '~lb 9 -1 @chooseyourfriend'

        To specify a user, also use '-' as a placeholder to get monthly ranking
        examples: '~lb - -1 @chooseyourfriend'

        Note the weekly time resets on Monday GMT+0 5pm and the monthly time 1st day of the month 5pm
        """
        # TODO implement all-time
        text = ""

        # if the user has not specified someone else
        if not user:
            user = ctx.author

        await self.update_stats(ctx, user)

        if timepoint and timepoint != "-":
            timepoint, display_timezone, display_timepoint = await utilities.get_user_timeinfo(ctx, user, timepoint)
            text = f"(From {display_timezone} {display_timepoint})\n"
        # No timepoint or using placeholder
        else:
            timepoint = utilities.get_rank_categories()["monthly"]

        # No timepoint or using placeholder
        if not page or page == -1:
            user_id = user.id
            leaderboard = await self.get_neighbor_stats(timepoint, user_id)
        else:
            if page < 1:
                await ctx.send("Invalid page number.")
                return

            end = page * 10
            start = end - 10
            leaderboard = await self.get_info_from_leaderboard(timepoint, start, end)

        num_dec = int(os.getenv(("test_" if os.getenv("mode") == "test" else "") + "display_num_decimal"))
        width = 5 + num_dec

        for person in leaderboard:
            name = (await self.get_discord_name(person["discord_user_id"]))[:40]
            style = "**" if user and person["discord_user_id"] == user.id else ""
            text += f'`{(person["rank"] or 0):>5}.` {style}{person["study_time"]:{width}.{num_dec}f} h {name}{style}\n'

        lb_embed = discord.Embed(title=f'{utilities.config["embed_titles"]["lb"]} ({utilities.get_month()})',
                                 description=text)

        lb_embed.set_footer(text=f"Type ~help lb to see how to go to other pages")
        await ctx.send(embed=lb_embed)

    # @lb.error
    # async def lb_error(self, ctx, error):
    #     if isinstance(error, commands.errors.BadArgument):
    #         await ctx.send("You provided a wrong argument, more likely you provide an invalid number for the page.")

    @commands.command(aliases=["ME", "m", "M"])
    async def me(self, ctx, timepoint=None, user: discord.Member = None):
        """
        Displays statistics for your studytime (use '~help me' to see more)
        By default the daily time is last 24 hours, but you can specify a start time (in the last 24 hours)
        Currently, the available starting points are hours. If we include half past hours, '~me 10:14' will become '~me 10:30'

        To specify a starting time, use any of the following formats "%H:%M", "%H:%m", "%h:%M", "%h:%m", "%H", "%h"
        examples: '~me 9' or '~me 9pm'

        To specify a user, use
        examples: '~me 9 @chooseyourfriend' or '~me - @chooseyourfriend'
        
        Note the weekly time resets on Monday GMT+0 5pm and the monthly time 1st day of the month 5pm
        """

        """
        # Regarding timezone
        # user input on command, input on DB: use user time to get UTC time & display user time
        # user input on command, not input on DB: use UTC time - prompt to input timezone
        # no user input on command, input on DB: past 24 hours - display user time
        # no user input on command, no input on DB: past 24 hours - prompt to input timezone
        """
        if not user:
            user = ctx.author

        await self.update_stats(ctx, user)
        timepoint, display_timezone, display_timepoint = await utilities.get_user_timeinfo(ctx, user, timepoint)
        rank_categories = utilities.get_rank_categories()
        name = user.name + "#" + user.discriminator
        user_sql_obj = self.sqlalchemy_session.query(User).filter(User.id == user.id).first()
        stats = await utilities.get_user_stats(self.redis_client, user.id, timepoint=timepoint)
        average_per_day = utilities.round_num(
            stats[rank_categories["monthly"]]["study_time"] / utilities.get_num_days_this_month())

        currentStreak = user_sql_obj.current_streak if user_sql_obj else 0
        longestStreak = user_sql_obj.longest_streak if user_sql_obj else 0
        currentStreak = str(currentStreak) + " day" + ("s" if currentStreak != 1 else "")
        longestStreak = str(longestStreak) + " day" + ("s" if longestStreak != 1 else "")

        num_dec = int(os.getenv(("test_" if os.getenv("mode") == "test" else "") + "display_num_decimal"))
        width = 5 + num_dec

        text = f"""
```css
{utilities.config["embed_titles"]["me"]}```
```glsl
Timeframe   {" " * (num_dec - 1)}Hours   Place

Daily:    {stats[timepoint]["study_time"]:{width}.{num_dec}f}h   #{stats[str(timepoint)]["rank"]}
Weekly:   {stats[rank_categories["weekly"]]["study_time"]:{width}.{num_dec}f}h   #{stats[rank_categories["weekly"]]["rank"]}
Monthly:  {stats[rank_categories["monthly"]]["study_time"]:{width}.{num_dec}f}h   #{stats[rank_categories["monthly"]]["rank"]}
All-time: {stats[rank_categories["all_time"]]["study_time"]:{width}.{num_dec}f}h   #{stats[rank_categories["all_time"]]["rank"]}

Average/day ({utilities.get_month()}): {average_per_day} h

Current study streak: {currentStreak}
Longest study streak: {longestStreak}
```
        """

        emb = discord.Embed(
            description=text)
        foot = name

        # Add Fancy decoration for supporter_role
        if self.supporter_role in user.roles:
            foot = "⭐ " + foot

        emb.set_footer(text=foot, icon_url=user.avatar_url)

        await ctx.send(f"**Daily starts tracking at {display_timezone} {display_timepoint}**")
        await ctx.send(embed=emb)

    @commands.has_any_role(utilities.get_role_id("staff"), utilities.get_role_id("dev"))
    @commands.command(aliases=["CHANGE", "c", "C"])
    async def change(self, ctx, dataset_name, val: float, user: discord.Member = None):
        """
        Changes users' hours (use '~help change' to see more)
        Only streak data and zset data types are supported ("longest_streak", "current_streak", "all_time" and "monthly_*")
        
        example: '-c current_streak 21 @studydev' changes the current_streak data to be 21 and update the longest_streak if sensible
        example: '-c longest_streak 210 @studydev' changes the longest_streak data to be 210

        examples: '-c monthly_February 200.5 @studydev' changes the February monthly data to be 200 hours
        examples: '-c all_time 400.21 @studydev' changes the all_time data to be 400.21 hours

        Suggestion: ALWAYS test any change commands on @studydev first.
        """
        user_id = user.id

        if dataset_name in ["longest_streak", "current_streak"]:
            val = round(val)
            user_sql_obj = self.sqlalchemy_session.query(User).filter(User.id == user_id).first()

            if dataset_name == "longest_streak":
                user_sql_obj.longest_streak = val
            elif dataset_name == "current_streak":
                user_sql_obj.current_streak = val
                user_sql_obj.longest_streak = max(val, user_sql_obj.longest_streak)

            utilities.commit_or_rollback(self.sqlalchemy_session)

        elif self.redis_client.type(dataset_name) == "zset":
            self.redis_client.zrem(dataset_name, user_id)
            self.redis_client.zadd(dataset_name, {user_id: val})

        await ctx.send(f"user_id: {user_id}, dataset_name: {dataset_name}\nval: {val}")

    @commands.Cog.listener()
    async def on_command_error(self, ctx, exception):
        print(utilities.get_time(), exception)
        await ctx.send(f"{exception}\nTry ~help?")

    @commands.Cog.listener()
    async def on_guild_unavailable(self, guild):
        self.time_counter_logger.info(f'{utilities.get_time()} guild unavailable')

    @commands.Cog.listener()
    async def on_guild_available(self, guild):
        self.time_counter_logger.info(f'{utilities.get_time()} guild available')


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
    prefix = os.getenv("prefix")
    prefix_2 = os.getenv("prefix_2")
    prefixes = [prefix, prefix_2] if prefix_2 else prefix

    client = commands.Bot(command_prefix=prefixes, intents=Intents.all(),
                          description="Your study statistics and rankings")
    client.load_extension('time_counter')
    client.run(os.getenv('bot_token'))
