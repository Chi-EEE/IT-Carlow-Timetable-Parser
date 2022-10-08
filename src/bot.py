import os
import requests
import hashlib
import json
import jsonschema
from jsonschema import validate
from dotenv import load_dotenv
import discord
from discord import app_commands

load_dotenv()

import discord

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

timetable_channel_schema = {
    "type": "object",
    "properties": {
        "url": {"type": "string"},
        "id": {"type": "string"},
        "hash": {"type": "string"},
    },
    "additionalProperties": False,
}


@tree.command(
    name="timetable_assign",
    description="Designate the discord channel as a timetable channel",
)
@app_commands.describe(
    channel_name="Your Channel's Name (Can be anything)",
    timetable_id="The Id of the timetable",
)
async def timetable_assign(
    interaction: discord.InteractionMessage, channel_name: str, timetable_id: str
):
    has_channel = None
    for channel in interaction.guild.channels:
        if channel.name == channel_name:
            has_channel = channel
            break
    if has_channel:
        timetable_url = f"http://timetable.itcarlow.ie/reporting/individual;student+set;id;{timetable_id}?t=student+set+individual&days=1-5&weeks=&periods=5-40&template=student+set+individual"
        res = requests.get(timetable_url)
        if res.status_code == 200:
            await has_channel.edit(
                topic=json.dumps(
                    {
                        "url": timetable_url,
                        "id": timetable_id,
                        "hash": hashlib.sha256(  # This is to check if the channel was set up properly
                            (os.getenv("PRIVATE_HASH") + timetable_id).encode("utf-8")
                        ).hexdigest(),
                    }
                )
            )
            await interaction.response.send_message(
                f"The timetable channel has been assigned."
            )
        else:
            await interaction.response.send_message(
                f"The requested timetable id ({timetable_id}) is invalid."
            )
    else:
        await interaction.response.send_message(
            f"Unable to find the channel ({channel_name})."
        )


async def get_timetable_channels():
    channels = client.get_all_channels()
    while channel := next(channels, None):
        if isinstance(channel, discord.TextChannel) and channel.topic:
            try:
                timetable_info = json.loads(channel.topic)
                validate(instance=timetable_info, schema=timetable_channel_schema)
                print(timetable_info.get("hash"))
            except jsonschema.ValidationError:
                pass
            except ValueError:
                pass


@client.event
async def on_ready():
    print(f"We have logged in as {client.user}")
    await tree.sync()
    await get_timetable_channels()


client.run(os.getenv("TOKEN"))
