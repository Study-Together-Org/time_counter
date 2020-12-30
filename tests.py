import sys
from distest import TestCollector
from distest import run_dtest_bot
from discord import Embed
import utilities

test_collector = TestCollector()


@test_collector()
async def test_p(interface):
    embed = Embed(title=':coffee: Personal rank statistics')
    await interface.assert_reply_embed_equals("!p", embed, attributes_to_check=["title"])


@test_collector()
async def test_lb(interface):
    embed = Embed(title=f'🧗 Study leaderboard ({utilities.get_month()})')
    await interface.assert_reply_embed_equals("!lb", embed, attributes_to_check=["title"])

if __name__ == "__main__":
    run_dtest_bot(sys.argv, test_collector)
