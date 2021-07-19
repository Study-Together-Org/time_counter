#!/bin/bash
set -e
source .venv/bin/activate
nohup python controller_time_counter.py > console.log 2>&1 &