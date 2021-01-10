import os
from datetime import timedelta

from distest import TestCollector
from distest import run_command_line_bot
from discord import Embed
from sqlalchemy.orm import sessionmaker
from models import Action, User
import utilities

test_collector = TestCollector()
bot_container = []
bot = None
guild = None
bot_id = None
time_to_stay = 36
time_tolerance = timedelta(seconds=.1)

redis_client = utilities.get_redis_client()
engine = utilities.get_engine()
Session = sessionmaker(bind=engine)
sqlalchemy_session = Session()


@test_collector()
async def test_init(interface):
    global bot, guild, bot_id
    bot = bot_container[0]
    guild = bot.guilds[0]
    bot_id = bot.user.id


@test_collector()
async def test_incr(interface):
    await guild.system_channel.send(os.getenv("prefix") + "me")
    prev_stats = await utilities.get_user_stats(redis_client, bot_id)
    voice_channel = [channel for channel in guild.voice_channels if "screen/cam" in channel.name][1]
    voice_client = await voice_channel.connect()
    start_channel_time = utilities.get_time()
    utilities.sleep(time_to_stay)
    await voice_client.disconnect()
    end_channel_time = utilities.get_time()
    await guild.system_channel.send(os.getenv("prefix") + "me")
    utilities.sleep(3)
    cur_stats = await utilities.get_user_stats(redis_client, bot_id)
    # TODO test - use fields to check description?
    # reply = await guild.system_channel.history(limit=1).flatten()[0].embeds[0].description
    diff = utilities.check_stats_diff(prev_stats, cur_stats)
    is_all_increment_right = [hours * 3600 == time_to_stay for hours in diff]
    assert all(is_all_increment_right)

    # Check SQL
    records = sqlalchemy_session.query(Action) \
        .filter(Action.user_id == bot_id) \
        .filter(Action.category.in_(["end channel", "start channel"])) \
        .order_by(Action.creation_time.desc()).limit(2).all()
    records.reverse()

    assert (records[0].category == "start channel")
    assert (records[0].detail == records[1].detail == voice_channel.id)
    assert (records[0].creation_time - start_channel_time < time_tolerance)
    assert (records[1].creation_time - end_channel_time < time_tolerance)


@test_collector()
async def test_p(interface):
    embed = Embed(title=utilities.config["embed_titles"]["p"])
    await interface.assert_reply_embed_equals(os.getenv("prefix") + "p", embed, attributes_to_check=["title"])


@test_collector()
async def test_lb(interface):
    embed = Embed(title=f'{utilities.config["embed_titles"]["lb"]} ({utilities.get_month()})')
    await interface.assert_reply_embed_equals(os.getenv("prefix") + "lb", embed, attributes_to_check=["title"])


@test_collector()
async def test_lb_with_page(interface):
    embed = Embed(title=f'{utilities.config["embed_titles"]["lb"]} ({utilities.get_month()})')
    await interface.assert_reply_embed_equals(os.getenv("prefix") + "lb 4000000", embed, attributes_to_check=["title"])


@test_collector()
async def test_me(interface):
    embed = Embed(title=utilities.config["embed_titles"]["me"])
    await interface.assert_reply_embed_equals(os.getenv("prefix") + "me", embed, attributes_to_check=["title"])


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
    run_command_line_bot(target=int(os.getenv("test_bot_id")), token=os.getenv("test_bot_token"),
                         channel_id=int(os.getenv("test_channel_id")), tests="all",
                         stats=True, timeout=5, collector=test_collector, bot_container=bot_container)
