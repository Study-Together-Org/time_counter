import asyncio
import logging
import os
import subprocess
from datetime import datetime, timedelta
from time import sleep

from discord import Intents
from discord.ext import commands
from dotenv import load_dotenv

import dbmanagement as dbm
import utilities

load_dotenv("dev.env")
logger = utilities.get_logger("main")


def get_last_time():
    with open('heartbeat.log', 'rb') as f:
        f.seek(-2, os.SEEK_END)
        while f.read(1) != b'\n':
            f.seek(-2, os.SEEK_CUR)
            # TODO handle empty file
            # TODO handle non timestamp
        last_line = f.readline().decode().strip()

    return datetime.strptime(last_line, "%Y-%m-%d %H:%M:%S.%f")


proc = None

while True:
    try:
        if utilities.get_time() - get_last_time() > timedelta(minutes=1):
            proc = subprocess.Popen(['python3', './time_counter.py'])
            logger.log(40, f"restart bot with pid: {proc.pid}")
            sleep(10)

        sleep(60)
    except KeyboardInterrupt:
        if proc:
            proc.kill()

        break

# TODO actually kill the bot
# proc.kill()
