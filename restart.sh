#!/bin/bash
set -e
pkill -f time_counter
git pull
source venv/bin/activate
nohup python main_time_counter.py 2>&1 > console.log &
tail -F console.log