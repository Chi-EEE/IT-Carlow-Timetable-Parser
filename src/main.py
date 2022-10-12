from io import BytesIO
import os
from dotenv import load_dotenv
import requests
import re
import hashlib
import json
import jsonschema
from jsonschema import validate
import discord
from discord import app_commands
from discord.ext import tasks
from keep_alive import keep_alive

from timetable import Timetable

load_dotenv()

MINUTES = 2

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

timetable_name_to_id = {}

# List of timetables to update
timetables = {}


async def setup_timetable_name_to_id():
    response = requests.get("http://timetable.itcarlow.ie/js/filter.js")
    if response.status_code == 200:
        filter_js = response.text
        timetable_key_name = "studset"
        timetable_names = re.findall(
            rf"{timetable_key_name}array\[[0-9]*\] \[[0]\] = \"([a-zA-Z0-9\-\ \&\#\%_\(\)\/\-\,\.]+)\"",
            filter_js,
        )
        timetable_values = re.findall(
            rf"{timetable_key_name}array\[[0-9]*\] \[[2]\] = \"([a-zA-Z0-9\-\ \&\#\%_\(\)\/\-\,\.]+)\"",
            filter_js,
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


async def post_timetable_screenshot(
    channel: discord.TextChannel,
    timetable_id: str,
    timetable_screenshot: BytesIO,
):
    image_file = discord.File(timetable_screenshot, filename=f"{timetable_id}.png")
    await channel.send(file=image_file)


async def send_message(
    channel: discord.TextChannel, message: str, syntax_language: str, file_name: str
):
    """
    Sends a message whether the string is less than or equal to 2000 characters long or a text file if the string longer than 2000 characters.
    Parameters
    ------------
    channel: :class:`~discord.Channel`
        The channel to send the message to.
    message: :class:`~str`
        The message which to send to the channel.
    syntax_language: :class:`~str`
        The syntax language highlight of the message.
    file_name: :class:`~str`
        The file name of the message file if it is over 2000 characters.
    """
    if message != "":
        if len(message) <= 2000:
            await channel.send(
                content=f"""```{syntax_language}
            {message}```"""
            )
        else:
            text_file = discord.File(
                BytesIO(bytes(message, encoding="utf-8")),
                filename=f"{file_name}.{syntax_language}",
            )
            await channel.send(file=text_file)


async def send_timetable_alert(
    channel: discord.TextChannel,
    timetable_id: str,
    current_timetable: str,
    timetable_diff: str,
    timetable_screenshot: BytesIO,
):
    await send_message(channel, current_timetable, "json", timetable_id)
    await post_timetable_screenshot(channel, timetable_id, timetable_screenshot)
    await send_message(channel, timetable_diff, "diff", "Difference")


@tasks.loop(minutes=MINUTES)
async def alert_timetable():
    for timetable_id, timetable in timetables.items():
        await timetable.clear()
        await timetable.create_default()
        for channel in timetable.channels:
            timetable_diff = await timetable.get_previous_timetable_diff(channel)
            if timetable_diff != "":
                await send_timetable_alert(
                    channel,
                    timetable_id,
                    timetable.JSON_STRING,
                    timetable_diff,
                    timetable.SCREENSHOT,
                )


async def assign_timetable(timetable_id: str, channel: discord.TextChannel):
    if timetable_id not in timetables:
        timetable = Timetable(client, timetable_id)
        timetables[timetable_id] = timetable
        await timetable.create_default()
    timetable = timetables[timetable_id]
    await timetable.add_channel(channel=channel)
    timetable_diff = await timetable.get_previous_timetable_diff(channel)
    await send_timetable_alert(
        channel,
        timetable_id,
        timetable.JSON_STRING,
        timetable_diff,
        timetable.SCREENSHOT,
    )


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
            await assign_timetable(timetable_id, channel)
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
                    await assign_timetable(timetable_id, channel)
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
    alert_timetable.start()


keep_alive()  # Starts a webserver to be pinged.
client.run(os.getenv("TOKEN"))
