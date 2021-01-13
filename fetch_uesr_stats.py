import gspread_asyncio as gaio
from oauth2client.service_account import ServiceAccountCredentials

import asyncio
from pprint import pprint
# import json

import pandas as pd
import utilities
import json


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
    sheet1 = (await session.open_by_url("https://docs.google.com/spreadsheets/d/1xvmK6yawHbhtfvi_0Dvp9afWv8mZ5Tn7o_szE1a76ZY/edit")).sheet1
    sheet2 = (await session.open_by_url("https://docs.google.com/spreadsheets/d/1hsw5l0IXoPK9k9CWXZrW556yAUsUdjtSs9joub4Oa_g/edit")).sheet1
    return (sheet1, sheet2)


def pair_data(data, cols, *row_name):
    print("DATA", len(data))
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

    names = utilities.get_rank_categories()
    print(names)
    all_time = pair_data(sheet.range("J2:K" + str(sheet.row_count)), 2, names["all_time"])
    df_all_time = pd.DataFrame(all_time[1:], columns=all_time[0])

    monthly = pair_data(sheet.range("C2:D" + str(sheet.row_count)), 2, names["monthly"])
    df_monthly = pd.DataFrame(monthly[1:], columns=monthly[0])

    weekly = pair_data(sheet.range("Q2:R" + str(sheet.row_count)), 2, names["weekly"])
    df_weekly = pd.DataFrame(weekly[1:], columns=weekly[0])

    daily = pair_data(sheet.range("X2:Y" + str(sheet.row_count)), 2, names["daily"])
    df_daily = pd.DataFrame(daily[1:], columns=daily[0])

    streaks = pair_data(sheet2.range("A3:C" + str(sheet2.row_count)), 3, "current_streak", "longest_streak")
    df_streaks = pd.DataFrame(streaks[1:], columns=streaks[0])

    return [df_all_time, df_monthly, df_weekly, df_daily, df_streaks]


a = asyncio.get_event_loop().run_until_complete(main())
res = a[0]
for i in a[1:]:
    res = pd.merge(res, i, how="outer", on="Discord username")


def df_func(name):
    return name[:3]


with open("user_files/mapping_ids.json") as f:
    ids = json.load(f)

res["id"] = res["Discord username"].map(ids)
res.fillna(0, inplace=True)
res = res[res.all_time != 0]
res = res[res.id != 0]
# res = pd.merge(a[0], a[1], how="outer", on="Discord username")
# res = pd.concat(a, axis=0)
# print(list(res))
res.to_csv("./user_files/user_stats.csv", index=False)
