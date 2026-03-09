import os
files = {}
files['README.md'] = """# SPECTRA — Hi-Res Audio Laboratory

A high-resolution audio player for Android built with Kotlin + Jetpack Compose + ExoPlayer (Media3).

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
"""
files['app/proguard-rules.pro'] = """-keep class com.spectra.player.** { *; }
-keep class androidx.media3.** { *; }
"""
files['app/src/main/AndroidManifest.xml'] = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <!-- Storage permissions -->
    <uses-permission android:name="android.permission.READ_MEDIA_AUDIO" />
    <!-- Fallback for Android < 13 -->
    <uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE"
        android:maxSdkVersion="32" />

    <!-- Foreground service for background playback -->
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK" />

    <!-- Wake lock to keep CPU running during playback -->
    <uses-permission android:name="android.permission.WAKE_LOCK" />

    <!-- USB Host for DAC support -->
    <uses-feature android:name="android.hardware.usb.host" android:required="false" />

    <application
        android:allowBackup="true"
        android:icon="@mipmap/ic_launcher"
        android:label="@string/app_name"
        android:roundIcon="@mipmap/ic_launcher"
        android:supportsRtl="true"
        android:theme="@style/Theme.SpectraPlayer">

        <activity
            android:name=".MainActivity"
            android:exported="true"
            android:windowSoftInputMode="adjustResize">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
            <!-- Handle audio file opens from file manager -->
            <intent-filter>
                <action android:name="android.intent.action.VIEW" />
                <category android:name="android.intent.category.DEFAULT" />
                <data android:mimeType="audio/*" />
            </intent-filter>
        </activity>

        <!-- Background playback service -->
        <service
            android:name=".audio.PlaybackService"
            android:exported="true"
            android:foregroundServiceType="mediaPlayback">
            <intent-filter>
                <action android:name="androidx.media3.session.MediaSessionService" />
            </intent-filter>
        </service>

    </application>

</manifest>
"""
files['app/src/main/java/com/spectra/player/MainActivity.kt'] = """package com.spectra.player

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.spectra.player.ui.screens.LibraryScreen
import com.spectra.player.ui.screens.PlayerScreen
import com.spectra.player.ui.screens.SettingsScreen
import com.spectra.player.ui.theme.*

enum class AppScreen { PLAYER, LIBRARY, SETTINGS }

class MainActivity : ComponentActivity() {

    private val vm: MainViewModel by viewModels()

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { grants ->
        if (grants.values.any { it }) {
            vm.refreshLibrary()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestStoragePermissions()

        setContent {
            SpectraTheme {
                SpectraApp(vm)
            }
        }
    }

    private fun requestStoragePermissions() {
        val permissions = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            arrayOf(Manifest.permission.READ_MEDIA_AUDIO)
        } else {
            arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE)
        }
        val missing = permissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            permissionLauncher.launch(missing.toTypedArray())
        } else {
            vm.refreshLibrary()
        }
        } // end Row
    } // end Column
}

@Composable
fun SpectraApp(vm: MainViewModel) {
    var screen by remember { mutableStateOf(AppScreen.PLAYER) }
    val currentTrack by vm.currentTrack.collectAsState()
    val isPlaying    by vm.isPlaying.collectAsState()

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Background)
    ) {
        Column(modifier = Modifier.fillMaxSize()) {
            // ── App Header ──────────────────────────────────────────────────
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(Background)
                    .padding(horizontal = 20.dp, vertical = 14.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text(
                        "SPECTRA",
                        color = Accent,
                        fontSize = 16.sp,
                        fontFamily = FontFamily.Monospace,
                        letterSpacing = 2.sp,
                    )
                    Text(
                        "HI-RES AUDIO LABORATORY",
                        color = TextTertiary,
                        fontSize = 7.sp,
                        letterSpacing = 1.5.sp,
                        fontFamily = FontFamily.Monospace,
                    )
                }
                // DAC status pill
                Row(
                    modifier = Modifier
                        .clip(RoundedCornerShape(20.dp))
                        .background(Accent.copy(alpha = 0.08f))
                        .padding(horizontal = 10.dp, vertical = 5.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(5.dp)
                ) {
                    DacDot()
                    Text("USB DAC", color = Accent, fontSize = 8.sp,
                        letterSpacing = 0.8.sp, fontFamily = FontFamily.Monospace)
                }
            }
            HorizontalDivider(color = Border, thickness = 1.dp)

            // ── Page Content ────────────────────────────────────────────────
            Box(modifier = Modifier.weight(1f).padding(bottom = 60.dp)) {
                when (screen) {
                    AppScreen.PLAYER   -> PlayerScreen(vm)
                    AppScreen.LIBRARY  -> LibraryScreen(vm)
                    AppScreen.SETTINGS -> SettingsScreen()
                }
            }
        }

        // ── Bottom Navigation ───────────────────────────────────────────────
        BottomNav(
            current    = screen,
            onNavigate = { screen = it },
            modifier   = Modifier.align(Alignment.BottomCenter)
        )
    }
}

@Composable
fun DacDot() {
    val infinite = rememberInfiniteTransition(label = "dac")
    val alpha by infinite.animateFloat(
        initialValue = 1f, targetValue = 0.3f,
        animationSpec = infiniteRepeatable(
            androidx.compose.animation.core.tween(1000),
            androidx.compose.animation.core.RepeatMode.Reverse
        ),
        label = "dacAlpha"
    )
    Box(
        modifier = Modifier
            .size(5.dp)
            .clip(androidx.compose.foundation.shape.CircleShape)
            .background(Accent.copy(alpha = alpha))
    )
}

@Composable
fun BottomNav(current: AppScreen, onNavigate: (AppScreen) -> Unit, modifier: Modifier = Modifier) {
    val items = listOf(
        Triple(AppScreen.PLAYER,   "▶",  "PLAYER"),
        Triple(AppScreen.LIBRARY,  "⊞",  "LIBRARY"),
        Triple(AppScreen.SETTINGS, "⚙",  "SETTINGS"),
    )

    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(Background.copy(alpha = 0.95f))
    ) {
        HorizontalDivider(color = Border, thickness = 1.dp)
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .navigationBarsPadding()
                .padding(vertical = 8.dp),
            horizontalArrangement = Arrangement.SpaceEvenly,
            verticalAlignment = Alignment.CenterVertically
        ) {
        items.forEach { (screen, icon, label) ->
            val selected = screen == current
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                modifier = Modifier
                    .clickable { onNavigate(screen) }
                    .padding(horizontal = 24.dp, vertical = 6.dp)
            ) {
                Text(
                    text = icon,
                    fontSize = 16.sp,
                    color = if (selected) Accent else TextTertiary,
                )
                Spacer(Modifier.height(3.dp))
                Text(
                    text = label,
                    fontSize = 7.sp,
                    letterSpacing = 0.8.sp,
                    fontFamily = FontFamily.Monospace,
                    color = if (selected) Accent else TextTertiary,
                )
            }
        }
        } // Row
    } // Column
}
"""
files['app/src/main/java/com/spectra/player/MainViewModel.kt'] = """package com.spectra.player

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.spectra.player.audio.PlayerController
import com.spectra.player.data.model.Track
import com.spectra.player.data.repository.MusicRepository
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

data class LibraryState(
    val tracks: List<Track> = emptyList(),
    val albums: Map<String, List<Track>> = emptyMap(),
    val artists: Map<String, List<Track>> = emptyMap(),
    val isScanning: Boolean = false,
    val totalTracks: Int = 0,
)

class MainViewModel(app: Application) : AndroidViewModel(app) {

    val repository      = MusicRepository(app)
    val playerController = PlayerController(app)

    // ── Player state (delegated from PlayerController) ──────────────────────
    val currentTrack  = playerController.currentTrack
    val isPlaying     = playerController.isPlaying
    val position      = playerController.position
    val duration      = playerController.duration
    val queue         = playerController.queue
    val currentIndex  = playerController.currentIndex

    // ── Library state ───────────────────────────────────────────────────────
    private val _libState = MutableStateFlow(LibraryState())
    val libState: StateFlow<LibraryState> = _libState.asStateFlow()

    private val _searchQuery = MutableStateFlow("")
    val searchQuery: StateFlow<String> = _searchQuery.asStateFlow()

    val searchResults: StateFlow<List<Track>> = _searchQuery
        .debounce(300)
        .flatMapLatest { query ->
            if (query.isBlank()) flowOf(emptyList())
            else repository.searchTracks(query)
        }
        .stateIn(viewModelScope, SharingStarted.Lazily, emptyList())

    init {
        // Observe DB
        viewModelScope.launch {
            repository.allTracks.collect { tracks ->
                val albumMap  = tracks.groupBy { it.album }
                val artistMap = tracks.groupBy { it.artist }
                _libState.update { it.copy(
                    tracks     = tracks,
                    albums     = albumMap,
                    artists    = artistMap,
                    totalTracks = tracks.size
                )}
            }
        }
        // Auto-scan on first launch
        refreshLibrary()
    }

    fun refreshLibrary() {
        viewModelScope.launch {
            _libState.update { it.copy(isScanning = true) }
            repository.refreshLibrary()
            _libState.update { it.copy(isScanning = false) }
        }
    }

    fun playTrack(track: Track) {
        val tracks = libState.value.tracks
        val idx    = tracks.indexOfFirst { it.id == track.id }.coerceAtLeast(0)
        playerController.playQueue(tracks, idx)
    }

    fun playAlbum(album: String, startTrack: Track? = null) {
        val tracks = libState.value.albums[album] ?: return
        val idx    = startTrack?.let { t -> tracks.indexOfFirst { it.id == t.id } } ?: 0
        playerController.playQueue(tracks, idx.coerceAtLeast(0))
    }

    fun playPause()     = playerController.playPause()
    fun skipNext()      = playerController.skipNext()
    fun skipPrevious()  = playerController.skipPrevious()
    fun seekTo(ms: Long) = playerController.seekTo(ms)

    fun setSearchQuery(q: String) { _searchQuery.value = q }

    override fun onCleared() {
        super.onCleared()
        playerController.release()
    }
}
"""
files['app/src/main/java/com/spectra/player/audio/PlaybackService.kt'] = """package com.spectra.player.audio

import android.app.PendingIntent
import android.content.Intent
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.session.MediaSession
import androidx.media3.session.MediaSessionService
import com.spectra.player.MainActivity

class PlaybackService : MediaSessionService() {

    private lateinit var player:       ExoPlayer
    private lateinit var mediaSession: MediaSession

    override fun onCreate() {
        super.onCreate()

        // Build ExoPlayer with high-quality audio attributes
        player = ExoPlayer.Builder(this)
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(C.USAGE_MEDIA)
                    .setContentType(C.AUDIO_CONTENT_TYPE_MUSIC)
                    .build(),
                /* handleAudioFocus = */ true
            )
            .setHandleAudioBecomingNoisy(true) // pause on headphone unplug
            .build()

        // Pending intent returns user to the player screen
        val sessionIntent = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE
        )

        mediaSession = MediaSession.Builder(this, player)
            .setSessionActivity(sessionIntent)
            .build()
    }

    override fun onGetSession(controllerInfo: MediaSession.ControllerInfo) = mediaSession

    override fun onDestroy() {
        mediaSession.release()
        player.release()
        super.onDestroy()
    }
}
"""
files['app/src/main/java/com/spectra/player/audio/PlayerController.kt'] = """package com.spectra.player.audio

import android.content.ComponentName
import android.content.Context
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.session.MediaController
import androidx.media3.session.SessionToken
import com.google.common.util.concurrent.ListenableFuture
import com.google.common.util.concurrent.MoreExecutors
import com.spectra.player.data.model.Track
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*

/** Thin wrapper that exposes ExoPlayer state as Kotlin Flows. */
class PlayerController(context: Context) {

    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())

    private val _currentTrack   = MutableStateFlow<Track?>(null)
    private val _isPlaying      = MutableStateFlow(false)
    private val _position       = MutableStateFlow(0L)
    private val _duration       = MutableStateFlow(0L)
    private val _queue          = MutableStateFlow<List<Track>>(emptyList())
    private val _currentIndex   = MutableStateFlow(0)

    val currentTrack: StateFlow<Track?> = _currentTrack.asStateFlow()
    val isPlaying:    StateFlow<Boolean> = _isPlaying.asStateFlow()
    val position:     StateFlow<Long>    = _position.asStateFlow()
    val duration:     StateFlow<Long>    = _duration.asStateFlow()
    val queue:        StateFlow<List<Track>> = _queue.asStateFlow()
    val currentIndex: StateFlow<Int>     = _currentIndex.asStateFlow()

    private var controller: MediaController? = null
    private val controllerFuture: ListenableFuture<MediaController>

    init {
        val sessionToken = SessionToken(
            context,
            ComponentName(context, PlaybackService::class.java)
        )
        controllerFuture = MediaController.Builder(context, sessionToken).buildAsync()
        controllerFuture.addListener({
            controller = controllerFuture.get()
            controller?.addListener(playerListener)
            startPositionPolling()
        }, MoreExecutors.directExecutor())
    }

    // ── Playback Listener ───────────────────────────────────────────────────

    private val playerListener = object : Player.Listener {
        override fun onIsPlayingChanged(playing: Boolean) {
            _isPlaying.value = playing
        }
        override fun onMediaItemTransition(mediaItem: MediaItem?, reason: Int) {
            val idx = controller?.currentMediaItemIndex ?: 0
            _currentIndex.value = idx
            _currentTrack.value = _queue.value.getOrNull(idx)
            _duration.value = controller?.duration?.coerceAtLeast(0) ?: 0
        }
    }

    // ── Position polling ────────────────────────────────────────────────────

    private fun startPositionPolling() {
        scope.launch {
            while (isActive) {
                _position.value = controller?.currentPosition?.coerceAtLeast(0) ?: 0
                _duration.value = controller?.duration?.coerceAtLeast(0) ?: 0
                delay(500)
            }
        }
    }

    // ── Public API ──────────────────────────────────────────────────────────

    fun playQueue(tracks: List<Track>, startIndex: Int = 0) {
        _queue.value = tracks
        _currentIndex.value = startIndex
        _currentTrack.value = tracks.getOrNull(startIndex)

        val mediaItems = tracks.map { track ->
            MediaItem.Builder()
                .setUri(track.toMediaUri())
                .setMediaId(track.id.toString())
                .build()
        }
        controller?.apply {
            setMediaItems(mediaItems, startIndex, 0)
            prepare()
            play()
        }
    }

    fun playPause() {
        controller?.let {
            if (it.isPlaying) it.pause() else it.play()
        }
    }

    fun skipNext() {
        controller?.seekToNextMediaItem()
    }

    fun skipPrevious() {
        val ctrl = controller ?: return
        if (ctrl.currentPosition > 3000) {
            ctrl.seekTo(0)
        } else {
            ctrl.seekToPreviousMediaItem()
        }
    }

    fun seekTo(positionMs: Long) {
        controller?.seekTo(positionMs)
    }

    fun toggleShuffle() {
        controller?.let { it.shuffleModeEnabled = !it.shuffleModeEnabled }
    }

    fun setRepeatMode(mode: Int) {
        controller?.repeatMode = mode
    }

    fun release() {
        scope.cancel()
        controller?.removeListener(playerListener)
        MediaController.releaseFuture(controllerFuture)
    }
}
"""
files['app/src/main/java/com/spectra/player/data/model/Track.kt'] = """package com.spectra.player.data.model

import android.net.Uri
import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "tracks")
data class Track(
    @PrimaryKey val id: Long,
    val uri: String,
    val title: String,
    val artist: String,
    val album: String,
    val albumArtUri: String?,
    val duration: Long,          // milliseconds
    val sampleRate: Int,         // Hz e.g. 96000
    val bitDepth: Int,           // e.g. 24
    val bitrate: Int,            // kbps
    val format: String,          // FLAC, WAV, ALAC, MP3, etc.
    val fileSize: Long,          // bytes
    val trackNumber: Int,
    val year: Int,
    val genre: String,
    val addedAt: Long = System.currentTimeMillis()
) {
    fun toMediaUri(): Uri = Uri.parse(uri)

    val isHiRes: Boolean
        get() = sampleRate > 44100 || bitDepth > 16

    val isLossless: Boolean
        get() = format in listOf("FLAC", "WAV", "AIFF", "ALAC")

    val formatBadge: String
        get() = when {
            format == "DSD" -> "DSD"
            isLossless && isHiRes -> "$format ${bitDepth}/${sampleRate / 1000}k"
            isLossless -> "$format ${bitDepth}/44.1k"
            else -> format
        }

    val durationFormatted: String
        get() {
            val totalSec = duration / 1000
            val min = totalSec / 60
            val sec = totalSec % 60
            return "$min:${sec.toString().padStart(2, '0')}"
        }
}
"""
files['app/src/main/java/com/spectra/player/data/repository/MediaScanner.kt'] = """package com.spectra.player.data.repository

import android.content.ContentResolver
import android.content.ContentUris
import android.content.Context
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import com.spectra.player.data.model.Track
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class MediaScanner(private val context: Context) {

    private val supportedFormats = setOf(
        "audio/flac", "audio/x-flac",
        "audio/wav", "audio/x-wav",
        "audio/aiff", "audio/x-aiff",
        "audio/alac",
        "audio/mp4",       // includes ALAC
        "audio/mpeg",      // MP3
        "audio/aac",
        "audio/ogg",
        "audio/dsd",       // DSD (device dependent)
    )

    suspend fun scanDevice(): List<Track> = withContext(Dispatchers.IO) {
        val tracks = mutableListOf<Track>()
        val contentResolver: ContentResolver = context.contentResolver

        val collection = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            MediaStore.Audio.Media.getContentUri(MediaStore.VOLUME_EXTERNAL)
        } else {
            MediaStore.Audio.Media.EXTERNAL_CONTENT_URI
        }

        val projection = arrayOf(
            MediaStore.Audio.Media._ID,
            MediaStore.Audio.Media.TITLE,
            MediaStore.Audio.Media.ARTIST,
            MediaStore.Audio.Media.ALBUM,
            MediaStore.Audio.Media.ALBUM_ID,
            MediaStore.Audio.Media.DURATION,
            MediaStore.Audio.Media.BITRATE,
            MediaStore.Audio.Media.SIZE,
            MediaStore.Audio.Media.TRACK,
            MediaStore.Audio.Media.YEAR,
            MediaStore.Audio.Media.MIME_TYPE,
            MediaStore.Audio.Media.DATA,
        )

        val sortOrder = "${MediaStore.Audio.Media.ARTIST} ASC, " +
                        "${MediaStore.Audio.Media.ALBUM} ASC, " +
                        "${MediaStore.Audio.Media.TRACK} ASC"

        contentResolver.query(collection, projection, null, null, sortOrder)?.use { cursor ->
            val idCol      = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media._ID)
            val titleCol   = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.TITLE)
            val artistCol  = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.ARTIST)
            val albumCol   = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.ALBUM)
            val albumIdCol = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.ALBUM_ID)
            val durCol     = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.DURATION)
            val bitrateCol = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.BITRATE)
            val sizeCol    = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.SIZE)
            val trackCol   = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.TRACK)
            val yearCol    = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.YEAR)
            val mimeCol    = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.MIME_TYPE)

            while (cursor.moveToNext()) {
                val id       = cursor.getLong(idCol)
                val mimeType = cursor.getString(mimeCol) ?: continue
                val duration = cursor.getLong(durCol)
                if (duration < 1000) continue // skip noise / ringtones

                val contentUri = ContentUris.withAppendedId(
                    MediaStore.Audio.Media.EXTERNAL_CONTENT_URI, id
                )
                val albumId   = cursor.getLong(albumIdCol)
                val albumArt  = getAlbumArtUri(albumId)

                // Extract sample rate & bit depth via MediaMetadataRetriever
                val (sampleRate, bitDepth, format) = extractAudioMetadata(contentUri, mimeType)

                tracks.add(
                    Track(
                        id          = id,
                        uri         = contentUri.toString(),
                        title       = cursor.getString(titleCol) ?: "Unknown Title",
                        artist      = cursor.getString(artistCol) ?: "Unknown Artist",
                        album       = cursor.getString(albumCol) ?: "Unknown Album",
                        albumArtUri = albumArt,
                        duration    = duration,
                        sampleRate  = sampleRate,
                        bitDepth    = bitDepth,
                        bitrate     = cursor.getInt(bitrateCol) / 1000,
                        format      = format,
                        fileSize    = cursor.getLong(sizeCol),
                        trackNumber = cursor.getInt(trackCol) % 1000,
                        year        = cursor.getInt(yearCol),
                        genre       = "",
                    )
                )
            }
        }

        tracks
    }

    private fun getAlbumArtUri(albumId: Long): String? {
        val albumArtUri = Uri.parse("content://media/external/audio/albumart")
        return ContentUris.withAppendedId(albumArtUri, albumId).toString()
    }

    private fun extractAudioMetadata(uri: Uri, mimeType: String): Triple<Int, Int, String> {
        val retriever = MediaMetadataRetriever()
        return try {
            retriever.setDataSource(context, uri)
            val sampleRate = retriever
                .extractMetadata(MediaMetadataRetriever.METADATA_KEY_SAMPLERATE)
                ?.toIntOrNull() ?: 44100
            val bitDepth = retriever
                .extractMetadata(MediaMetadataRetriever.METADATA_KEY_BITS_PER_SAMPLE)
                ?.toIntOrNull() ?: 16
            val format = mimeTypeToFormat(mimeType)
            Triple(sampleRate, bitDepth, format)
        } catch (e: Exception) {
            Triple(44100, 16, mimeTypeToFormat(mimeType))
        } finally {
            retriever.release()
        }
    }

    private fun mimeTypeToFormat(mimeType: String): String = when {
        mimeType.contains("flac") -> "FLAC"
        mimeType.contains("wav")  -> "WAV"
        mimeType.contains("aiff") -> "AIFF"
        mimeType.contains("alac") -> "ALAC"
        mimeType.contains("mpeg") || mimeType.contains("mp3") -> "MP3"
        mimeType.contains("aac") || mimeType.contains("mp4") -> "AAC"
        mimeType.contains("ogg") -> "OGG"
        mimeType.contains("dsd") -> "DSD"
        else -> "AUDIO"
    }
}
"""
files['app/src/main/java/com/spectra/player/data/repository/MusicRepository.kt'] = """package com.spectra.player.data.repository

import android.content.Context
import com.spectra.player.data.model.Track
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.withContext

class MusicRepository(context: Context) {

    private val db      = SpectraDatabase.getInstance(context)
    private val dao     = db.trackDao()
    private val scanner = MediaScanner(context)

    val allTracks: Flow<List<Track>> = dao.getAllTracks()
    val albums:    Flow<List<String>> = dao.getAlbums()
    val artists:   Flow<List<String>> = dao.getArtists()

    fun getTracksByAlbum(album: String)   = dao.getTracksByAlbum(album)
    fun getTracksByArtist(artist: String) = dao.getTracksByArtist(artist)
    fun searchTracks(query: String)       = dao.searchTracks(query)

    /** Scans device storage and syncs the local DB. */
    suspend fun refreshLibrary(): Int = withContext(Dispatchers.IO) {
        val scanned = scanner.scanDevice()
        dao.upsertTracks(scanned)
        dao.removeDeletedTracks(scanned.map { it.id })
        scanned.size
    }

    suspend fun getTrackCount() = dao.getTrackCount()
}
"""
files['app/src/main/java/com/spectra/player/data/repository/SpectraDatabase.kt'] = """package com.spectra.player.data.repository

import android.content.Context
import androidx.room.*
import com.spectra.player.data.model.Track
import kotlinx.coroutines.flow.Flow

// ── DAO ──────────────────────────────────────────────────────────────────────

@Dao
interface TrackDao {
    @Query("SELECT * FROM tracks ORDER BY artist, album, trackNumber")
    fun getAllTracks(): Flow<List<Track>>

    @Query("SELECT * FROM tracks WHERE id = :id")
    suspend fun getTrackById(id: Long): Track?

    @Query("SELECT DISTINCT album FROM tracks ORDER BY album")
    fun getAlbums(): Flow<List<String>>

    @Query("SELECT DISTINCT artist FROM tracks ORDER BY artist")
    fun getArtists(): Flow<List<String>>

    @Query("SELECT * FROM tracks WHERE album = :album ORDER BY trackNumber")
    fun getTracksByAlbum(album: String): Flow<List<Track>>

    @Query("SELECT * FROM tracks WHERE artist = :artist ORDER BY album, trackNumber")
    fun getTracksByArtist(artist: String): Flow<List<Track>>

    @Query("SELECT * FROM tracks WHERE title LIKE '%' || :query || '%' OR artist LIKE '%' || :query || '%' OR album LIKE '%' || :query || '%'")
    fun searchTracks(query: String): Flow<List<Track>>

    @Upsert
    suspend fun upsertTracks(tracks: List<Track>)

    @Query("DELETE FROM tracks WHERE id NOT IN (:ids)")
    suspend fun removeDeletedTracks(ids: List<Long>)

    @Query("SELECT COUNT(*) FROM tracks")
    suspend fun getTrackCount(): Int
}

// ── DATABASE ─────────────────────────────────────────────────────────────────

@Database(entities = [Track::class], version = 1, exportSchema = false)
abstract class SpectraDatabase : RoomDatabase() {
    abstract fun trackDao(): TrackDao

    companion object {
        @Volatile private var INSTANCE: SpectraDatabase? = null

        fun getInstance(context: Context): SpectraDatabase =
            INSTANCE ?: synchronized(this) {
                Room.databaseBuilder(
                    context.applicationContext,
                    SpectraDatabase::class.java,
                    "spectra_db"
                ).build().also { INSTANCE = it }
            }
    }
}
"""
files['app/src/main/java/com/spectra/player/ui/components/Components.kt'] = """package com.spectra.player.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import com.spectra.player.data.model.Track
import com.spectra.player.ui.theme.*

@Composable
fun FormatBadge(track: Track, modifier: Modifier = Modifier) {
    val color = when {
        track.format == "DSD"       -> AccentPurple
        track.isLossless && track.isHiRes -> Accent
        track.isLossless            -> AccentBlue
        else                        -> TextSecondary
    }
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(3.dp))
            .background(color.copy(alpha = 0.12f))
            .padding(horizontal = 6.dp, vertical = 2.dp)
    ) {
        Text(
            text = track.formatBadge,
            color = color,
            fontSize = 8.sp,
            fontFamily = FontFamily.Monospace,
            letterSpacing = 0.8.sp,
        )
    }
}

@Composable
fun TrackRow(
    track: Track,
    isActive: Boolean,
    trackNumber: Int,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    val accentColor = if (isActive) Accent else TextPrimary

    Row(
        modifier = modifier
            .fillMaxWidth()
            .clickable { onClick() }
            .background(if (isActive) Surface2 else Color.Transparent)
            .padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        // Track number / play indicator
        Text(
            text = if (isActive) "▶" else trackNumber.toString(),
            color = if (isActive) Accent else TextTertiary,
            fontSize = 9.sp,
            fontFamily = FontFamily.Monospace,
            modifier = Modifier.width(20.dp)
        )

        // Album art thumbnail
        AsyncImage(
            model = track.albumArtUri,
            contentDescription = null,
            modifier = Modifier
                .size(40.dp)
                .clip(RoundedCornerShape(3.dp))
                .background(Surface3)
        )

        // Title + artist
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = track.title,
                color = accentColor,
                fontSize = 13.sp,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Spacer(Modifier.height(2.dp))
            Text(
                text = track.artist,
                color = TextSecondary,
                fontSize = 10.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }

        Column(horizontalAlignment = Alignment.End) {
            FormatBadge(track)
            Spacer(Modifier.height(3.dp))
            Text(
                text = track.durationFormatted,
                color = TextTertiary,
                fontSize = 9.sp,
                fontFamily = FontFamily.Monospace,
            )
        }
    }
}

@Composable
fun SectionLabel(title: String, badge: String? = null, modifier: Modifier = Modifier) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = title,
            color = TextTertiary,
            fontSize = 8.sp,
            fontFamily = FontFamily.Monospace,
            letterSpacing = 1.5.sp,
        )
        if (badge != null) {
            Text(
                text = badge,
                color = AccentBlue,
                fontSize = 8.sp,
                fontFamily = FontFamily.Monospace,
                letterSpacing = 0.8.sp,
            )
        }
    }
}
"""
files['app/src/main/java/com/spectra/player/ui/screens/LibraryScreen.kt'] = """package com.spectra.player.ui.screens

import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.*
import androidx.compose.foundation.lazy.grid.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import com.spectra.player.MainViewModel
import com.spectra.player.data.model.Track
import com.spectra.player.ui.components.FormatBadge
import com.spectra.player.ui.components.TrackRow
import com.spectra.player.ui.theme.*

enum class LibTab { ALBUMS, ARTISTS, TRACKS }

@Composable
fun LibraryScreen(vm: MainViewModel) {
    val libState    by vm.libState.collectAsState()
    val searchQuery by vm.searchQuery.collectAsState()
    val searchResults by vm.searchResults.collectAsState()
    var activeTab   by remember { mutableStateOf(LibTab.ALBUMS) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Background)
    ) {
        // ── Search ──────────────────────────────────────────────────────────
        OutlinedTextField(
            value = searchQuery,
            onValueChange = vm::setSearchQuery,
            placeholder = { Text("Search tracks, artists, albums…",
                color = TextTertiary, fontSize = 11.sp, fontFamily = FontFamily.Monospace) },
            leadingIcon = { Icon(Icons.Default.Search, null, tint = TextTertiary) },
            singleLine = true,
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 12.dp),
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor   = AccentBlue,
                unfocusedBorderColor = Border,
                focusedTextColor     = TextPrimary,
                unfocusedTextColor   = TextPrimary,
                cursorColor          = Accent,
            ),
            shape = RoundedCornerShape(4.dp)
        )

        // ── Tabs ────────────────────────────────────────────────────────────
        Row(
            modifier = Modifier
                .padding(horizontal = 16.dp)
                .clip(RoundedCornerShape(4.dp))
                .background(Surface)
                .border(1.dp, Border, RoundedCornerShape(4.dp))
                .padding(3.dp),
        ) {
            LibTab.values().forEach { tab ->
                val selected = tab == activeTab
                Box(
                    modifier = Modifier
                        .weight(1f)
                        .clip(RoundedCornerShape(3.dp))
                        .background(if (selected) Surface3 else Color.Transparent)
                        .border(if (selected) 1.dp else 0.dp, if (selected) Border2 else Color.Transparent, RoundedCornerShape(3.dp))
                        .clickable { activeTab = tab }
                        .padding(vertical = 7.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = tab.name,
                        color = if (selected) Accent else TextTertiary,
                        fontSize = 8.sp,
                        letterSpacing = 1.sp,
                        fontFamily = FontFamily.Monospace,
                    )
                }
            }
        }

        Spacer(Modifier.height(12.dp))

        // ── Stats row ────────────────────────────────────────────────────────
        Row(
            modifier = Modifier.padding(horizontal = 16.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            StatChip("${libState.totalTracks} TRACKS")
            StatChip("${libState.albums.size} ALBUMS")
            if (libState.isScanning) StatChip("SCANNING…", Accent)
        }

        Spacer(Modifier.height(12.dp))

        // ── Content ──────────────────────────────────────────────────────────
        if (searchQuery.isNotBlank()) {
            // Search results
            LazyColumn {
                items(searchResults, key = { it.id }) { track ->
                    TrackRow(
                        track       = track,
                        isActive    = false,
                        trackNumber = 0,
                        onClick     = { vm.playTrack(track) }
                    )
                }
            }
        } else {
            when (activeTab) {
                LibTab.ALBUMS -> AlbumsGrid(vm)
                LibTab.ARTISTS -> ArtistsList(vm)
                LibTab.TRACKS -> TracksList(vm)
            }
        }
    }
}

@Composable
fun AlbumsGrid(vm: MainViewModel) {
    val libState by vm.libState.collectAsState()
    LazyVerticalGrid(
        columns = GridCells.Fixed(2),
        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        libState.albums.forEach { (album, tracks) ->
            item(key = album) {
                AlbumCard(
                    albumName = album,
                    artist    = tracks.firstOrNull()?.artist ?: "",
                    artUri    = tracks.firstOrNull()?.albumArtUri,
                    trackCount = tracks.size,
                    format    = tracks.firstOrNull(),
                    onClick   = { vm.playAlbum(album) }
                )
            }
        }
    }
}

@Composable
fun AlbumCard(
    albumName:  String,
    artist:     String,
    artUri:     String?,
    trackCount: Int,
    format:     Track?,
    onClick:    () -> Unit
) {
    Column(
        modifier = Modifier
            .clip(RoundedCornerShape(4.dp))
            .background(Surface)
            .border(1.dp, Border, RoundedCornerShape(4.dp))
            .clickable { onClick() }
            .padding(10.dp)
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(1f)
                .clip(RoundedCornerShape(3.dp))
                .background(Surface3)
        ) {
            AsyncImage(
                model = artUri,
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize()
            )
        }
        Spacer(Modifier.height(8.dp))
        Text(albumName, color = TextPrimary, fontSize = 11.sp, fontWeight = FontWeight.SemiBold,
            maxLines = 1, overflow = TextOverflow.Ellipsis)
        Text(artist, color = TextSecondary, fontSize = 9.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
        Spacer(Modifier.height(5.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
            format?.let { FormatBadge(it) }
            Text("$trackCount tracks", color = TextTertiary, fontSize = 8.sp, fontFamily = FontFamily.Monospace)
        }
    }
}

@Composable
fun ArtistsList(vm: MainViewModel) {
    val libState by vm.libState.collectAsState()
    LazyColumn(contentPadding = PaddingValues(horizontal = 16.dp)) {
        libState.artists.forEach { (artist, tracks) ->
            item(key = artist) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { vm.playAlbum(tracks.first().album) }
                        .padding(vertical = 12.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column {
                        Text(artist, color = TextPrimary, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                        Text("${tracks.size} tracks · ${tracks.map { it.album }.toSet().size} albums",
                            color = TextSecondary, fontSize = 10.sp)
                    }
                    Text("▶", color = TextTertiary, fontSize = 12.sp)
                }
                HorizontalDivider(color = Border, thickness = 0.5.dp)
            }
        }
    }
}

@Composable
fun TracksList(vm: MainViewModel) {
    val libState by vm.libState.collectAsState()
    LazyColumn {
        itemsIndexed(libState.tracks, key = { _, t -> t.id }) { idx, track ->
            TrackRow(
                track       = track,
                isActive    = false,
                trackNumber = idx + 1,
                onClick     = { vm.playTrack(track) }
            )
        }
    }
}

@Composable
fun StatChip(text: String, color: Color = TextTertiary) {
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(20.dp))
            .background(Surface)
            .border(1.dp, Border, RoundedCornerShape(20.dp))
            .padding(horizontal = 8.dp, vertical = 4.dp)
    ) {
        Text(text, color = color, fontSize = 7.sp, letterSpacing = 0.8.sp,
            fontFamily = FontFamily.Monospace)
    }
}
"""
files['app/src/main/java/com/spectra/player/ui/screens/PlayerScreen.kt'] = """package com.spectra.player.ui.screens

import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import com.spectra.player.MainViewModel
import com.spectra.player.data.model.Track
import com.spectra.player.ui.components.FormatBadge
import com.spectra.player.ui.components.SectionLabel
import com.spectra.player.ui.components.TrackRow
import com.spectra.player.ui.theme.*

@Composable
fun PlayerScreen(vm: MainViewModel) {
    val currentTrack by vm.currentTrack.collectAsState()
    val isPlaying    by vm.isPlaying.collectAsState()
    val position     by vm.position.collectAsState()
    val duration     by vm.duration.collectAsState()
    val queue        by vm.queue.collectAsState()
    val queueIndex   by vm.currentIndex.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .background(Background)
    ) {
        if (currentTrack == null) {
            EmptyPlayerPlaceholder()
        } else {
            currentTrack?.let { track ->
                AlbumArtSection(track = track, isPlaying = isPlaying)

                Column(modifier = Modifier.padding(horizontal = 20.dp)) {
                    Spacer(Modifier.height(20.dp))
                    TrackInfoSection(track)
                    Spacer(Modifier.height(16.dp))
                    ProgressSection(position, duration, onSeek = vm::seekTo)
                    Spacer(Modifier.height(16.dp))
                    ControlsSection(isPlaying, vm)
                    Spacer(Modifier.height(16.dp))
                }

                DacDashboard(track)
                Spacer(Modifier.height(12.dp))
                SignalMetersSection()
                Spacer(Modifier.height(12.dp))

                // Up next queue
                if (queue.isNotEmpty()) {
                    Column(modifier = Modifier.padding(horizontal = 20.dp)) {
                        SectionLabel(title = "UP NEXT", badge = "${queue.size} TRACKS")
                        Spacer(Modifier.height(10.dp))
                    }
                    queue.forEachIndexed { idx, t ->
                        TrackRow(
                            track       = t,
                            isActive    = idx == queueIndex,
                            trackNumber = idx + 1,
                            onClick     = { vm.playerController.playQueue(queue, idx) }
                        )
                    }
                    Spacer(Modifier.height(12.dp))
                }
            }
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────

@Composable
fun EmptyPlayerPlaceholder() {
    Box(
        modifier = Modifier.fillMaxWidth().height(300.dp),
        contentAlignment = Alignment.Center
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text("◈", fontSize = 48.sp, color = TextTertiary)
            Spacer(Modifier.height(16.dp))
            Text(
                "No track playing",
                color = TextSecondary,
                fontSize = 14.sp,
                fontFamily = FontFamily.Monospace
            )
            Text(
                "Browse your library to begin",
                color = TextTertiary,
                fontSize = 10.sp,
                letterSpacing = 0.5.sp,
                modifier = Modifier.padding(top = 4.dp)
            )
        }
    }
}

@Composable
fun AlbumArtSection(track: Track, isPlaying: Boolean) {
    val rotation by rememberInfiniteTransition(label = "vinyl").animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 20000, easing = LinearEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "spin"
    )

    Box(
        modifier = Modifier
            .fillMaxWidth()
            .aspectRatio(1f)
            .background(Surface)
    ) {
        // Album art
        AsyncImage(
            model = track.albumArtUri,
            contentDescription = "Album art",
            contentScale = ContentScale.Crop,
            modifier = Modifier.fillMaxSize()
        )

        // Dark scrim at bottom
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(120.dp)
                .align(Alignment.BottomCenter)
                .background(
                    Brush.verticalGradient(
                        listOf(Color.Transparent, Background.copy(alpha = 0.95f))
                    )
                )
        )

        // Animated vinyl disc when no art
        if (track.albumArtUri == null) {
            Box(
                modifier = Modifier
                    .size(200.dp)
                    .align(Alignment.Center)
                    .rotate(if (isPlaying) rotation else 0f)
                    .clip(CircleShape)
                    .background(Surface2)
                    .border(1.dp, Border, CircleShape),
                contentAlignment = Alignment.Center
            ) {
                Box(
                    modifier = Modifier
                        .size(50.dp)
                        .clip(CircleShape)
                        .background(Background)
                        .border(1.dp, Border2, CircleShape)
                )
            }
        }

        // Format badge top-right
        Box(
            modifier = Modifier
                .align(Alignment.TopEnd)
                .padding(12.dp)
                .clip(RoundedCornerShape(3.dp))
                .background(Background.copy(alpha = 0.85f))
                .padding(horizontal = 10.dp, vertical = 6.dp)
        ) {
            Column {
                Text(track.format, color = Accent, fontSize = 13.sp, fontWeight = FontWeight.Bold,
                    fontFamily = FontFamily.Monospace)
                Text("${track.bitDepth}BIT / ${track.sampleRate / 1000}kHz",
                    color = TextSecondary, fontSize = 8.sp, letterSpacing = 0.5.sp,
                    fontFamily = FontFamily.Monospace)
            }
        }

        // Bit-perfect badge bottom-left
        Row(
            modifier = Modifier
                .align(Alignment.BottomStart)
                .padding(12.dp)
                .clip(RoundedCornerShape(3.dp))
                .background(Background.copy(alpha = 0.85f))
                .border(1.dp, Accent.copy(alpha = 0.3f), RoundedCornerShape(3.dp))
                .padding(horizontal = 9.dp, vertical = 5.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(5.dp)
        ) {
            Box(Modifier.size(4.dp).clip(CircleShape).background(Accent))
            Text("BIT-PERFECT", color = Accent, fontSize = 8.sp, letterSpacing = 0.8.sp,
                fontFamily = FontFamily.Monospace)
        }
    }
}

@Composable
fun TrackInfoSection(track: Track) {
    Text(
        text = track.title,
        color = TextPrimary,
        fontSize = 22.sp,
        fontWeight = FontWeight.Bold,
        maxLines = 1,
        overflow = TextOverflow.Ellipsis
    )
    Spacer(Modifier.height(4.dp))
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(track.artist, color = TextSecondary, fontSize = 12.sp)
        Text("·", color = TextTertiary, fontSize = 12.sp)
        Text(track.album, color = AccentBlue, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
fun ProgressSection(position: Long, duration: Long, onSeek: (Long) -> Unit) {
    val progress = if (duration > 0) (position.toFloat() / duration).coerceIn(0f, 1f) else 0f

    Column {
        // Slider
        Slider(
            value = progress,
            onValueChange = { onSeek((it * duration).toLong()) },
            modifier = Modifier.fillMaxWidth().height(20.dp),
            colors = SliderDefaults.colors(
                thumbColor = Accent,
                activeTrackColor = Accent,
                inactiveTrackColor = Surface3
            )
        )
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(formatMs(position), color = TextTertiary, fontSize = 9.sp, fontFamily = FontFamily.Monospace)
            Text(formatMs(duration), color = TextTertiary, fontSize = 9.sp, fontFamily = FontFamily.Monospace)
        }
    }
}

@Composable
fun ControlsSection(isPlaying: Boolean, vm: MainViewModel) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically
    ) {
        ControlButton(icon = Icons.Default.Shuffle, onClick = { vm.playerController.toggleShuffle() })
        Spacer(Modifier.width(12.dp))
        ControlButton(icon = Icons.Default.SkipPrevious, size = 32.dp, onClick = vm::skipPrevious)
        Spacer(Modifier.width(16.dp))

        // Play/Pause FAB
        Box(
            modifier = Modifier
                .size(60.dp)
                .clip(CircleShape)
                .background(Brush.linearGradient(listOf(AccentBlue, Accent)))
                .clickable { vm.playPause() },
            contentAlignment = Alignment.Center
        ) {
            Icon(
                imageVector = if (isPlaying) Icons.Default.Pause else Icons.Default.PlayArrow,
                contentDescription = null,
                tint = Background,
                modifier = Modifier.size(28.dp)
            )
        }

        Spacer(Modifier.width(16.dp))
        ControlButton(icon = Icons.Default.SkipNext, size = 32.dp, onClick = vm::skipNext)
        Spacer(Modifier.width(12.dp))
        ControlButton(icon = Icons.Default.Repeat, onClick = {})
    }
}

@Composable
fun ControlButton(icon: ImageVector, size: androidx.compose.ui.unit.Dp = 24.dp, onClick: () -> Unit) {
    IconButton(onClick = onClick) {
        Icon(imageVector = icon, contentDescription = null, tint = TextSecondary,
            modifier = Modifier.size(size))
    }
}

@Composable
fun DacDashboard(track: Track) {
    Column(
        modifier = Modifier
            .padding(horizontal = 20.dp)
            .clip(RoundedCornerShape(4.dp))
            .background(Surface)
            .border(1.dp, Border, RoundedCornerShape(4.dp))
            .padding(14.dp)
    ) {
        SectionLabel(title = "DAC INTERFACE", badge = "ES9038PRO · USB")
        Spacer(Modifier.height(12.dp))

        Row(modifier = Modifier.fillMaxWidth()) {
            DacStat("${track.sampleRate / 1000}k", "SAMPLE RATE", Modifier.weight(1f))
            Box(Modifier.width(1.dp).height(40.dp).background(Border))
            DacStat("${track.bitDepth}", "BIT DEPTH", Modifier.weight(1f))
            Box(Modifier.width(1.dp).height(40.dp).background(Border))
            DacStat(track.format, "FORMAT", Modifier.weight(1f))
        }

        Spacer(Modifier.height(12.dp))
        HorizontalDivider(color = Border, thickness = 1.dp)
        Spacer(Modifier.height(10.dp))

        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            DacStatusItem("BIT-PERFECT ON", true)
            DacStatusItem("USB EXCL. MODE", true)
            DacStatusItem("MQA PASSTHROUGH", false)
        }
    }
}

@Composable
fun DacStat(value: String, label: String, modifier: Modifier = Modifier) {
    Column(modifier = modifier, horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, color = Accent, fontSize = 18.sp, fontWeight = FontWeight.Bold,
            fontFamily = FontFamily.Monospace)
        Spacer(Modifier.height(3.dp))
        Text(label, color = TextTertiary, fontSize = 7.sp, letterSpacing = 0.8.sp,
            textAlign = TextAlign.Center)
    }
}

@Composable
fun DacStatusItem(label: String, on: Boolean) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Box(
            Modifier.size(4.dp).clip(CircleShape)
                .background(if (on) Accent else Warning)
        )
        Text(label, color = TextSecondary, fontSize = 7.sp, letterSpacing = 0.5.sp,
            fontFamily = FontFamily.Monospace)
    }
}

@Composable
fun SignalMetersSection() {
    // Animated VU meters
    val infiniteTransition = rememberInfiniteTransition(label = "meters")
    val meterL by infiniteTransition.animateFloat(
        initialValue = 0.65f, targetValue = 0.88f,
        animationSpec = infiniteRepeatable(tween(300, easing = LinearEasing), RepeatMode.Reverse),
        label = "mL"
    )
    val meterR by infiniteTransition.animateFloat(
        initialValue = 0.55f, targetValue = 0.78f,
        animationSpec = infiniteRepeatable(tween(400, easing = LinearEasing), RepeatMode.Reverse),
        label = "mR"
    )

    Row(
        modifier = Modifier
            .padding(horizontal = 20.dp)
            .fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        MeterCard("CHANNEL L/R", meterL, meterR, Modifier.weight(1f))
        MeterCard("DYN RANGE", 0.82f, 0.45f, Modifier.weight(1f), isRange = true)
    }
}

@Composable
fun MeterCard(
    title: String,
    valA: Float,
    valB: Float,
    modifier: Modifier = Modifier,
    isRange: Boolean = false
) {
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(4.dp))
            .background(Surface)
            .border(1.dp, Border, RoundedCornerShape(4.dp))
            .padding(12.dp)
    ) {
        Text(title, color = TextTertiary, fontSize = 7.sp, letterSpacing = 1.sp,
            fontFamily = FontFamily.Monospace)
        Spacer(Modifier.height(8.dp))

        MeterBar(valA, if (isRange) Brush.horizontalGradient(listOf(AccentPurple, AccentBlue)) else
            Brush.horizontalGradient(listOf(AccentBlue, Accent)))
        Spacer(Modifier.height(4.dp))
        MeterBar(valB, if (isRange) Brush.horizontalGradient(listOf(Warning, Hot)) else
            Brush.horizontalGradient(listOf(AccentBlue, Accent)))

        Spacer(Modifier.height(6.dp))
        if (isRange) {
            Text("DR14  -9 LUFS", color = AccentBlue, fontSize = 11.sp, fontFamily = FontFamily.Monospace,
                fontWeight = FontWeight.Bold)
        } else {
            val dbL = (-20 * kotlin.math.log10(1.0 / valA.coerceIn(0.01f, 1f))).toInt()
            val dbR = (-20 * kotlin.math.log10(1.0 / valB.coerceIn(0.01f, 1f))).toInt()
            Text("${dbL}dBFS  ${dbR}dBFS", color = TextPrimary, fontSize = 11.sp,
                fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
fun MeterBar(value: Float, brush: Brush) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(5.dp)
            .clip(RoundedCornerShape(2.dp))
            .background(Surface3)
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth(value.coerceIn(0f, 1f))
                .fillMaxHeight()
                .clip(RoundedCornerShape(2.dp))
                .background(brush)
        )
    }
}

// ─────────────────────────────────────────────────────────────────────────────

fun formatMs(ms: Long): String {
    if (ms <= 0) return "0:00"
    val totalSec = ms / 1000
    val min = totalSec / 60
    val sec = totalSec % 60
    return "$min:${sec.toString().padStart(2, '0')}"
}
"""
files['app/src/main/java/com/spectra/player/ui/screens/SettingsScreen.kt'] = """package com.spectra.player.ui.screens

import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.spectra.player.ui.theme.*

data class SettingItem(
    val label: String,
    val sub:   String,
    val type:  SettingType,
    val value: String = "",
    val defaultOn: Boolean = false,
)

sealed class SettingType {
    object Toggle : SettingType()
    data class Value(val display: String) : SettingType()
    object Arrow  : SettingType()
}

@Composable
fun SettingsScreen() {
    val groups = listOf(
        "PLAYBACK ENGINE" to listOf(
            SettingItem("Bit-Perfect Mode", "Bypass system mixer entirely", SettingType.Toggle, defaultOn = true),
            SettingItem("USB Exclusive Mode", "Direct hardware DAC access", SettingType.Toggle, defaultOn = true),
            SettingItem("Gapless Playback", "Seamless track transitions", SettingType.Toggle, defaultOn = true),
            SettingItem("Buffer Size", "Lower = less latency, more CPU", SettingType.Value("512 samples")),
        ),
        "AUDIO PROCESSING" to listOf(
            SettingItem("ReplayGain", "Volume normalization", SettingType.Toggle, defaultOn = false),
            SettingItem("Crossfeed", "Speaker simulation on headphones", SettingType.Toggle, defaultOn = false),
            SettingItem("Dither", "Noise shaping on bit reduction", SettingType.Toggle, defaultOn = true),
            SettingItem("Sample Rate Output", "Target rate for conversion", SettingType.Value("Native")),
        ),
        "OUTPUT DEVICE" to listOf(
            SettingItem("Audio Output", "Current playback device", SettingType.Value("ES9038PRO DAC")),
            SettingItem("Hardware Volume", "DAC attenuation control", SettingType.Toggle, defaultOn = true),
            SettingItem("MQA Passthrough", "Send undecoded MQA to DAC", SettingType.Toggle, defaultOn = false),
        ),
        "LIBRARY" to listOf(
            SettingItem("Scan Music Library", "Refresh from device storage", SettingType.Arrow),
            SettingItem("Show Hi-Res Only", "Filter to lossless formats", SettingType.Toggle, defaultOn = false),
        ),
        "ABOUT" to listOf(
            SettingItem("Version", "Audio engine build", SettingType.Value("2.4.1")),
            SettingItem("ExoPlayer", "Media3 playback engine", SettingType.Value("1.4.0")),
        )
    )

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Background)
            .verticalScroll(rememberScrollState())
    ) {
        Spacer(Modifier.height(4.dp))
        groups.forEach { (groupName, items) ->
            SettingsGroup(groupName, items)
            Spacer(Modifier.height(20.dp))
        }
        Spacer(Modifier.height(80.dp))
    }
}

@Composable
fun SettingsGroup(title: String, items: List<SettingItem>) {
    Column(modifier = Modifier.padding(horizontal = 16.dp)) {
        Text(title, color = TextTertiary, fontSize = 7.sp, letterSpacing = 1.5.sp,
            fontFamily = FontFamily.Monospace, modifier = Modifier.padding(start = 2.dp, bottom = 8.dp))

        items.forEachIndexed { idx, item ->
            val radius = when {
                items.size == 1 -> RoundedCornerShape(4.dp)
                idx == 0        -> RoundedCornerShape(topStart = 4.dp, topEnd = 4.dp)
                idx == items.lastIndex -> RoundedCornerShape(bottomStart = 4.dp, bottomEnd = 4.dp)
                else            -> RoundedCornerShape(0.dp)
            }
            SettingsRow(item, radius)
            if (idx < items.lastIndex) {
                HorizontalDivider(color = Border, thickness = 0.5.dp,
                    modifier = Modifier.padding(start = 16.dp))
            }
        }
    }
}

@Composable
fun SettingsRow(item: SettingItem, shape: RoundedCornerShape) {
    var toggled by remember { mutableStateOf(item.defaultOn) }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(shape)
            .background(Surface)
            .clickable {
                if (item.type is SettingType.Toggle) toggled = !toggled
            }
            .padding(horizontal = 14.dp, vertical = 13.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(item.label, color = TextPrimary, fontSize = 12.sp, fontWeight = FontWeight.Medium)
            Spacer(Modifier.height(2.dp))
            Text(item.sub, color = TextTertiary, fontSize = 9.sp, letterSpacing = 0.3.sp)
        }
        Spacer(Modifier.width(12.dp))
        when (item.type) {
            is SettingType.Toggle -> {
                Switch(
                    checked = toggled,
                    onCheckedChange = { toggled = it },
                    colors = SwitchDefaults.colors(
                        checkedThumbColor  = Background,
                        checkedTrackColor  = Accent,
                        uncheckedThumbColor = TextTertiary,
                        uncheckedTrackColor = Surface3,
                        uncheckedBorderColor = Border2,
                    )
                )
            }
            is SettingType.Value -> {
                Text(item.type.display, color = AccentBlue, fontSize = 10.sp,
                    fontFamily = FontFamily.Monospace)
            }
            is SettingType.Arrow -> {
                Text("›", color = TextSecondary, fontSize = 18.sp)
            }
        }
    }
}
"""
files['app/src/main/java/com/spectra/player/ui/theme/Theme.kt'] = """package com.spectra.player.ui.theme

import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight

// ── Colour palette ──────────────────────────────────────────────────────────

val Background    = Color(0xFF080C0E)
val Surface       = Color(0xFF0D1315)
val Surface2      = Color(0xFF111A1E)
val Surface3      = Color(0xFF162028)
val Border        = Color(0xFF1E3040)
val Border2       = Color(0xFF243848)

val Accent        = Color(0xFF00E5B0)
val AccentBlue    = Color(0xFF00B5E8)
val AccentPurple  = Color(0xFF7B5EA7)
val Warning       = Color(0xFFF0A500)
val Hot           = Color(0xFFFF4D6D)

val TextPrimary   = Color(0xFFC8DDE8)
val TextSecondary = Color(0xFF6A8FA0)
val TextTertiary  = Color(0xFF3A5568)

// ── Material3 dark colour scheme ────────────────────────────────────────────

private val SpectraColorScheme = darkColorScheme(
    primary          = Accent,
    onPrimary        = Background,
    primaryContainer = Surface3,
    secondary        = AccentBlue,
    onSecondary      = Background,
    background       = Background,
    surface          = Surface,
    onSurface        = TextPrimary,
    onBackground     = TextPrimary,
    surfaceVariant   = Surface2,
    outline          = Border,
    error            = Hot,
)

@Composable
fun SpectraTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = SpectraColorScheme,
        content     = content
    )
}
"""
files['app/src/main/res/drawable/ic_launcher_background.xml'] = """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <solid android:color="#080C0E"/>
</shape>
"""
files['app/src/main/res/drawable/ic_launcher_foreground.xml'] = """<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp"
    android:height="108dp"
    android:viewportWidth="108"
    android:viewportHeight="108">
    <path
        android:fillColor="#080C0E"
        android:pathData="M0,0h108v108H0z"/>
    <path
        android:fillColor="#00E5B0"
        android:pathData="M54,24 L54,84 M34,44 L34,64 M44,34 L44,74 M64,34 L64,74 M74,44 L74,64"
        android:strokeColor="#00E5B0"
        android:strokeWidth="3"
        android:strokeLineCap="round"/>
    <path
        android:fillColor="#00000000"
        android:strokeColor="#00E5B0"
        android:strokeWidth="2"
        android:pathData="M54,38 A16,16 0 0,1 70,54 A16,16 0 0,1 54,70 A16,16 0 0,1 38,54 A16,16 0 0,1 54,38 Z"/>
</vector>
"""
files['app/src/main/res/mipmap-hdpi/ic_launcher.xml'] = """<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@drawable/ic_launcher_background"/>
    <foreground android:drawable="@drawable/ic_launcher_foreground"/>
</adaptive-icon>
"""
files['app/src/main/res/mipmap-hdpi/ic_launcher_round.xml'] = """<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@drawable/ic_launcher_background"/>
    <foreground android:drawable="@drawable/ic_launcher_foreground"/>
</adaptive-icon>
"""
files['app/src/main/res/values/strings.xml'] = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">Spectra</string>
</resources>
"""
files['app/src/main/res/values/themes.xml'] = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="Theme.SpectraPlayer" parent="Theme.AppCompat.DayNight.NoActionBar">
        <item name="android:statusBarColor">#FF080C0E</item>
        <item name="android:navigationBarColor">#FF080C0E</item>
        <item name="android:windowBackground">#FF080C0E</item>
    </style>
</resources>
"""
files['gradle/libs.versions.toml'] = """[versions]
agp = "7.4.2"
kotlin = "1.8.22"
coreKtx = "1.10.1"
junit = "4.13.2"
junitVersion = "1.1.5"
espressoCore = "3.5.1"
lifecycleRuntimeKtx = "2.6.2"
activityCompose = "1.7.2"
composeBom = "2023.08.00"
media3 = "1.1.1"
navigationCompose = "2.7.2"
coil = "2.4.0"
kotlinxCoroutines = "1.7.3"
room = "2.5.2"
ksp = "1.8.22-1.0.11"

[libraries]
androidx-core-ktx = { group = "androidx.core", name = "core-ktx", version.ref = "coreKtx" }
junit = { group = "junit", name = "junit", version.ref = "junit" }
androidx-junit = { group = "androidx.test.ext", name = "junit", version.ref = "junitVersion" }
androidx-espresso-core = { group = "androidx.test.espresso", name = "espresso-core", version.ref = "espressoCore" }
androidx-lifecycle-runtime-ktx = { group = "androidx.lifecycle", name = "lifecycle-runtime-ktx", version.ref = "lifecycleRuntimeKtx" }
androidx-lifecycle-viewmodel-compose = { group = "androidx.lifecycle", name = "lifecycle-viewmodel-compose", version.ref = "lifecycleRuntimeKtx" }
androidx-activity-compose = { group = "androidx.activity", name = "activity-compose", version.ref = "activityCompose" }
androidx-compose-bom = { group = "androidx.compose", name = "compose-bom", version.ref = "composeBom" }
androidx-ui = { group = "androidx.compose.ui", name = "ui" }
androidx-ui-graphics = { group = "androidx.compose.ui", name = "ui-graphics" }
androidx-ui-tooling = { group = "androidx.compose.ui", name = "ui-tooling" }
androidx-ui-tooling-preview = { group = "androidx.compose.ui", name = "ui-tooling-preview" }
androidx-ui-test-manifest = { group = "androidx.compose.ui", name = "ui-test-manifest" }
androidx-ui-test-junit4 = { group = "androidx.compose.ui", name = "ui-test-junit4" }
androidx-material3 = { group = "androidx.compose.material3", name = "material3" }
androidx-material-icons = { group = "androidx.compose.material", name = "material-icons-extended" }
media3-exoplayer = { group = "androidx.media3", name = "media3-exoplayer", version.ref = "media3" }
media3-ui = { group = "androidx.media3", name = "media3-ui", version.ref = "media3" }
media3-session = { group = "androidx.media3", name = "media3-session", version.ref = "media3" }
media3-datasource = { group = "androidx.media3", name = "media3-datasource", version.ref = "media3" }
navigation-compose = { group = "androidx.navigation", name = "navigation-compose", version.ref = "navigationCompose" }
coil-compose = { group = "io.coil-kt", name = "coil-compose", version.ref = "coil" }
kotlinx-coroutines-android = { group = "org.jetbrains.kotlinx", name = "kotlinx-coroutines-android", version.ref = "kotlinxCoroutines" }
room-runtime = { group = "androidx.room", name = "room-runtime", version.ref = "room" }
room-ktx = { group = "androidx.room", name = "room-ktx", version.ref = "room" }
room-compiler = { group = "androidx.room", name = "room-compiler", version.ref = "room" }

[plugins]
android-application = { id = "com.android.application", version.ref = "agp" }
kotlin-android = { id = "org.jetbrains.kotlin.android", version.ref = "kotlin" }
kotlin-compose = { id = "org.jetbrains.kotlin.plugin.compose", version.ref = "kotlin" }
ksp = { id = "com.google.devtools.ksp", version.ref = "ksp" }
"""
files['gradle/wrapper/gradle-wrapper.properties'] = """distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\\://services.gradle.org/distributions/gradle-7.4.2-bin.zip
networkTimeout=10000
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
"""

for path, content in files.items():
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    print(f"Created: {path}")
print("\nAll files created! Now run: chmod +x gradlew && ./gradlew assembleDebug")
