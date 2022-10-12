from io import BytesIO, TextIOWrapper
import requests
from pyppeteer import launch
import json
import jsonschema
from jsonschema import validate
from bs4 import BeautifulSoup
import discord
import difflib

module_schema = {
    "type": "object",
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

day_schema = {
    "type": "array",
    "items": module_schema,
    "additionalProperties": False,
}

timetable_info_schema = {
    "type": "object",
    "properties": {
        "Monday": day_schema,
        "Tuesday": day_schema,
        "Wednesday": day_schema,
        "Thursday": day_schema,
        "Friday": day_schema,
        "Saturday": day_schema,
        "Sunday": day_schema,
    },
    "additionalProperties": False,
}


def _unidiff_output(expected, actual):
    """
    Helper function. Returns a string containing the unified diff of two multiline strings.
    """
    expected = expected.splitlines(1)
    actual = actual.splitlines(1)

    diff = difflib.unified_diff(expected, actual)

    return "".join(diff)


class Timetable:
    def __init__(self, client: discord.Client, timetable_id: str):
        self.client = client
        self.timetable_id = timetable_id
        self.channels: list[discord.TextChannel] = []
        self.created = False
        self.JSON_STRING = ""
        self.SCREENSHOT: BytesIO = False

    async def get_json(self):
        text_timetable_url = f"http://timetable.itcarlow.ie/reporting/textspreadsheet;student+set;id;{self.timetable_id}?t=student+set+textspreadsheet&days=1-5&weeks=&periods=5-40&template=student+set+textspreadsheet"
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
        self.JSON_STRING = json.dumps(week_modules, indent=4)

    async def get_screenshot(self):
        user_timetable_url = f"http://timetable.itcarlow.ie/reporting/individual;student+set;id;{self.timetable_id}?t=student+set+individual&days=1-5&weeks=&periods=5-40&template=student+set+individual"
        browser = await launch(
            headless=True, handleSIGINT=False, handleSIGTERM=False, handleSIGHUP=False
        )
        page = await browser.newPage()
        await page.goto(user_timetable_url)
        timetable_screen = await page.screenshot({"fullPage": True})
        await browser.close()
        self.SCREENSHOT = BytesIO(timetable_screen)

    async def create_default(self):
        if not self.created:
            self.created = True
            await self.get_json()
            await self.get_screenshot()

    async def get_previous_timetable_diff(self, channel: discord.TextChannel):
        messages = [message async for message in channel.history(limit=15)]
        for message in messages:
            if (
                message.author == self.client.user
                and len(message.attachments) > 0
                and message.attachments[0].filename.endswith(".json")
            ):
                try:
                    timetable_bytes = BytesIO()
                    await message.attachments[0].save(timetable_bytes)
                    wrapper = TextIOWrapper(timetable_bytes, encoding="utf-8")
                    previous_timetable_string = wrapper.read()
                    validate(
                        instance=json.loads(previous_timetable_string),
                        schema=timetable_info_schema,
                    )
                    return _unidiff_output(
                        previous_timetable_string, self.JSON_STRING
                    )
                except jsonschema.ValidationError:
                    pass
                except ValueError:
                    pass
                break
        return ""

    async def add_channel(self, channel: discord.TextChannel):
        self.channels.append(channel)

    async def clear(self):
        self.created = False
        self.JSON_STRING = ""
        self.SCREENSHOT = False