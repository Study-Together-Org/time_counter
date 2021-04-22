# Author: https://github.com/Gugu7264
import os

import gspread_asyncio as gaio
import hjson
import pandas as pd
from discord import Intents
from discord.ext import commands
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials

import utilities

load_dotenv("dev.env")

client = commands.Bot(command_prefix=os.getenv("prefix"), intents=Intents.all())

with open("config.hjson") as f:
    config = hjson.load(f)


def get_creds():
    return ServiceAccountCredentials.from_json_keyfile_name(
        "creds.json",
        ["https://spreadsheets.google.com/feeds",
         'https://www.googleapis.com/auth/spreadsheets',
         "https://www.googleapis.com/auth/drive.file",
         "https://www.googleapis.com/auth/drive"],
    )


async def get_sheet(google_client):
    session = await google_client.authorize()
    sheet1 = (await session.open_by_url(
        "https://docs.google.com/spreadsheets/d/1xvmK6yawHbhtfvi_0Dvp9afWv8mZ5Tn7o_szE1a76ZY/edit")).sheet1
    sheet2 = (await session.open_by_url(
        "https://docs.google.com/spreadsheets/d/1hsw5l0IXoPK9k9CWXZrW556yAUsUdjtSs9joub4Oa_g/edit")).sheet1
    return sheet1, sheet2


def pair_data(data, cols, *row_name):
    print("data", len(data))
    final = []
    c = 0
    temp = []
    for d in data:
        if c == cols:
            final.append(temp)
            temp = []
            c = 0
        if d.value == "":
            break
        temp.append(d.value)
        c += 1
    if row_name:
        c = 1
        for name in row_name:
            final[0][c] = name
            c += 1
    return final


async def main():
    google_client = gaio.AsyncioGspreadClientManager(get_creds)

    sheets = await get_sheet(google_client)
    sheet = sheets[0]
    sheet2 = sheets[1]

    names = utilities.get_rank_categories(flatten=True)
    print(names)
    all_time = pair_data(sheet.range("J2:K" + str(sheet.row_count)), 2, "all_time")
    df_all_time = pd.DataFrame(all_time[1:], columns=all_time[0])

    monthly = pair_data(sheet.range("C2:D" + str(sheet.row_count)), 2, "monthly")
    df_monthly = pd.DataFrame(monthly[1:], columns=monthly[0])

    weekly = pair_data(sheet.range("Q2:R" + str(sheet.row_count)), 2, "weekly")
    df_weekly = pd.DataFrame(weekly[1:], columns=weekly[0])

    daily = pair_data(sheet.range("X2:Y" + str(sheet.row_count)), 2, "daily")
    df_daily = pd.DataFrame(daily[1:], columns=daily[0])

    # streaks = pair_data(sheet2.range("A3:C" + str(sheet2.row_count)), 3, "current_streak", "longest_streak")
    # df_streaks = pd.DataFrame(streaks[1:], columns=streaks[0])

    return [df_all_time, df_monthly, df_weekly, df_daily] # , df_streaks


@client.event
async def on_ready():
    guild = client.get_guild(utilities.get_guildID())
    a = await main()
    res = a[0]
    for i in a[1:]:
        res = pd.merge(res, i, how="outer", on="Discord username")
    # Make ids string to prevent finite precision as Dataframe converts into to floats
    username_to_id = {member.name + "#" + member.discriminator: str(member.id) for member in guild.members}
    res["id"] = res["Discord username"].map(username_to_id)
    res.dropna(subset=["id"], inplace=True)
    res["id"] = res["id"].astype(int)
    res.to_csv("./user_files/user_stats.csv", index=False, float_format='{:f}'.format, encoding='utf-8')

    await client.logout()


client.run(os.getenv('bot_token'))
print("Done")
