import os
<<<<<<< Updated upstream
from pyppeteer import launch
=======
from dotenv import load_dotenv
>>>>>>> Stashed changes
import requests
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
async def get_timetable_hash(timetable_id: str):
    return hashlib.sha256(
        (os.getenv("PRIVATE_HASH") + timetable_id).encode("utf-8")
    ).hexdigest()


async def post_messages(channel: discord.TextChannel, timetable_id):
    timetable_url = f"http://timetable.itcarlow.ie/reporting/textspreadsheet;student+set;id;{timetable_id}?t=student+set+textspreadsheet&days=1-5&weeks=&periods=5-40&template=student+set+textspreadsheet"
    timetable_html = requests.get(timetable_url)
    timetable_soup = BeautifulSoup(timetable_html.text)
    body = timetable_soup.find("body")
    days = [p.find("span").string for p in body.find_all("p", recursive=False)]
    tables = body.findChildren("table", recursive=False)
    timetable_days = tables[1:-1]

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
        await channel.send(json.dumps({day: day_modules}))


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
        if isinstance(channel, discord.TextChannel) and channel.name == channel_name:
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
                        "hash": await get_timetable_hash(timetable_id),
                    }
                )
            )
            await interaction.response.send_message(
                f"The timetable channel has been assigned."
            )
            await post_messages(has_channel, timetable_id)
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
                timetable_id = timetable_info.get("id")
                real_hash = await get_timetable_hash(timetable_id)
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
    await tree.sync()
    await get_timetable_channels()


client.run(os.getenv("TOKEN"))
