import logging
import os
from datetime import datetime, timedelta

import discord
import hjson
from discord.ext import commands
from dotenv import load_dotenv

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


def get_utctime():
    now = datetime.utcnow()
    return now


def get_month_start():
    given_date = datetime.today().date()
    first_day_of_month = given_date - timedelta(days=int(given_date.strftime("%d")) - 1)
    return first_day_of_month


def round_num(num):
    return round(num, 1)


def calc_total_time(data):
    if not data:
        return 0

    total_time = timedelta(0)
    start_idx = 0
    end_idx = len(data) - 1

    if data[0]["category"] == "exit channel":
        total_time += data[0]["creation_time"] - get_month_start()
        start_idx = 1

    if data[-1]["category"] == "enter channel":
        total_time += get_utctime() - data[-1]["creation_time"]
        end_idx -= 1

    for idx in range(start_idx, end_idx + 1, 2):
        total_time += data[idx + 1]["creation_time"] - data[idx]["creation_time"]

    total_time = round_num(total_time.total_seconds() / 3600)
    return total_time


class Study(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.guild = None
        self.role_objs = None

    def get_role(self, user):
        user_study_roles = list(set(user.roles).intersection(set(self.role_name_to_obj.values())))
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

    async def fetch(self):
        if not self.guild:
            self.guild = self.bot.get_guild(guildID)
        self.role_name_to_obj = {role.name: role for role in self.guild.roles}

    @commands.Cog.listener()
    async def on_ready(self):
        if self.bot.pool is None:
            await self.bot.sql.init()

        print('We have logged in as {0.user}'.format(self.bot))
        # game = discord.Game(f"{self.bot.month} statistics")
        # await self.bot.change_presence(status=discord.Status.online, activity=game)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel == after.channel:
            return

        User_id = await self.get_User_id(member.id)

        for action_name, channel in [("exit channel", before.channel), ("enter channel", after.channel)]:
            if channel:
                insert_action = f"""
                    INSERT INTO Action (User_id, category, detail, creation_time)
                    VALUES ({User_id}, '{action_name}', '{channel.id}', '{get_utctime()}');
                """
                print(insert_action)
                response = await self.bot.sql.query(insert_action)
                if response:
                    print(response)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        insert_new_member = f"""
            INSERT INTO User (discord_user_id)
            VALUES ({member.id});
        """

        response = await self.bot.sql.query(insert_new_member)
        if response:
            print(response)

    async def get_User_id(self, discord_id):
        select_User_id = f"""
            SELECT id from User WHERE discord_user_id = {discord_id}
        """
        User_id = await self.bot.sql.query(select_User_id)
        return User_id[0]["id"]

    async def get_time_cur_month(self, User_id):
        insert_new_member = f"""
            SELECT category, creation_time FROM Action
            WHERE User_id = {User_id} AND (category = 'enter channel' OR category = 'exit channel')
        """
        print(insert_new_member)
        response = await self.bot.sql.query(insert_new_member)
        total_time = calc_total_time(response)
        return total_time

    @commands.command(aliases=["rank"])
    async def p(self, ctx, user: discord.Member = None):
        # if the user has not specified someone else
        if not user:
            user = ctx.author

        if user.bot:
            await ctx.send("Bots don't study ;)")
            return

        name = user.name + "#" + user.discriminator
        User_id = await self.get_User_id(user.id)
        hours_cur_month = await self.get_time_cur_month(User_id)
        if not self.role_objs:
            await self.fetch()

        role, next_role = self.get_role(user)
        next_time = None

        if not hours_cur_month:
            # New member
            next_time = role_name_to_begin_hours[next_role] - hours_cur_month
            next_time = round_num(next_time)

        text = f"""
        **User:** ``{name}``\n
        __Study role__ ({get_utctime().strftime("%B")})
        **Current study role:** {role.mention if role else "No Role"}
        **Next study role:** {next_role.mention if next_role else "``👑 Highest rank reached``"}
        **Role promotion in:** ``{(str(next_time) + 'h') if next_time else list(role_name_to_begin_hours.values())[1]}``
        **Role rank:** ``{'👑 ' if role and role_names.index(role.name) + 1 == {len(roles)} else ''}{role_names.index(role.name) + 1 if role else '0'}/{len(roles)}``
        """

        emb = discord.Embed(title=":coffee: Personal rank statistics", description=text)
        await ctx.send(embed=emb)

    @commands.command()
    async def me(self, ctx, user: discord.Member = None):
        if not user:
            user = ctx.author

        if user.bot:
            await ctx.send("Bots don't study ;)")
            return

        name = user.name + "#" + user.discriminator

        monthly_row = await get_monthly_row(name)
        weekly_row = await get_weekly_row(name)
        daily_row = await get_daily_row(name)
        overall_row = await get_overall_row(name)
        if monthly_row == None:
            monthly_row = ["", "", "0"]
        place_total = ("#" + overall_row[0] if overall_row[0] else "No data")
        place_monthly = ("#" + monthly_row[0] if monthly_row[0] else "No data")
        place_weekly = ("#" + weekly_row[0] if weekly_row[0] else "No data")
        place_daily = ("#" + daily_row[0] if daily_row[0] else "No data")

        min_total = (
            str(round(int(overall_row[2].replace(',', '')) / 60, 1)) + " h" if overall_row[2] else "No data").ljust(9)
        min_monthly = (
            str(round(int(monthly_row[2].replace(',', '')) / 60, 1)) + " h" if monthly_row[2] else "No data").ljust(9)
        min_weekly = (
            str(round(int(weekly_row[2].replace(',', '')) / 60, 1)) + " h" if weekly_row[2] else "No data").ljust(9)
        min_daily = (
            str(round(int(daily_row[2].replace(',', '')) / 60, 1)) + " h" if daily_row[2] else "No data").ljust(9)

        average = str(round(float(min_monthly.strip()[:-1]) / datetime.datetime.utcnow().day,
                            1)) + " h" if min_monthly != "No data" else "No data"

        streaks = await get_streaks(name)
        currentStreak = (str(streaks[1]) if streaks else "0")
        longestStreak = (str(streaks[2]) if streaks else "0")
        currentStreak += " day" + ("s" if int(currentStreak) != 1 else "")
        longestStreak += " day" + ("s" if int(longestStreak) != 1 else "")

        emb = discord.Embed(
            description=f"```css\nPersonal study statistics```\n```glsl\nTimeframe   Hours    Place\n\nPast day:   {min_daily}{place_daily}\nPast week:  {min_weekly}{place_weekly}\nMonthly:    {min_monthly}{place_monthly}\nAll-time:   {min_total}{place_total}\n\nAverage/day ({self.bot.month}): {average}\n\nCurrent study streak: {currentStreak}\nLongest study streak: {longestStreak}```")
        foot = name
        if self.client.get_guild(self.client.guild_id).get_role(685967088170696715) in self.client.get_guild(
            self.client.guild_id).get_member(user.id).roles:
            foot = "⭐ " + foot
        emb.set_footer(text=foot, icon_url=user.avatar_url)
        await ctx.send(embed=emb)


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
