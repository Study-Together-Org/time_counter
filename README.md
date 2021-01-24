# [Study Together!](https://discord.me/studytogether) Codebase
[![Discord Server](https://img.shields.io/discord/595999872222756885?color=purple&label=Discord)](https://discord.me/studytogether)

[![Pull Requests Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat)](http://makeapullrequest.com)
[![first-timers-only Friendly](https://img.shields.io/badge/first--timers--only-friendly-blue.svg)](http://www.firsttimersonly.com/)

# How to Install
(optional) Create a virtual environment
`pip3 install -r requirements.txt`
Set up MySQL database and Redis

(optional) Get credentials from the dev team
(optional) If you are using PyCharm, install [.env files support](https://plugins.jetbrains.com/plugin/9525--env-files-support) for env file autocompletion.

# Quick Start
`insert_data.py`
`timezone_bot.py`
`time_counter.py`

# License
All rights reserved until I figure out which license is compatible with the used libraries.

## Backgorund
Discord chatroom 
* 45k members in total (30 days 5k, over 10%)
* Concurrently could reach ~5k+ members in diff channels
* Rate of requests about 5/sec

## Requirements

* The rankings are based on the following
  * all-time
  * monthly (reset at UTC 5pm)
  * weekly (reset at UTC 5pm)
  * daily (reset at UTC 5pm)
  * minutes (every single minute in the past 24h)
* Auto restart when the discord bot dies

* Show streak

## Mechanism
### basic
A process listens to events from discord api when members join/leave study channels or request stats.
This process will insert logs into a SQL database (not any analytical data).

### ranking
# efficient way to maintain a linked list in sorted order
Another bot will use in memory sorted sets (also called skip lists) in-memory cache Redis to maintain the users' scores and rankings.
Each ranking has a different sorted sets.
num of sorted set: 1 + 1 + 1 + 24 * 60

### problems
past 24h ranking not fully accurate
event based

streaks used: 

daily Ranking last 24 hours (bad idea; your study time from yesterday influences your studytime and ranking today)
periodic calculating the ranking
not accurate, not real time, the wait time will keep increasing
