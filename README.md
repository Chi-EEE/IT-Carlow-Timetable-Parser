# IT Carlow Timetable Parser

Discord bot that can upload the json file of the timetable, screenshot of the timetable, and the differences between the previous timetable and the current timetable.

## Getting Started

These instructions will guide you how to set up and run the program.

### Prerequisites

Requirements for the software

- [Python](https://www.python.org/downloads/)

### Installing

To get the development environment running, you'll have to enter the directory and run the cmd in Command Prompt:

```
pip install -r requirements.txt
```

Afterwards you create a .env file with the following:

**.env**
```
TOKEN=(OAuth token from discord bot)
HASH=(Secret string to prevent users from editing channel topic) 
```

Lastly, you run the bot.py script:
```
py src\bot.py
```
Result in the Command Prompt:
```
INFO     discord.client logging in using static token
INFO     discord.gateway Shard ID None has connected to Gateway (Session ID: ...).
We have logged in as abcd#1234
```

## Built With

  - [Creative Commons](https://creativecommons.org/) - Used to choose
    the license

## Authors

  - **Chi Huu Huynh** - *Created the IT Carlow Timetable Parser Bot* -
    [HuuChiHuynh](https://github.com/HuuChiHuynh)
  - **Billie Thompson** - *Provided README Template* -
    [PurpleBooth](https://github.com/PurpleBooth)

## License

This project is licensed under the [MIT License](LICENSE)
MIT License - see the [LICENSE](LICENSE) file for
details
