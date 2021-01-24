#!/bin/bash
set -e
pkill -f time_counter
git pull
source venv/bin/activate
nohup python main_time_counter.py > console.log 2>&1 &
tail -F console.log