# Twitch Chat Joiner

Made to bot services like StreamElements, which give you points for staying in chat.

If you're looking for a program to bot Twitch's in-built points system, I recommend you use [Tkd-Alex's Twitch Channel Points Miner](https://github.com/Tkd-Alex/Twitch-Channel-Points-Miner-v2).

### Requirements
- Python3.8
- `aiohttp` (Async Request Library), `bottom` (Async IRC Library), `rich` (Pretty Printing)

### Installation
- `git clone https://github.com/TheOnlyWayUp/Twitch-Chat-Joiner twitch_chat_joiner`
- `cd twitch_chat_joiner`
- `python3.8 -m pip install -r requirements.txt`
- `python3.8 async_twitch.py`

### Configuration
```json
{
    "bot_username": "",
    "client_id": "",
    "client_secret": "",
    "oauth_token": "",
    "channels": [],
    "wait_time": 0
}
```
- `bot_username`: Your account username
- `client_id`: Your Client ID (Create an application [here](https://dev.twitch.tv/docs/authentication/register-app) to get the client id & client secret)
- `client_secret`: Your Client Secret (From the application you just made)
- `oauth_token`: OAuth Token to access IRC (You can get it [here](https://twitchapps.com/tmi/))
- `channels`: List of Twitch Streamer names whose chats the bot should join
- `wait_time`: How often the bot should check if streamers are online/offline and join their chats (in seconds)

TheOnlyWayUp#1231