"""Package to join a twitch streamer's chat and earn streamelements points."""

import json, aiohttp, bottom, asyncio, signal
from typing import Optional, List
from rich.console import Console
from pathlib import Path
from collections import ChainMap

"""
References
- https://dev.twitch.tv/docs/irc
- https://github.com/numberoverzero/bottom

- https://bottom-docs.readthedocs.io (Functions keepalive, handle_sigint and handle are directly copied from here.
- https://github.com/jschlenker/twitch-multistream-chat (Tried using this, but it became impractical to keep modifying it to stop breaking/suit my needs. I wrote this program as a kind of 'rewrite', taking reference from `twitch-multistream-chat`)
"""

# --- Constants --- #

config_path = Path(__file__).parent / "config.json"
console = Console()

with open(config_path, "r") as handler:
    config = json.load(handler)
    console.log("[cyan][LOG][/cyan] - Config Loaded, {}".format(config))
STREAMER_LISTS = {"joined": set(), "offline": set(config.get("channels"))}

# --- Validate Config --- #


def validate_config():
    """Makes sure all the required keys are in the configuration file."""

    required_keys = {
        "bot_username": str,
        "client_id": str,
        "client_secret": str,
        "oauth_token": str,
        "channels": list,
        "wait_time": int,
        "verbose": bool
    }

    # Key Presence Validation
    not_present_keys = [k for k in required_keys if k not in config]
    errors = []
    for key in not_present_keys:
        console.log(
            "[red][ERROR][/red] Key `{}` not present in configuration file ({}), please verify.".format(
                key, config_path.absolute()
            )
        )
        errors.append(KeyError(key))

    if len(not_present_keys) != 0:
        raise Exception(errors)

    # Value Validation
    not_present_values = [(k, v) for k, v in config.items() if not v and type(v) is not bool]
    errors = []
    for key, value in not_present_values:
        console.log(
            "[red][ERROR][/red] Key `{}` has no value (`{}`). Value should also be of type `{}`. Configuration File - {}".format(
                key, value, required_keys.get(key), config_path.absolute()
            )
        )
        errors.append(TypeError(key))

    if len(not_present_values) != 0:
        raise Exception(errors)

    # Value Type Validation
    bad_type_values = [
        (k, v) for k, v in config.items() if required_keys.get(k) is not type(v)
    ]
    errors = []
    for key, value in bad_type_values:
        console.log(
            "[red][ERROR][/red] Key `{}`'s value (`{}`) is of type `{}` when it should be of type `{}`.\nConfiguration File - {}".format(
                key,
                value,
                type(value),
                type(required_keys.get(key)),
                config_path.absolute(),
            )
        )
        errors.append(TypeError(key))

    if len(bad_type_values) != 0:
        raise Exception(errors)

    # --- #
    return True


validate_config()

# --- Events --- #

bot = bottom.Client(host="irc.chat.twitch.tv", port=6697, ssl=True)


@bot.on("CLIENT_CONNECT")
async def connect(**kwargs):
    oauth_token = config["oauth_token"]
    oauth_token = (
        "oauth:" + oauth_token if not oauth_token.startswith("oauth:") else oauth_token
    )
    bot_username = config["bot_username"]

    bot.send("PASS", password=oauth_token)
    bot.send("NICK", nick=bot_username)
    bot.send_raw("CAP REQ :twitch.tv/membership")

    console.rule("Logged In")


@bot.on("CLIENT_DISCONNECT")
async def reconnect(**kwargs):
    # Wait a second so we don't flood
    await asyncio.sleep(2, loop=bot.loop)  # type: ignore

    # Wait until we've reconnected
    await bot.connect()


@bot.on("PING")
def keepalive(message, **kwargs):
    bot.send("PONG", message=message)


def handle_sigint(signum, frame):
    console.log("[green][EXIT][/green] - CTRL+C Recieved, cleaning up.")
    asyncio.create_task(handle())


signal.signal(signal.SIGINT, handle_sigint)


async def handle(**kwargs):
    console.log("[cyan][LOG][/cyan] - Stopping")
    try:
        await asyncio.wait_for(bot.disconnect(), timeout=5)
    except asyncio.TimeoutError:
        console.log("[yellow][WARNING][/yellow] Disconnect timed out")

    # Signal a stop before disconnecting so that any reconnect
    # coros aren't run by the last run_forever sweep.

    async def stop():
        bot.loop.stop()

    try:
        await asyncio.wait_for(stop(), timeout=5)
    except asyncio.TimeoutError:
        console.log("[yellow][WARNING][/yellow] Stopping the loop timed out")
        bot.loop.stop()
        exit()

    exit()


# --- Helper Functions --- #


async def retrieve_access_token(
    client_id: str, client_secret: str, _session: Optional[aiohttp.ClientSession] = None
):
    """Retrieves the access token by sending a client credentials request to twitch."""

    body = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
    }

    session = _session or aiohttp.ClientSession()

    async with session.post("https://id.twitch.tv/oauth2/token", json=body) as response:
        response_data = await response.json()

        if response.status == 500:
            console.log(
                "[red][ERROR]/[red] Failed to fetch access token.\nResponse: {}\nJSON: {}\nBody: {}".format(
                    response, response_data, body
                )
            )
            raise Exception("Failed to fetch access token.")

        elif not str(response.status).startswith(
            "2"
        ):  # Status Code doesn't start with two
            console.log(
                "[yellow][WARNING][/yellow] Status Code for access token fetch is not in the 200 Range.\nResponse: {}\nJSON: {}\nBody: {}".format(
                    response, response_data, body
                )
            )

    access_token = response_data.get("access_token")
    if access_token is None:
        console.log(
            "[red][ERROR][/red] Access token is not present in response, please check logs.\nJSON: {}\nBody: {}".format(
                response_data, body
            )
        )
        raise KeyError("access_token")

    if (
        not session == _session
    ):  # When the program creates its own session (with the or statement), this condition will be True
        await session.close()

    return access_token


async def retrieve_streaming_status(
    client_id: str,
    access_token: str,
    streamer_name: str,
    _session: Optional[aiohttp.ClientSession] = None,
):
    """Retrieves streamer status, ie, whether they're streaming or not at the moment."""

    headers = {"Client-ID": client_id, "Authorization": "Bearer " + access_token}
    session = _session or aiohttp.ClientSession()

    async with session.get(
        "https://api.twitch.tv/helix/streams?user_login={}".format(streamer_name),
        headers=headers,
    ) as response:
        response_data = await response.json()

        if type(response_data.get("data")) is not list:
            # something went wrong with the request

            console.log(
                "[red][ERROR][/red] Access token is not present in response, please check logs.\nJSON: {}\nHeaders: {}".format(
                    response_data, headers
                )
            )
            raise KeyError("data")

    return {streamer_name: len(response_data["data"]) == 1}


async def prepare_socket():
    """Prepares socket with authentication and returns it"""

    done, pending = await asyncio.wait(
        [bot.wait("RPL_ENDOFMOTD"), bot.wait("ERR_NOMOTD")],
        loop=bot.loop,
        return_when=asyncio.FIRST_COMPLETED,
    )  # type: ignore

    # Cancel whichever waiter's event didn't come in.
    for future in pending:
        future.cancel()

    return bot


async def get_alive_streamers(
    streamers: List[str], _session: Optional[aiohttp.ClientSession] = None
):
    """Gets all alive streamers"""

    access_token = await retrieve_access_token(
        config["client_id"], config["client_secret"], _session=_session
    )
    config["access_token"] = access_token

    data = await asyncio.gather(
        *[
            retrieve_streaming_status(
                config["client_id"],
                access_token=access_token,
                streamer_name=streamer,
                _session=_session,
            )
            for streamer in streamers
        ]
    )

    result = [
        k for k, v in dict(ChainMap(*data)).items() if v is True
    ]  # A list of all the streamers whose values are True, ie, a list of channels that are streaming

    return result


async def join_channels(channels: List[str], bot: bottom.Client):
    """Joins channels"""

    for channel in channels:
        bot.send("JOIN", channel="#{}".format(channel))
        console.log("[cyan][JOIN][/cyan] - Joined channel {}".format(channel))

    return True


async def leave_channels(channels: List[str], bot: bottom.Client):
    """Leaves channels"""

    for channel in channels:
        bot.send("PART", channel="#{}".format(channel))
        console.log("[cyan][LEAVE][/cyan] - Left channel {}".format(channel))

    return True

if config.get("verbose", False):
    all_events = [
        "PING",
        "JOIN",
        "PART",
        "PRIVMSG",
        "NOTICE",
        "USERMODE",
        "CHANNELMODE",
        "RPL_WELCOME",
        "RPL_YOURHOST",
        "RPL_CREATED",
        "RPL_MYINFO",
        "RPL_BOUNCE",
        "RPL_MOTDSTART",
        "RPL_MOTD",
        "RPL_ENDOFMOTD",
        "RPL_LUSERCLIENT",
        "RPL_LUSERME",
        "RPL_LUSEROP",
        "RPL_LUSERUNKNOWN",
        "RPL_LUSERCHANNELS",
        "ERR_NOMOTD",
    ]

    def event_handler(event_name: str, bot: bottom.Client):

        @bot.on(event_name)
        async def log(**kwargs):
            console.log("{} - {}".format(event_name, kwargs))
        
        return log

    [event_handler(event, bot) for event in all_events]


# --- Main --- #


async def main():
    """Main Loop"""

    session = aiohttp.ClientSession()
    bot = await prepare_socket()

    console.log("[cyan][LOG][/cyan] - Socket Prepared")

    while True:
        console.rule("Beginning Loop")

        # Alive Streamers are retrieved through the API, that's compared with the currently alive streamers to see the difference, ie, who's new and who's gone offline, then leave/join according channels, then update the config for the next loop

        currently_alive_streamers = set(
            await get_alive_streamers(config["channels"], _session=session)
        )
        console.log(config)
        console.log(
            "[cyan][LOG][/cyan] - Alive Streamers Retrieved, {}".format(
                currently_alive_streamers
            )
        )

        previous_alive_streamers: set = STREAMER_LISTS.get("joined", set())
        now_offline_streamers = previous_alive_streamers.difference(
            currently_alive_streamers
        )
        console.log(
            "[cyan][LOG][/cyan] - Offline Streamers Retrieved, {}".format(
                now_offline_streamers
            )
        )
        to_join_streamers = currently_alive_streamers.difference(
            STREAMER_LISTS.get("joined", set())
        )

        STREAMER_LISTS["joined"] = currently_alive_streamers
        STREAMER_LISTS["offline"] = now_offline_streamers

        await leave_channels(list(now_offline_streamers), bot=bot)
        await join_channels(list(to_join_streamers), bot=bot)

        console.rule("Sleeping")

        await asyncio.sleep(int(config["wait_time"]))


# --- Running --- #

bot.loop.create_task(bot.connect())
bot.loop.create_task(main())
bot.loop.run_forever()  # Ctrl + C here
