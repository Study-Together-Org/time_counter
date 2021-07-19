#!/bin/bash
set -e
python timezone_bot.py &
python controller_time_counter.py > console.log 2>&1
