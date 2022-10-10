from io import BytesIO, TextIOWrapper
import os
from dotenv import load_dotenv
import requests
import re
from pyppeteer import launch
import hashlib
import json
import jsonschema
from jsonschema import validate
from bs4 import BeautifulSoup
import discord
from discord import app_commands
import difflib

from timetable import Timetable

load_dotenv()

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

timetable_name_to_id = {}


async def setup_timetable_name_to_id():
    response = requests.get("http://timetable.itcarlow.ie/js/filter.js")
    if response.status_code == 200:
        filterJS = response.text
        timetable_key_name = "studset"
        timetable_names = re.findall(
            rf"{timetable_key_name}array\[[0-9]*\] \[[0]\] = \"([a-zA-Z0-9\-\ \&\#\%_\(\)\/\-\,\.]+)\"",
            filterJS,
        )
        timetable_values = re.findall(
            rf"{timetable_key_name}array\[[0-9]*\] \[[2]\] = \"([a-zA-Z0-9\-\ \&\#\%_\(\)\/\-\,\.]+)\"",
            filterJS,
        )
        for timetable_name, timetable_value in zip(timetable_names, timetable_values):
            timetable_name_to_id[timetable_name] = timetable_value
    else:
        print("Unable to get filter.js from timetable.itcarlow.ie")


timetable_channel_schema = {
    "type": "object",
    "properties": {
        "url": {"type": "string"},
        "id": {"type": "string"},
        "hash": {"type": "string"},
    },
    "additionalProperties": False,
}

# This is to check if the channel was set up properly
async def get_timetable_hash(timetable_url: str, timetable_id: str):
    return hashlib.sha256(
        (os.getenv("PRIVATE_HASH") + timetable_url + timetable_id).encode()
    ).hexdigest()

async def post_timetable_screenshot(channel: discord.TextChannel, timetable: Timetable, timetable_id: str):
    image_file = discord.File(await timetable.get_timetable_screenshot(), filename=f"{timetable_id}.png")
    await channel.send(file=image_file)

async def send_message(channel: discord.TextChannel, message: str, syntax_language: str, file_name: str):
    if message != "":
        if len(message) <= 4000:
            await channel.send(content=f"""```{syntax_language}
            {message}```""")
        else:
            text_file = discord.File(
                BytesIO(bytes(message, encoding="utf-8")),
                filename=f"{file_name}.{syntax_language}",
            )
            await channel.send(file=text_file)

async def send_timetable_messages(channel: discord.TextChannel, timetable: Timetable, timetable_id: str):
    current_timetable = await timetable.get_timetable_json()
    timetable_diff = await timetable.get_previous_timetable_diff()
    await send_message(channel, current_timetable, "json", timetable_id)
    await post_timetable_screenshot(channel, timetable, timetable_id)
    await send_message(channel, timetable_diff, "diff", "Difference")

@tree.command(
    name="timetable_assign",
    description="Designate the discord channel as a timetable channel",
)
@app_commands.describe(
    channel_name="Your Channel's Name (Can be anything)",
    timetable_string="The Name / Id of the timetable (Not URL)",
)
async def timetable_assign(
    interaction: discord.InteractionMessage, channel_name: str, timetable_string: str
):
    has_channel = None
    for channel in interaction.guild.channels:
        if isinstance(channel, discord.TextChannel) and channel.name == channel_name:
            has_channel = channel
            break
    if has_channel:
        if not (timetable_id := timetable_name_to_id.get(timetable_string)):
            timetable_id = timetable_string
        timetable_url = f"http://timetable.itcarlow.ie/reporting/individual;student+set;id;{timetable_id}?t=student+set+individual&days=1-5&weeks=&periods=5-40&template=student+set+individual"
        res = requests.get(timetable_url)
        if res.status_code == 200:
            await has_channel.edit(
                topic=json.dumps(
                    {
                        "url": timetable_url,
                        "id": timetable_id,
                        "hash": await get_timetable_hash(timetable_url, timetable_id),
                    }
                )
            )
            await interaction.response.send_message(
                f"The timetable channel has been assigned.", ephemeral=True
            )
            timetable = Timetable(client, channel, timetable_id)
            await send_timetable_messages(channel, timetable, timetable_id)
        else:
            await interaction.response.send_message(
                f"The requested timetable id ({timetable_id}) is invalid.",
                ephemeral=True,
            )
    else:
        await interaction.response.send_message(
            f"Unable to find the channel ({channel_name}).", ephemeral=True
        )


async def get_timetable_channels():
    channels = client.get_all_channels()
    while channel := next(channels, None):
        if isinstance(channel, discord.TextChannel) and channel.topic:
            try:
                timetable_info = json.loads(channel.topic)
                validate(instance=timetable_info, schema=timetable_channel_schema)
                timetable_id = timetable_info.get("id")
                timetable_url = timetable_info.get("url")
                real_hash = await get_timetable_hash(timetable_url, timetable_id)
                if real_hash == timetable_info.get("hash"):
                    timetable = Timetable(client, channel, timetable_id)
                    await send_timetable_messages(channel, timetable, timetable_id)
                    break
            except jsonschema.ValidationError:
                pass
            except ValueError:
                pass


@client.event
async def on_ready():
    print(f"We have logged in as {client.user}")
    await setup_timetable_name_to_id()
    await tree.sync()
    await get_timetable_channels()


client.run(os.getenv("TOKEN"))
