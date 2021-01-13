#!/bin/bash
sudo apt update

sudo apt-get install python3.8-venv python3.8-dev
python3.8 -m venv venv
source venv/bin/activate

sudo apt install mariadb-server
sudo mysql_secure_installation  # manual choices needed
# https://stackoverflow.com/questions/39281594/error-1698-28000-access-denied-for-user-rootlocalhost/42742610#42742610
sudo systemctl enable --now mysql
# to test: mysql -u root -p

sudo apt install redis-server
sudo systemctl enable redis-server
# to test: redis-cli

# manual: create a database called studytogether
# manual: set up dev.env config (create bot etc)

python models.py
python create_roles.py
python get_monitored_categories.py
python insert_real_data.py  # optional
touch discord.log
touch heartbeat.log

nohup python main_time_counter.py 2>&1 > console.log &
# to check: ps -ef | egrep "main_study|PID"
tail -F discord.log
# wait for login log to show