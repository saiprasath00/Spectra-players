# SPECTRA — Hi-Res Audio Laboratory

A high-resolu tion audio player for Android built with Kotlin + Jetpack Compose + ExoPlayer (Media3).

---

## Features

- **Real local file playback** via ExoPlayer (Media3) with background service
- **Automatic library scanning** — reads all audio from device storage
- **Metadata extraction** — sample rate, bit depth, format per file
- **Hi-res detection** — badges for FLAC, WAV, ALAC, DSD, MP3 etc.
- **Background playback** with media notification + lock screen controls
- **Album art** from MediaStore
- **Search** across tracks, artists, albums
- **Album / Artist / Track** browse modes
- **Bit-perfect mode toggle**, USB DAC status display
- **DAC dashboard** with sample rate, bit depth, format readout
- **Animated VU meters** (L/R, Dynamic Range)
- **Settings** for ReplayGain, crossfeed, gapless, buffer size, etc.
- **Dark laboratory aesthetic** — monospace fonts, scan-line texture, oscilloscope palette

---

## Setup in Android Studio

1. **Open** Android Studio (Hedgehog or newer recommended).
2. Choose **"Open"** and select the `SpectraPlayer/` folder.
3. Wait for Gradle sync to finish (downloads ~150MB of dependencies first time).
4. **Run** on a physical device (API 26+) or emulator for best results.

> Audio scanning requires a real device with music files. The emulator has no music library.

---

## Permissions

| Permission | Reason |
|---|---|
| `READ_MEDIA_AUDIO` (API 33+) | Scan device music files |
| `READ_EXTERNAL_STORAGE` (API <33) | Scan device music files |
| `FOREGROUND_SERVICE` | Background playback |
| `WAKE_LOCK` | Keep CPU alive during playback |

---

## Architecture

```
MainActivity
  └── SpectraApp (Compose navigation)
        ├── PlayerScreen       ← Now Playing
        ├── LibraryScreen      ← Albums / Artists / Tracks
        └── SettingsScreen     ← Audio engine config

MainViewModel
  ├── MusicRepository          ← DB + MediaScanner
  │     ├── SpectraDatabase    ← Room (SQLite)
  │     └── MediaScanner       ← MediaStore + MediaMetadataRetriever
  └── PlayerController         ← ExoPlayer via MediaController

PlaybackService (MediaSessionService)
  └── ExoPlayer                ← actual audio engine
```

---

## Adding USB DAC Support (Future)

The manifest already has `android.hardware.usb.host`. To add real USB audio:

1. Add `UsbManager` service in `PlaybackService`
2. Read USB device descriptors to detect DAC
3. Open `UsbDeviceConnection` and configure isochronous transfer
4. Write PCM samples directly to USB endpoint

This bypasses Android's audio mixer entirely for true bit-perfect output.
For consumer use, ExoPlayer's `AudioTrack` with `ENCODING_PCM_FLOAT` is the practical path.

---

## File Format Support

| Format | Supported | Hi-Res |
|---|---|---|
| FLAC | ✅ | ✅ up to 32-bit/384kHz |
| WAV | ✅ | ✅ |
| ALAC (M4A) | ✅ | ✅ |
| MP3 | ✅ | ❌ |
| AAC | ✅ | ❌ |
| OGG Vorbis | ✅ | ❌ |
| DSD | ⚠️ Device-dependent | ✅ |

---

## Dependencies

- **ExoPlayer / Media3 1.4** — playback engine
- **Room 2.6** — local track database
- **Coil 2.6** — album art loading
- **Jetpack Compose BOM 2024.06** — UI
- **Material3** — component library
- **Kotlin Coroutines** — async operations
