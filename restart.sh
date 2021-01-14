#!/bin/bash
pkill -f time_counter
git pull
nohup python main_time_counter.py 2>&1 > console.log &
tail -F console.log