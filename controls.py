"""
✘ Commands Available -

• `{i}joinvc <optional chat id/username>`
   Join the voice chat.

• `{i}leavevc`
   Leave the voice chat.

• `{i}rejoin`
   Re-join the voice chat, incase of errors.

• `{i}volume <number>`
   Put number between 1 to 100

• `{i}skip`
   Skip the current song and play the next in queue, if any.
"""

from pytgcalls.exceptions import NotInCallError

from . import vc_asst, Player, get_string, CLIENTS, VIDEO_ON


@vc_asst("joinvc")
async def join_(event):
    if len(event.text.split()) > 1:
        chat = event.text.split()[1]
        try:
            chat = await event.client.parse_id(chat)
        except Exception as e:
            return await event.eor(get_string("vcbot_2").format(str(e)))
    else:
        chat = event.chat_id
    ultSongs = Player(chat, event)
    if not await ultSongs.is_connected():
        await ultSongs.vc_joiner()


@vc_asst("(leavevc|stopvc)")
async def leaver(event):
    if len(event.text.split()) > 1:
        chat = event.text.split()[1]
        try:
            chat = await event.client.parse_id(chat)
        except Exception as e:
            return await event.eor(get_string("vcbot_2").format(str(e)))
    else:
        chat = event.chat_id
    ultSongs = Player(chat)
    await ultSongs.stop()
    CLIENTS.pop(chat, None)
    VIDEO_ON.pop(chat, None)
    await event.eor(get_string("vcbot_1"))


@vc_asst("rejoin")
async def rejoiner(event):
    if len(event.text.split()) > 1:
        chat = event.text.split()[1]
        try:
            chat = await event.client.parse_id(chat)
        except Exception as e:
            return await event.eor(get_string("vcbot_2").format(str(e)))
    else:
        chat = event.chat_id
    ultSongs = Player(chat)
    try:
        await ultSongs.reconnect()
    except NotInCallError:
        return await event.eor(get_string("vcbot_6"))
    await event.eor(get_string("vcbot_5"))


@vc_asst("volume")
async def volume_setter(event):
    if len(event.text.split()) <= 1:
        return await event.eor(get_string("vcbot_4"))
    inp = event.text.split()
    vol = None
    if inp[1].startswith(("@", "-")):
        chat = inp[1]
        vol = int(inp[2])
        try:
            chat = await event.client.parse_id(chat)
        except Exception as e:
            return await event.eor(get_string("vcbot_2").format(str(e)))
    elif inp[1].isdigit() and len(inp) == 2:
        vol = int(inp[1])
        chat = event.chat_id
    else:
        return await event.eor(get_string("vcbot_4"))
    if vol is None:
        return await event.eor(get_string("vcbot_4"))
    vol = max(1, min(200, vol))
    ultSongs = Player(chat)
    await ultSongs.set_my_volume(vol)
    return await event.eor(get_string("vcbot_3").format(vol))


@vc_asst("skip")
async def skipper(event):
    if len(event.text.split()) > 1:
        chat = event.text.split()[1]
        try:
            chat = await event.client.parse_id(chat)
        except Exception as e:
            return await event.eor(f"**ERROR:**\n{str(e)}")
    else:
        chat = event.chat_id
    ultSongs = Player(chat, event)
    await ultSongs.play_from_queue()
