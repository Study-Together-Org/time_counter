import os
import subprocess
from datetime import timedelta
from time import sleep

import utilities

logger = utilities.get_logger("main", "heartbeat.log")

proc = None
line = utilities.get_last_line()
# TODO: fix - Dangerous - need to make sure it's our process
utilities.kill_last_process(line)

while True:
    try:
        line = utilities.get_last_line()
        last_time = utilities.get_last_time(line)
        max_diff_sec = int(os.getenv("heart_attack_interval_sec"))
        max_diff = timedelta(seconds=max_diff_sec)

        if (not last_time) or utilities.get_time() - last_time > max_diff:
            # Process has died. Restart it
            proc = subprocess.Popen(['python3', './time_counter.py'])
            logger.info(f"{utilities.get_time()} birth with pid {proc.pid}")

        sleep(max_diff_sec)
    except Exception as e:
        print(e)
        # This does not catch exceptions from child processes!!
        if proc:
            proc.kill()
        logger.info(f"{utilities.get_time()} graceful death")

        break
