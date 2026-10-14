# VcBot

Telegram group voice/video chat player for [Megatron](https://github.com/ToxygenX/Megatron).

## Stack

- **[NTgCalls](https://pypi.org/project/ntgcalls/)** — native WebRTC / media engine
- **[py-tgcalls](https://pypi.org/project/py-tgcalls/)** — async MTProto bridge (`import pytgcalls`)
- **Telethon** — Telegram client (via Megatron `vcClient`)

This replaces the legacy `pytgcalls==3.0.0.dev24` (`GroupCallFactory`) stack, which is unmaintained and incompatible with Python 3.14.

## Requirements (installed by Megatron)

```
ntgcalls>=3.0.0
py-tgcalls>=3.0.0
```

## Commands

Loaded only when `VCBOT` is enabled. See `.vchelp` / inline help for the full list (`.play`, `.videoplay`, `.joinvc`, `.leavevc`, queue, mute/pause, etc.).
