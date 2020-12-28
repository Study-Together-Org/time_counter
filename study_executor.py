import logging
from sqlalchemy.orm import sessionmaker
import os
import pandas as pd
from models import Action, User
import discord
import hjson
from discord.ext import commands
from dotenv import load_dotenv
import utilities
import numpy as np
from sqlalchemy import update

load_dotenv("dev.env")
logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

with open("roles.json") as f:
    roles = hjson.load(f)

role_name_to_begin_hours = {role_name: float(role_info['hours'].split("-")[0]) for role_name, role_info in
                            roles.items()}
role_names = list(roles.keys())
guildID = int(os.getenv("guildID"))


class Study(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.guild = None
        self.role_objs = None
        self.sqlalchemy_session = None

    def get_role(self, user):
        user_roles = {r for r in user.roles if r.name not in {"ST! Tester", "@everyone"}}
        user_study_roles = list(user_roles.intersection(set(self.role_name_to_obj.values())))
        role = None
        next_role = None

        if user_study_roles:
            role = user_study_roles[0]
            if role.id != self.role_name_to_obj[role_names[-1]].id:
                # If user has not reached the end
                next_role = self.role_name_to_obj[role_names[role_names.index(role.name) + 1]]
        else:
            next_role = self.role_name_to_obj[role_names[0]]

        return role, next_role

    async def get_num_rows(self, table):
        count_row_query = f"""
            SELECT COUNT(*)
            FROM {table}
        """
        num_rows = await self.bot.sql.query(count_row_query)
        return list(num_rows[0].values())[0]

    async def get_User_id(self, user):
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
            return utilities.generate_username()[0]

        user = await self.bot.get_user(int(discord_user_id))
        return user.name

    async def get_user_rank(self, user_id):
        rank = self.sqlalchemy_session.query(User.rank).filter(User.id == user_id).scalar()
        return rank

    async def get_neighbor_stats(self, user_id):
        user_res = self.sqlalchemy_session.query(User).filter(User.id == user_id).all()
        if not user_res:
            return

        user = user_res[0]
        before = self.sqlalchemy_session.query(User).filter(User.study_time > (user.study_time or 0)).order_by(User.study_time.desc())[-5:]
        after = self.sqlalchemy_session.query(User).filter(User.study_time <= (user.study_time or 0)).filter(User.id != user_id).order_by(User.study_time.desc())[:5]
        response = before + [user] + after
        return response

    @commands.Cog.listener()
    async def on_message(self, message):
        # self.p()
        if message.content == '!p' and message.author.bot:
            ctx = await self.bot.get_context(message)
            await self.p(ctx, message.author)

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
        if before.channel == after.channel:
            return

        User_id = await self.get_User_id(member)

        for action_name, channel in [("exit channel", before.channel), ("enter channel", after.channel)]:
            if channel:
                insert_action = f"""
                    INSERT INTO action (User_id, category, detail, creation_time)
                    VALUES ({User_id}, '{action_name}', '{channel.name}', '{utilities.get_time()}');
                """
                print(insert_action)
                response = await self.bot.sql.query(insert_action)
                if response:
                    print(response)

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

    async def get_time_cur_month(self, User_id):
        get_cur_month_data_query = f"""
            SELECT study_time FROM user
            WHERE id = {User_id}
        """
        print(get_cur_month_data_query)
        response = await self.bot.sql.query(get_cur_month_data_query)
        return list(response[0].values())[0]

    @commands.command(aliases=["refresh"])
    # @profile
    async def r(self, ctx=None, user: discord.Member = None):
        query = self.sqlalchemy_session.query(Action.user_id, Action.category, Action.creation_time) \
            .filter(Action.category.in_(['enter channel', 'exit channel'])) \
            .filter(Action.creation_time >= utilities.get_month_start())
        response = pd.read_sql(query.statement, self.sqlalchemy_session.bind)
        agg = response.groupby("user_id", as_index=False).apply(utilities.get_total_time_cur_month)
        agg.columns = [agg.columns[0], "study_time"]
        # TODO: use user' join date to break ties
        agg["rank"] = agg.sort_values(by=["study_time", "user_id"], ascending=False).reset_index().sort_values("index").index + 1
        agg.to_sql('temp_table', self.sqlalchemy_session.bind, if_exists='replace', index=False)

        update_statement = """
            UPDATE user JOIN temp_table ON user.id = temp_table.user_id
            SET user.study_time = temp_table.study_time, user.rank = temp_table.rank
            WHERE user.id = temp_table.user_id
        """

        self.sqlalchemy_session.bind.execute(update_statement)
        print("refreshed")

    @commands.command(aliases=["rank"])
    async def p(self, ctx, user: discord.Member = None):
        # if the user has not specified someone else
        if not user:
            user = ctx.author

        name = user.name + "#" + user.discriminator
        User_id = await self.get_User_id(user)

        hours_cur_month = await self.get_time_cur_month(User_id)

        role, next_role = self.get_role(user)
        next_time = None

        if not hours_cur_month:
            # New member
            next_time = role_name_to_begin_hours[next_role.name] - hours_cur_month
            next_time = utilities.round_num(next_time)

        text = f"""
        **User:** ``{name}``\n
        __Study role__ ({utilities.get_time().strftime("%B")})
        **Current study role:** {role.mention if role else "No Role"}
        **Next study role:** {next_role.mention if next_role else "``👑 Highest rank reached``"}
        **Role promotion in:** ``{(str(next_time) + 'h') if next_time else list(role_name_to_begin_hours.values())[1]}``
        **Role rank:** ``{'👑 ' if role and role_names.index(role.name) + 1 == {len(roles)} else ''}{role_names.index(role.name) + 1 if role else '0'}/{len(roles)}``
        """

        emb = discord.Embed(title=":coffee: Personal rank statistics", description=text)
        await ctx.send(embed=emb)

    @commands.command(aliases=['top'])
    async def lb(self, ctx, *, page: int = 1, user: discord.Member = None):
        if page < 1:
            await ctx.send("You can't look page 0 or a minus number.")
            return

        # if the user has not specified someone else
        if not user:
            user = ctx.author

        user_id = await self.get_User_id(user)

        # data = self.r()
        stop = page * 10
        start = stop - 10
        # if stop > len(data):
        #     stop = len(data)
        # leaderboard = data[start:stop]

        num_users = await self.get_num_rows("user")
        if start > num_users:
            await ctx.send("There are not enough pages")
            return

        leaderboard = await self.get_neighbor_stats(user_id)
        if not leaderboard:
            print("no stats")
            return

        lb = ''

        for person in leaderboard:
            name = (await self.get_discord_name(person.discord_user_id))[:15]
            lb += f'`{person.rank:>5}.` {person.study_time:<06} h {name}\n'
        lb_embed = discord.Embed(title=f'🧗 Study leaderboard ({utilities.get_month()})',
                                 description=lb)
        # lb_embed.set_footer(text=f"Type !lb {page + 1} to see placements {stop + 1}-{stop + 10}")
        await ctx.send(embed=lb_embed)

    @lb.error
    async def lb_error(self, ctx, error):
        if isinstance(error, commands.errors.BadArgument):
            await ctx.send("You provided a wrong argument, more likely you provide an invalid number for the page.")
        else:
            await ctx.send("Unknown error, please contact owner.")
            print(error)

    # @commands.command()
    # async def me(self, ctx, user: discord.Member = None):
    #     if not user:
    #         user = ctx.author
    #
    #     if user.bot:
    #         await ctx.send("Bots don't study ;)")
    #         return
    #
    #     name = user.name + "#" + user.discriminator
    #
    #     monthly_row = await get_monthly_row(name)
    #     weekly_row = await get_weekly_row(name)
    #     daily_row = await get_daily_row(name)
    #     overall_row = await get_overall_row(name)
    #     if monthly_row == None:
    #         monthly_row = ["", "", "0"]
    #     place_total = ("#" + overall_row[0] if overall_row[0] else "No data")
    #     place_monthly = ("#" + monthly_row[0] if monthly_row[0] else "No data")
    #     place_weekly = ("#" + weekly_row[0] if weekly_row[0] else "No data")
    #     place_daily = ("#" + daily_row[0] if daily_row[0] else "No data")
    #
    #     min_total = (
    #         str(round(int(overall_row[2].replace(',', '')) / 60, 1)) + " h" if overall_row[2] else "No data").ljust(9)
    #     min_monthly = (
    #         str(round(int(monthly_row[2].replace(',', '')) / 60, 1)) + " h" if monthly_row[2] else "No data").ljust(9)
    #     min_weekly = (
    #         str(round(int(weekly_row[2].replace(',', '')) / 60, 1)) + " h" if weekly_row[2] else "No data").ljust(9)
    #     min_daily = (
    #         str(round(int(daily_row[2].replace(',', '')) / 60, 1)) + " h" if daily_row[2] else "No data").ljust(9)
    #
    #     average = str(round(float(min_monthly.strip()[:-1]) / datetime.datetime.utcnow().day,
    #                         1)) + " h" if min_monthly != "No data" else "No data"
    #
    #     streaks = await get_streaks(name)
    #     currentStreak = (str(streaks[1]) if streaks else "0")
    #     longestStreak = (str(streaks[2]) if streaks else "0")
    #     currentStreak += " day" + ("s" if int(currentStreak) != 1 else "")
    #     longestStreak += " day" + ("s" if int(longestStreak) != 1 else "")
    #
    #     emb = discord.Embed(
    #         description=f"```css\nPersonal study statistics```\n```glsl\nTimeframe   Hours    Place\n\nPast day:   {min_daily}{place_daily}\nPast week:  {min_weekly}{place_weekly}\nMonthly:    {min_monthly}{place_monthly}\nAll-time:   {min_total}{place_total}\n\nAverage/day ({self.bot.month}): {average}\n\nCurrent study streak: {currentStreak}\nLongest study streak: {longestStreak}```")
    #     foot = name
    #     if self.client.get_guild(self.client.guild_id).get_role(685967088170696715) in self.client.get_guild(
    #         self.client.guild_id).get_member(user.id).roles:
    #         foot = "⭐ " + foot
    #     emb.set_footer(text=foot, icon_url=user.avatar_url)
    #     await ctx.send(embed=emb)


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
