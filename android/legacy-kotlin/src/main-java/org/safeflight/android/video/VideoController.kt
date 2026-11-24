package org.safeflight.android.video

import android.content.Context
import android.os.Handler
import android.os.Looper
import androidx.annotation.OptIn
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.VideoSize
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.DefaultLoadControl
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.rtsp.RtspMediaSource
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import org.safeflight.android.config.VideoSettings
import org.safeflight.android.diagnostics.DiagnosticsLog

/**
 * RTSP/H.264 player built on Media3 ExoPlayer.
 *
 * Responsibilities: low-latency buffering, frame-age supervision, controlled
 * retries after errors and release of the decoder when the screen stops.
 * Must be used from the main thread.
 */
@OptIn(UnstableApi::class)
class VideoController(
    private val context: Context,
    private val log: DiagnosticsLog,
) {
    private val handler = Handler(Looper.getMainLooper())
    private var player: ExoPlayer? = null
    private var settings: VideoSettings? = null
    private var staleAfterMs: Long = 2000
    private var retryDelayMs: Long = 1000
    @Volatile private var lastFrameAtMs: Long? = null
    @Volatile private var frameCounter: Long = 0
    private var openedAtMs: Long? = null
    private var attachedSurfaces = 0

    /**
     * Called by the views that display the video. Without a surface no frame
     * is rendered, so freeze detection is suspended instead of reporting a
     * false "frozen video" and reopening the session in a loop.
     */
    fun onSurfaceAttached() {
        attachedSurfaces += 1
        lastFrameAtMs = lastFrameAtMs?.let { System.currentTimeMillis() }
    }

    fun onSurfaceDetached() {
        attachedSurfaces = (attachedSurfaces - 1).coerceAtLeast(0)
    }

    private val _state = MutableStateFlow(VideoState())
    val state: StateFlow<VideoState> = _state.asStateFlow()

    private val _player = MutableStateFlow<Player?>(null)
    /** Current player instance; changes after every reconnection. */
    val playerFlow: StateFlow<Player?> = _player.asStateFlow()

    private val ticker = object : Runnable {
        override fun run() {
            val now = System.currentTimeMillis()
            if (attachedSurfaces == 0 && lastFrameAtMs != null) {
                // No visible surface: keep the session, do not judge freshness.
                handler.postDelayed(this, 250)
                return
            }
            _state.update {
                VideoSupervisor.onTick(it, lastFrameAtMs, now, staleAfterMs).copy(framesRendered = frameCounter)
            }
            VideoSupervisor.restartReason(
                _state.value, openedAtMs, lastFrameAtMs, now, staleAfterMs, CONNECT_TIMEOUT_MS,
            )?.let { reason ->
                log.warn("Vídeo", "$reason; reabriendo la sesión RTSP")
                _state.update { VideoSupervisor.onError(it, reason) }
                settings?.let { openPlayer(it) }
            }
            handler.postDelayed(this, 250)
        }
    }

    private val retry = Runnable { settings?.let { openPlayer(it) } }

    /** Applies [video] settings and starts playback when RTSP is configured. */
    fun start(video: VideoSettings, staleS: Double, reconnectIntervalS: Double) {
        stop()
        settings = video
        staleAfterMs = (staleS * 1000).toLong()
        retryDelayMs = (reconnectIntervalS * 1000).toLong().coerceAtLeast(200)
        if (video.mode != "rtsp" || video.rtspUrl.isBlank()) {
            _state.value = VideoState(status = VideoStatus.IDLE, url = video.rtspUrl)
            log.info("Vídeo", "Vídeo desactivado en el perfil (${video.mode})")
            return
        }
        _state.value = VideoState(status = VideoStatus.CONNECTING, url = video.rtspUrl)
        openPlayer(video)
        handler.post(ticker)
    }

    private fun openPlayer(video: VideoSettings) {
        handler.removeCallbacks(retry)
        releasePlayer()
        lastFrameAtMs = null
        frameCounter = 0
        openedAtMs = System.currentTimeMillis()
        _state.update { it.copy(status = VideoStatus.CONNECTING, lastFrameAgeMs = null) }
        log.info("Vídeo", "Abriendo ${video.rtspUrl} (${video.rtspTransport.uppercase()})")
        val loadControl = DefaultLoadControl.Builder()
            // Small buffers: live supervision video, latency over smoothness.
            .setBufferDurationsMs(300, 1500, 150, 150)
            .setPrioritizeTimeOverSizeThresholds(true)
            .build()
        val exo = ExoPlayer.Builder(context).setLoadControl(loadControl).build()
        val source = RtspMediaSource.Factory()
            .setForceUseRtpTcp(video.rtspTransport == "tcp")
            .setTimeoutMs(8000)
            .createMediaSource(MediaItem.fromUri(video.rtspUrl))
        exo.setMediaSource(source)
        exo.playWhenReady = true
        exo.setVideoFrameMetadataListener { _, _, format, _ ->
            lastFrameAtMs = System.currentTimeMillis()
            frameCounter += 1
            if (frameCounter == 1L) {
                handler.post {
                    if (player !== exo) return@post
                    _state.update { VideoSupervisor.onFrame(it, System.currentTimeMillis(), format.width, format.height) }
                    log.info("Vídeo", "Primer fotograma ${format.width}x${format.height}")
                }
            }
        }
        exo.addListener(object : Player.Listener {
            override fun onPlayerError(error: PlaybackException) {
                if (player !== exo) return // event from a replaced player
                val message = "${error.errorCodeName}: ${error.message}"
                _state.update { VideoSupervisor.onError(it, message) }
                log.error("Vídeo", "$message. Reintento en ${retryDelayMs} ms")
                handler.removeCallbacks(retry)
                handler.postDelayed(retry, retryDelayMs)
            }

            override fun onPlaybackStateChanged(playbackState: Int) {
                if (player !== exo) return
                if (playbackState == Player.STATE_ENDED) {
                    log.warn("Vídeo", "Flujo finalizado por el servidor; reintentando")
                    _state.update { VideoSupervisor.onError(it, "STATE_ENDED") }
                    handler.removeCallbacks(retry)
                    handler.postDelayed(retry, retryDelayMs)
                }
            }

            override fun onVideoSizeChanged(videoSize: VideoSize) {
                if (videoSize.width > 0) _state.update { it.copy(width = videoSize.width, height = videoSize.height) }
            }
        })
        exo.prepare()
        player = exo
        _player.value = exo
    }

    /** Stops playback and releases the decoder (called on ON_STOP). */
    fun stop() {
        handler.removeCallbacks(retry)
        handler.removeCallbacks(ticker)
        openedAtMs = null
        releasePlayer()
        if (_state.value.status != VideoStatus.IDLE) log.info("Vídeo", "Reproducción detenida")
        _state.update { it.copy(status = VideoStatus.IDLE, lastFrameAgeMs = null) }
    }

    private companion object {
        const val CONNECT_TIMEOUT_MS = 10_000L
    }

    private fun releasePlayer() {
        _player.value = null
        player?.release()
        player = null
    }
}
