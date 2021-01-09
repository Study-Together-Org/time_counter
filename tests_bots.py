import os
import sys
from distest import TestCollector
from distest import run_dtest_bot
from discord import Embed
import utilities
from freezegun import freeze_time

test_collector = TestCollector()


@test_collector()
async def test_p(interface):
    # TODO test - Write case for new member + each role...
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
    # TODO test - read args from dev.end
    run_dtest_bot(sys.argv, test_collector)
