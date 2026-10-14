# VcBot

Telegram group voice/video chat player for [Megatron](https://github.com/ToxygenX/Megatron).

## Stack

- **[NTgCalls](https://pypi.org/project/ntgcalls/)** — native WebRTC / media engine
- **[py-tgcalls](https://pypi.org/project/py-tgcalls/)** — async MTProto bridge (`import pytgcalls`)
- **[ToxygenX/Telethon](https://github.com/ToxygenX/Telethon)** — Telegram MTProto client (via Megatron `vcClient`; Lonami v1 + Python 3.14 event-loop fix)

This replaces the legacy `pytgcalls==3.0.0.dev24` (`GroupCallFactory`) stack, which is unmaintained and incompatible with Python 3.14.

## Requirements (installed by Megatron)

```
ntgcalls>=3.0.0
py-tgcalls>=3.0.0
git+https://github.com/ToxygenX/Telethon.git@35290bc24af401e9c1331d71b7e0ff3ff0a10429
```

Python **3.10–3.14** supported when Megatron installs the pins above.

## Commands

Loaded only when `VCBOT` is enabled. See `.vchelp` / inline help for the full list (`.play`, `.videoplay`, `.joinvc`, `.leavevc`, queue, mute/pause, etc.).
