from io import BytesIO
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

timetable_info_schema = {
    "definitions": {
        "DayEntry": {
            "properties": {
                "Activity": {"type": "string"},
                "Name": {"type": "string"},
                "Type": {"type": "string"},
                "Start": {"type": "string"},
                "End": {"type": "string"},
                "Duration": {"type": "string"},
                "Weeks": {"type": "string"},
                "Room": {"type": "string"},
                "Staff": {"type": "string"},
                "Student_Groups": {"type": "string"},
            },
            "additionalProperties": False,
        }
    },
    "type": "object",
    "required": ["npcs"],
    "additionalProperties": False,
    "properties": {"items": {"$ref": "#/definitions/DayEntry"}},
}

# This is to check if the channel was set up properly
async def get_timetable_hash(timetable_url: str, timetable_id: str):
    return hashlib.sha256(
        (os.getenv("PRIVATE_HASH") + timetable_url + timetable_id).encode()
    ).hexdigest()


async def send_json_messages(channel: discord.TextChannel, timetable_id):
    text_timetable_url = f"http://timetable.itcarlow.ie/reporting/textspreadsheet;student+set;id;{timetable_id}?t=student+set+textspreadsheet&days=1-5&weeks=&periods=5-40&template=student+set+textspreadsheet"
    timetable_html = requests.get(text_timetable_url)
    timetable_soup = BeautifulSoup(timetable_html.text, features="html.parser")
    body = timetable_soup.find("body")
    days = [p.find("span").string for p in body.find_all("p", recursive=False)]
    tables = body.findChildren("table", recursive=False)
    timetable_days = tables[1:-1]

    week_modules = {}
    for day, modules in zip(days, timetable_days):
        modules = modules.find_all("tr")[1:]
        day_modules = []
        for module in modules:
            (
                module_activity,
                module_name,
                module_type,
                module_start,
                module_end,
                module_duration,
                module_weeks,
                module_room,
                module_staff,
                module_student_groups,
            ) = (module_info.string for module_info in module.find_all("td"))
            day_modules.append(
                {
                    "Activity": module_activity,
                    "Name": module_name,
                    "Type": module_type,
                    "Start": module_start,
                    "End": module_end,
                    "Duration": module_duration,
                    "Weeks": module_weeks,
                    "Room": module_room,
                    "Staff": module_staff,
                    "Student_Groups": module_student_groups,
                }
            )
        week_modules[day] = day_modules
    json_file = discord.File(
        BytesIO(bytes(json.dumps(week_modules, indent=4), encoding="utf-8")),
        filename=f"{timetable_id}.json",
    )
    await channel.send(file=json_file)


async def compare_previous_timetable(channel: discord.TextChannel, timetable_id):
    messages = await channel.history(limit=15)
    print("reading")
    while await (message := next(messages, None)):
        print(message.content)
        if message.author == client.user:
            message = next(messages)
            try:
                previous_timetable_info = json.loads(message.content)
                validate(
                    instance=previous_timetable_info, schema=timetable_channel_schema
                )
                print("correct")
            except jsonschema.ValidationError:
                pass
            except ValueError:
                pass
            message = next(messages)
            break


async def send_timetable_screenshot(channel: discord.TextChannel, timetable_id):
    user_timetable_url = f"http://timetable.itcarlow.ie/reporting/individual;student+set;id;{timetable_id}?t=student+set+individual&days=1-5&weeks=&periods=5-40&template=student+set+individual"
    browser = await launch(headless=True)
    page = await browser.newPage()
    await page.goto(user_timetable_url)
    timetable_screen = await page.screenshot({"fullPage": True})
    await browser.close()
    image_file = discord.File(BytesIO(timetable_screen), filename=f"{timetable_id}.png")
    await channel.send(file=image_file)


async def post_messages(channel: discord.TextChannel, timetable_id):
    await send_json_messages(channel, timetable_id)
    # await compare_previous_timetable(channel, timetable_id)
    await send_timetable_screenshot(channel, timetable_id)


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
            await post_messages(has_channel, timetable_id)
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
                    await post_messages(channel, timetable_id)
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
