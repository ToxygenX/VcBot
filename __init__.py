"""
CɪᴘʜᴇʀX VCBot — Telegram voice/video chat powered by NTgCalls.

Uses py-tgcalls (MTProto bridge) with ntgcalls (native WebRTC engine).
Compatible with Python 3.10+ including 3.14.
"""

import asyncio
import os
import traceback
from time import time
from traceback import format_exc

from telethon.errors.rpcerrorlist import ChatSendMediaForbiddenError
from telethon import events
from telethon.tl import functions

from pytgcalls import PyTgCalls
from pytgcalls import filters as call_filters
from pytgcalls.exceptions import (
    NoActiveGroupCall,
    NotInCallError,
)
from pytgcalls.types import (
    AudioQuality,
    ChatUpdate,
    Device,
    GroupCallConfig,
    MediaStream,
    StreamEnded,
    VideoQuality,
)

from CythonX import HNDLR, LOGS, asst, udB, vcClient
from CythonX._misc._decorators import compile_pattern
from CythonX.fns.helper import (
    bash,
    downloader,
    inline_mention,
    mediainfo,
    time_formatter,
)
from CythonX.fns.admins import admin_check
from CythonX.fns.tools import is_url_ok
from CythonX.fns.ytdl import get_videos_link
from CythonX._misc import owner_and_sudos, sudoers
from CythonX._misc._assistant import in_pattern
from CythonX._misc._wrappers import eod, eor
from CythonX.version import __version__ as UltVer

try:
    from yt_dlp import YoutubeDL
except ImportError:
    YoutubeDL = None
    LOGS.error("'yt-dlp' not found!")

try:
    from youtubesearchpython import VideosSearch
except ImportError:
    VideosSearch = None

from strings import get_string

asstUserName = asst.me.username
LOG_CHANNEL = udB.get_key("LOG_CHANNEL")
ACTIVE_CALLS, VC_QUEUE = [], {}
MSGID_CACHE, VIDEO_ON = {}, {}
# chat_id -> last played MediaStream source (path/url) + video flag
CURRENT_SOURCE = {}
CLIENTS = {}  # kept for compatibility; maps chat -> Player meta
# Suppress stream-end while replacing media (skip / replay / new play).
_IGNORE_STREAM_END = set()

_calls: PyTgCalls | None = None
_calls_lock = asyncio.Lock()
_handlers_ready = False


def VC_AUTHS():
    _vcsudos = udB.get_key("VC_SUDOS") or []
    return [int(a) for a in [*owner_and_sudos(), *_vcsudos]]


def _audio_stream(source: str) -> MediaStream:
    return MediaStream(
        source,
        audio_parameters=AudioQuality.HIGH,
        video_flags=MediaStream.Flags.IGNORE,
    )


def _video_stream(source: str) -> MediaStream:
    return MediaStream(
        source,
        audio_parameters=AudioQuality.HIGH,
        video_parameters=VideoQuality.HD_720p,
        audio_flags=MediaStream.Flags.REQUIRED,
        video_flags=MediaStream.Flags.AUTO_DETECT,
    )


async def get_calls() -> PyTgCalls:
    """Lazy-init a single NTgCalls-backed PyTgCalls client on vcClient."""
    global _calls, _handlers_ready
    async with _calls_lock:
        if _calls is None:
            _calls = PyTgCalls(vcClient)
            await _calls.start()
            LOGS.info("VCBot: NTgCalls / PyTgCalls client started.")
        if not _handlers_ready:
            @_calls.on_update(call_filters.stream_end())
            async def _on_stream_end(_, update: StreamEnded):
                # Advance queue once per track (audio capture end).
                if update.device != Device.MICROPHONE:
                    return
                chat_id = update.chat_id
                source = CURRENT_SOURCE.pop(chat_id, None)
                if source and isinstance(source.get("path"), str):
                    path = source["path"]
                    if os.path.exists(path) and path.startswith("vcbot/"):
                        try:
                            os.remove(path)
                        except OSError:
                            pass
                try:
                    await Player(chat_id).play_from_queue()
                except Exception:
                    LOGS.exception("VCBot stream-end handler failed")

            @_calls.on_update(
                call_filters.chat_update(ChatUpdate.Status.LEFT_CALL)
            )
            async def _on_chat_update(_, update: ChatUpdate):
                chat_id = update.chat_id
                if chat_id in ACTIVE_CALLS:
                    ACTIVE_CALLS.remove(chat_id)
                CURRENT_SOURCE.pop(chat_id, None)
                VIDEO_ON.pop(chat_id, None)
                CLIENTS.pop(chat_id, None)

            _handlers_ready = True
        return _calls


class Player:
    """High-level voice-chat controller for a single chat."""

    def __init__(self, chat, event=None, video=False):
        self._chat = int(chat)
        self._current_chat = event.chat_id if event else LOG_CHANNEL
        self._video = video
        CLIENTS[self._chat] = self

    @property
    def group_call(self):
        """Back-compat alias so older call sites can still reference Player."""
        return self

    async def calls(self) -> PyTgCalls:
        return await get_calls()

    async def is_connected(self) -> bool:
        call = await self.calls()
        try:
            active = await call.group_calls
            return self._chat in active
        except Exception:
            return self._chat in ACTIVE_CALLS

    async def make_vc_active(self):
        try:
            await vcClient(
                functions.phone.CreateGroupCallRequest(
                    self._chat, title="🎧 CɪᴘʜᴇʀX ᴇxᴄlusivᴇ ʙᴏᴛ Music 🎶"
                )
            )
        except Exception as e:
            LOGS.exception(e)
            return False, e
        return True, None

    async def startCall(self):
        """Join the group call (auto-starts VC if needed)."""
        call = await self.calls()
        if self._video:
            # Keep one video session at a time for stability.
            for chat_id in list(VIDEO_ON):
                if chat_id != self._chat:
                    try:
                        await call.leave_call(chat_id)
                    except (NotInCallError, Exception):
                        pass
                    VIDEO_ON.pop(chat_id, None)
            VIDEO_ON[self._chat] = True

        if self._chat not in ACTIVE_CALLS:
            try:
                await call.play(
                    self._chat,
                    None,
                    GroupCallConfig(auto_start=True),
                )
            except NoActiveGroupCall:
                dn, err = await self.make_vc_active()
                if err:
                    return False, err
                try:
                    await call.play(
                        self._chat,
                        None,
                        GroupCallConfig(auto_start=True),
                    )
                except Exception as e:
                    LOGS.exception(e)
                    return False, e
            except Exception as e:
                LOGS.exception(e)
                return False, e
            if self._chat not in ACTIVE_CALLS:
                ACTIVE_CALLS.append(self._chat)
        return True, None

    async def play_media(self, source: str, video: bool | None = None):
        """Play audio or video into the active call via NTgCalls."""
        is_video = self._video if video is None else video
        call = await self.calls()
        stream = _video_stream(source) if is_video else _audio_stream(source)
        CURRENT_SOURCE[self._chat] = {"path": source, "video": is_video}
        if is_video:
            VIDEO_ON[self._chat] = True
        elif self._chat in VIDEO_ON:
            VIDEO_ON.pop(self._chat, None)

        try:
            await call.play(
                self._chat,
                stream,
                GroupCallConfig(auto_start=True),
            )
        except NoActiveGroupCall:
            dn, err = await self.make_vc_active()
            if err:
                raise err
            await call.play(
                self._chat,
                stream,
                GroupCallConfig(auto_start=True),
            )
        if self._chat not in ACTIVE_CALLS:
            ACTIVE_CALLS.append(self._chat)

    # ---- back-compat method names used across plugins ----

    async def start_audio(self, source: str):
        await self.play_media(source, video=False)

    async def start_video(self, source: str, with_audio: bool = True):
        await self.play_media(source, video=True)

    async def stop(self):
        call = await self.calls()
        try:
            await call.leave_call(self._chat)
        except (NotInCallError, NoActiveGroupCall):
            pass
        except Exception as e:
            LOGS.exception(e)
        if self._chat in ACTIVE_CALLS:
            ACTIVE_CALLS.remove(self._chat)
        CURRENT_SOURCE.pop(self._chat, None)
        VIDEO_ON.pop(self._chat, None)
        CLIENTS.pop(self._chat, None)

    async def leave_call(self):
        await self.stop()

    async def reconnect(self):
        meta = CURRENT_SOURCE.get(self._chat)
        try:
            await self.stop()
        except Exception:
            pass
        await asyncio.sleep(1)
        ok, err = await self.startCall()
        if not ok:
            if isinstance(err, Exception):
                raise NotInCallError() from err
            raise NotInCallError()
        if meta and meta.get("path"):
            await self.play_media(meta["path"], video=bool(meta.get("video")))

    async def set_my_volume(self, vol: int):
        vol = max(1, min(200, int(vol)))
        call = await self.calls()
        await call.change_volume_call(self._chat, vol)

    async def set_is_mute(self, mute: bool):
        call = await self.calls()
        if mute:
            await call.mute(self._chat)
        else:
            await call.unmute(self._chat)

    async def set_pause(self, paused: bool):
        call = await self.calls()
        if paused:
            await call.pause(self._chat)
        else:
            await call.resume(self._chat)

    async def restart_playout(self):
        meta = CURRENT_SOURCE.get(self._chat)
        if not meta or not meta.get("path"):
            raise NotInCallError()
        await self.play_media(meta["path"], video=bool(meta.get("video")))

    async def stop_video(self):
        if self._chat in VIDEO_ON:
            VIDEO_ON.pop(self._chat, None)
        # Switch to idle join (no camera) if still in call.
        if await self.is_connected():
            call = await self.calls()
            try:
                await call.play(self._chat, None, GroupCallConfig(auto_start=False))
            except Exception:
                pass

    async def play_from_queue(self):
        chat_id = self._chat
        if chat_id in VIDEO_ON:
            await self.stop_video()
        try:
            song, title, link, thumb, from_user, pos, dur = await get_from_queue(
                chat_id
            )
            try:
                await self.start_audio(song)
            except NotInCallError:
                await self.vc_joiner()
                await self.start_audio(song)
            if MSGID_CACHE.get(chat_id):
                try:
                    await MSGID_CACHE[chat_id].delete()
                except Exception:
                    pass
                del MSGID_CACHE[chat_id]
            text = (
                f"<strong>🎧 Now playing #{pos}: <a href={link}>{title}</a>\n"
                f"⏰ Duration:</strong> <code>{dur}</code>\n"
                f"👤 <strong>Requested by:</strong> {from_user}"
            )
            try:
                xx = await vcClient.send_message(
                    self._current_chat,
                    text,
                    file=thumb,
                    link_preview=False,
                    parse_mode="html",
                )
            except ChatSendMediaForbiddenError:
                xx = await vcClient.send_message(
                    self._current_chat, text, link_preview=False, parse_mode="html"
                )
            MSGID_CACHE.update({chat_id: xx})
            VC_QUEUE[chat_id].pop(pos)
            if not VC_QUEUE[chat_id]:
                VC_QUEUE.pop(chat_id)

        except (IndexError, KeyError):
            await self.stop()
            await vcClient.send_message(
                self._current_chat,
                f"• Successfully Left Vc : <code>{chat_id}</code> •",
                parse_mode="html",
            )
        except Exception as er:
            LOGS.exception(er)
            await vcClient.send_message(
                self._current_chat,
                f"<strong>ERROR:</strong> <code>{format_exc()}</code>",
                parse_mode="html",
            )

    async def vc_joiner(self):
        chat_id = self._chat
        done, err = await self.startCall()

        if done:
            await vcClient.send_message(
                self._current_chat,
                f"• Joined VC in <code>{chat_id}</code>",
                parse_mode="html",
            )
            return True
        await vcClient.send_message(
            self._current_chat,
            f"<strong>ERROR while Joining Vc -</strong> <code>{chat_id}</code> :\n<code>{err}</code>",
            parse_mode="html",
        )
        return False


# --------------------------------------------------


def vc_asst(dec, **kwargs):
    def ult(func):
        kwargs["func"] = (
            lambda e: not e.is_private and not e.via_bot_id and not e.fwd_from
        )
        handler = udB.get_key("VC_HNDLR") or HNDLR
        kwargs["pattern"] = compile_pattern(dec, handler)
        vc_auth = kwargs.get("vc_auth", True)
        key = udB.get_key("VC_AUTH_GROUPS") or {}
        if "vc_auth" in kwargs:
            del kwargs["vc_auth"]

        async def vc_handler(e):
            VCAUTH = list(key.keys())
            if not (
                (e.out)
                or (e.sender_id in VC_AUTHS())
                or (vc_auth and e.chat_id in VCAUTH)
            ):
                return
            elif vc_auth and key.get(e.chat_id):
                cha, adm = key.get(e.chat_id), key[e.chat_id]["admins"]
                if adm and not (await admin_check(e)):
                    return
            try:
                await func(e)
            except Exception:
                LOGS.exception(Exception)
                await asst.send_message(
                    LOG_CHANNEL,
                    f"VC Error - <code>{UltVer}</code>\n\n<code>{e.text}</code>\n\n<code>{format_exc()}</code>",
                    parse_mode="html",
                )

        vcClient.add_event_handler(
            vc_handler,
            events.NewMessage(**kwargs),
        )

    return ult


# --------------------------------------------------


def add_to_queue(chat_id, song, song_name, link, thumb, from_user, duration):
    try:
        n = sorted(list(VC_QUEUE[chat_id].keys()))
        play_at = n[-1] + 1
    except BaseException:
        play_at = 1
    stuff = {
        play_at: {
            "song": song,
            "title": song_name,
            "link": link,
            "thumb": thumb,
            "from_user": from_user,
            "duration": duration,
        }
    }
    if VC_QUEUE.get(chat_id):
        VC_QUEUE[int(chat_id)].update(stuff)
    else:
        VC_QUEUE.update({chat_id: stuff})
    return VC_QUEUE[chat_id]


def list_queue(chat):
    if VC_QUEUE.get(chat):
        txt, n = "", 0
        for x in list(VC_QUEUE[chat].keys())[:18]:
            n += 1
            data = VC_QUEUE[chat][x]
            txt += f'<strong>{n}. <a href={data["link"]}>{data["title"]}</a> :</strong> <i>By: {data["from_user"]}</i>\n'
        txt += "\n\n....."
        return txt


async def get_from_queue(chat_id):
    play_this = list(VC_QUEUE[int(chat_id)].keys())[0]
    info = VC_QUEUE[int(chat_id)][play_this]
    song = info.get("song")
    title = info["title"]
    link = info["link"]
    thumb = info["thumb"]
    from_user = info["from_user"]
    duration = info["duration"]
    if not song:
        song = await get_stream_link(link)
    return song, title, link, thumb, from_user, play_this, duration


# --------------------------------------------------


async def download(query):
    if query.startswith("https://") and "youtube" not in query.lower():
        thumb, duration = None, "Unknown"
        title = link = query
    else:
        search = VideosSearch(query, limit=1).result()
        data = search["result"][0]
        link = data["link"]
        title = data["title"]
        duration = data.get("duration") or "♾"
        thumb = f"https://i.ytimg.com/vi/{data['id']}/hqdefault.jpg"
    dl = await get_stream_link(link)
    return dl, thumb, title, link, duration


async def get_stream_link(ytlink):
    """
    Prefer a direct ffmpeg-friendly URL. NTgCalls/MediaStream also accepts
    YouTube links natively via yt-dlp, so we fall back to the original URL.
    """
    stream = await bash(f'yt-dlp -g -f "best[height<=?720][width<=?1280]" {ytlink}')
    url = (stream[0] or "").strip()
    if url and not url.lower().startswith("error"):
        return url.splitlines()[0]
    return ytlink


async def vid_download(query):
    search = VideosSearch(query, limit=1).result()
    data = search["result"][0]
    link = data["link"]
    video = await get_stream_link(link)
    title = data["title"]
    thumb = f"https://i.ytimg.com/vi/{data['id']}/hqdefault.jpg"
    duration = data.get("duration") or "♾"
    return video, thumb, title, link, duration


async def dl_playlist(chat, from_user, link):
    links = await get_videos_link(link)
    try:
        search = VideosSearch(links[0], limit=1).result()
        vid1 = search["result"][0]
        duration = vid1.get("duration") or "♾"
        title = vid1["title"]
        song = await get_stream_link(vid1["link"])
        thumb = f"https://i.ytimg.com/vi/{vid1['id']}/hqdefault.jpg"
        return song, thumb, title, vid1["link"], duration
    finally:
        for z in links[1:]:
            try:
                search = VideosSearch(z, limit=1).result()
                vid = search["result"][0]
                duration = vid.get("duration") or "♾"
                title = vid["title"]
                thumb = f"https://i.ytimg.com/vi/{vid['id']}/hqdefault.jpg"
                add_to_queue(chat, None, title, vid["link"], thumb, from_user, duration)
            except Exception as er:
                LOGS.exception(er)


async def file_download(event, reply, fast_download=True):
    thumb = "https://telegra.ph/file/9847d2c66379f4da3b29d.mp4"
    title = reply.file.title or reply.file.name or f"{str(time())}.mp4"
    file = reply.file.name or f"{str(time())}.mp4"
    if fast_download:
        dl = await downloader(
            f"vcbot/downloads/{file}",
            reply.media.document,
            event,
            time(),
            f"Downloading {title}...",
        )

        dl = dl.name
    else:
        dl = await reply.download_media()
    duration = (
        time_formatter(reply.file.duration * 1000) if reply.file.duration else "🤷‍♂️"
    )
    if reply.document.thumbs:
        thumb = await reply.download_media("vcbot/downloads/", thumb=-1)
    return dl, thumb, title, reply.message_link, duration


# --------------------------------------------------
