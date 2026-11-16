# SUBTITLER

[🇷🇺 Русская версия](README.ru.md)

**Version:** 0.5.0 | **Date:** 17.11.2026

Subtitler is a cloud service for automatic transcription of audio and video into subtitles (SRT/VTT/TXT). Subtitles are created directly inside the Adobe After Effects workspace. The script automatically creates text layers and markers on the timeline.

The service supports transcription in 90+ languages and subtitle translation via Argos Translate.

Two deployment options are available: cloud-based (via API) or local. The service is free of charge and has no mandatory payments.

## 🚀 Quick Start

### Cloud Mode
1. Register at [subtitler.qzz.io](https://subtitler.qzz.io)
2. Download the `Subtitler.jsx` script. Copy the script into AE (`Adobe After Effects 20xx\Support Files\Scripts\ScriptUI Panels`).
3. In the plugin settings, enter the API key from your account dashboard.
4. In AE, select the desired file → start transcription.

### Local Mode
1. Download the `Worker_local_v2` files.
2. Run `Subtitler_Local.bat` (Windows) or `subtitler_local.sh` (macOS/Linux).
3. Follow the installation wizard (automatic installation of PyTorch, WhisperX, and models).
4. In the plugin settings, under the API field, specify: `Server URL = http://localhost:8765`.
5. In AE, select the desired file → start transcription.

## 📁 Supported Formats

**Input:** MP4, MOV, AVI, MKV, MP3, WAV, M4A, FLAC, OGG, and others (up to 500 MB).
**Output:** SRT, VTT, TXT.

### Subtitle Formats:
* **Standard** — standard phrases (2-7 sec)
* **Short** — short lines (1-3 sec)
* **Word** — each word separately