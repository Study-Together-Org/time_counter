from discord.ext import commands
import dbmanagement as dbm

client = commands.Bot(command_prefix="!")


@client.event
async def on_ready():
    if client.pool is None:
        await client.sql.init()


@client.command()
async def test(ctx):
    # Then whenever you need to use it
    response = await client.sql.query("SELECT * FROM studies WHERE user_id = %s", user_id)
    # My class manages arguments
    await ctx.send(str(response))


client.pool = None
client.sql = MySQL(client)

client.run("token")
