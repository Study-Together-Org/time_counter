import os
from datetime import timedelta

from distest import TestCollector
from distest import run_command_line_bot
from discord import Embed
from sqlalchemy.orm import sessionmaker
from setup.models import Action
import utilities

test_collector = TestCollector()
bot = None
guild = None
bot_id = None
time_to_stay = 3600 / (10 ** int(os.getenv("display_num_decimal")))
db_tolerance = timedelta(seconds=.2)
redis_tolerance = 3.6 * 1.5
discord_delay = 2  # discord api, when slow, could take 5 seconds to send messages
past_time = "2pm"  # specify some timepoint for commands that support it
prefix = utilities.config["prefixes"][0]
me_command = f"{prefix}me {past_time}"
timepoint = None

redis_client = utilities.get_redis_client()
engine = utilities.get_engine()
Session = sessionmaker(bind=engine)
sqlalchemy_session = Session()


@test_collector()
async def test_init(interface):
    # A workaround for shared info
    # TODO test -  Get rid of this function by calling these for each test, so we can specify running just one test if we want
    global bot, guild, bot_id, timepoint
    bot = interface.client
    guild = bot.guilds[0]
    bot_id = bot.user.id
    timepoint, display_timezone, display_timepoint = await utilities.get_user_timeinfo(guild.system_channel, bot.user, past_time)


@test_collector()
async def test_start_end_channel_incr(interface):
    await guild.system_channel.send(me_command)
    prev_stats = await utilities.get_user_stats(redis_client, bot_id, timepoint=timepoint)
    voice_channel = [channel for channel in guild.voice_channels if "screen/cam" in channel.name][1]
    voice_client = await voice_channel.connect()
    start_channel_time = utilities.get_time()
    utilities.sleep(time_to_stay)
    await voice_client.disconnect()
    end_channel_time = utilities.get_time()
    await guild.system_channel.send(me_command)
    utilities.sleep(discord_delay)
    cur_stats = await utilities.get_user_stats(redis_client, bot_id, timepoint=timepoint)
    # TODO test - use fields to check description?
    # reply = await guild.system_channel.history(limit=1).flatten()[0].embeds[0].description
    assert (utilities.check_stats_diff(prev_stats, cur_stats, time_to_stay, 1, redis_tolerance))

    # Check SQL
    records = sqlalchemy_session.query(Action) \
        .filter(Action.user_id == bot_id) \
        .filter(Action.category.in_(["end channel", "start channel"])) \
        .order_by(Action.creation_time.desc()).limit(2).all()
    records.reverse()

    assert (records[0].category == "start channel")
    assert (records[0].detail == records[1].detail == voice_channel.id)
    assert (records[0].creation_time - start_channel_time <= db_tolerance)
    assert (records[1].creation_time - end_channel_time <= db_tolerance)


@test_collector()
async def test_p(interface):
    embed = Embed(title=utilities.config["embed_titles"]["p"])
    await interface.assert_reply_embed_equals(prefix + "p", embed, attributes_to_check=["title"])


@test_collector()
async def test_lb(interface):
    embed = Embed(title=f'{utilities.config["embed_titles"]["lb"]} ({utilities.get_month()})')
    await interface.assert_reply_embed_equals(prefix + "lb", embed, attributes_to_check=["title"])


@test_collector()
async def test_lb_with_page(interface):
    embed = Embed(title=f'{utilities.config["embed_titles"]["lb"]} ({utilities.get_month()})')
    await interface.assert_reply_embed_equals(prefix + "lb - 4000000", embed, attributes_to_check=["title"])


@test_collector()
async def test_me(interface):
    embed = Embed(title=utilities.config["embed_titles"]["me"])
    await interface.assert_reply_embed_equals(prefix + "me", embed, attributes_to_check=["title"])
    utilities.sleep(discord_delay)


@test_collector()
async def test_in_session(interface):
    # TODO test - find out why this test can't be before test_p
    await guild.system_channel.send(me_command)
    prev_stats = await utilities.get_user_stats(redis_client, bot_id, timepoint=timepoint)
    voice_channel = [channel for channel in guild.voice_channels if "screen/cam" in channel.name][1]
    voice_client = await voice_channel.connect()

    multiplier = 2
    # multiplier = 175
    utilities.sleep(time_to_stay * multiplier)
    await guild.system_channel.send(me_command)
    utilities.sleep(discord_delay)
    mid_stats = await utilities.get_user_stats(redis_client, bot_id, timepoint=timepoint)
    assert (utilities.check_stats_diff(prev_stats, mid_stats, time_to_stay, multiplier, redis_tolerance))

    multiplier = 5
    # multiplier = 2147

    utilities.sleep(time_to_stay * multiplier)
    await voice_client.disconnect()
    await guild.system_channel.send(me_command)
    utilities.sleep(discord_delay)
    cur_stats = await utilities.get_user_stats(redis_client, bot_id, timepoint=timepoint)
    assert (utilities.check_stats_diff(mid_stats, cur_stats, time_to_stay, multiplier, redis_tolerance))

# TODO test - using large numbers as inputs to see if CPU hangs; it has caused discord.py not to log in the past
# TODO test - Write case for new member + each role...

# start id_1
# start id_1
#
# #done
# start id_1
# start id_2
#
# end id_1
# end id_1
#
# end id_1
# end id_2
#
# #done
# start id_1
# end id_1
#
# #done
# start id_1
# end id_2
#
# #done
# end id_1
# start id_1
#
# #done
# end id_1
# start id_2

if __name__ == "__main__":
    run_command_line_bot(target=int(os.getenv("bot_id")), token=os.getenv("test_bot_token"),
                         channel_id=int(os.getenv("test_channel_id")), tests="all",
                         stats=True, timeout=5, collector=test_collector)
