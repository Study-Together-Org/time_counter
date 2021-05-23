#!/bin/bash
pkill -15 -f time_counter
git pull
set -e
source venv/bin/activate
nohup python controller_time_counter.py > console.log 2>&1 &
tail -F console.log