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
    await interface.assert_reply_embed_equals("!p", embed, attributes_to_check=["title"])


@test_collector()
async def test_lb(interface):
    embed = Embed(title=f'{utilities.config["embed_titles"]["lb"]} ({utilities.get_month()})')
    await interface.assert_reply_embed_equals("!lb", embed, attributes_to_check=["title"])


@test_collector()
async def test_lb_with_page(interface):
    embed = Embed(title=f'{utilities.config["embed_titles"]["lb"]} ({utilities.get_month()})')
    await interface.assert_reply_embed_equals("!lb 4000000", embed, attributes_to_check=["title"])


@test_collector()
async def test_me(interface):
    embed = Embed(title=utilities.config["embed_titles"]["me"])
    await interface.assert_reply_embed_equals("!me", embed, attributes_to_check=["title"])


if __name__ == "__main__":
    run_dtest_bot(sys.argv, test_collector)
