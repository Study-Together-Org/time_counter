import os
import subprocess
from datetime import timedelta
from time import sleep

from dotenv import load_dotenv

import utilities

load_dotenv("dev.env")
logger = utilities.get_logger("main", "heartbeat.log")

proc = None
line = utilities.get_last_line()
utilities.kill_last_process(line)

while True:
    try:
        line = utilities.get_last_line()
        last_time = utilities.get_last_time(line)
        max_diff_var_name = ("test_" if os.getenv("mode") == "test" else "") + "heart_attack_interval_sec"
        max_diff_sec = int(os.getenv(max_diff_var_name))
        max_diff = timedelta(seconds=max_diff_sec)

        if (not last_time) or utilities.get_time() - last_time > max_diff:
            proc = subprocess.Popen(['python3', './time_counter.py'])
            logger.info(f"{utilities.get_time()} birth with pid {proc.pid}")

        sleep(60 if os.getenv("mode") != "test" else max_diff_sec)
    except Exception as e:
        print(e)
        # This does not catch exceptions from child processes!!
        if proc:
            proc.kill()
        logger.info(f"{utilities.get_time()} graceful death")

        break
