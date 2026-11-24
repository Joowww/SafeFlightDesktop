package org.safeflight.android.video

enum class VideoStatus {
    /** Video disabled or not started. */
    IDLE,
    /** Opening the RTSP session / buffering. */
    CONNECTING,
    /** Frames are being rendered. */
    PLAYING,
    /** Session open but no frame rendered for longer than `video_stale_s`. */
    STALE,
    /** Player error; a retry is scheduled. */
    ERROR,
}

data class VideoState(
    val status: VideoStatus = VideoStatus.IDLE,
    val url: String = "",
    val lastFrameAgeMs: Long? = null,
    val framesRendered: Long = 0,
    val width: Int? = null,
    val height: Int? = null,
    val lastError: String? = null,
    val retries: Int = 0,
)

/** Pure transitions for video supervision (unit tested on the JVM). */
object VideoSupervisor {
    fun onFrame(state: VideoState, nowMs: Long, width: Int?, height: Int?): VideoState =
        state.copy(
            status = VideoStatus.PLAYING,
            lastFrameAgeMs = 0,
            framesRendered = state.framesRendered + 1,
            width = width ?: state.width,
            height = height ?: state.height,
            lastError = null,
        )

    fun onTick(state: VideoState, lastFrameAtMs: Long?, nowMs: Long, staleAfterMs: Long): VideoState {
        if (state.status == VideoStatus.IDLE || state.status == VideoStatus.ERROR) return state
        if (lastFrameAtMs == null) return state
        val age = (nowMs - lastFrameAtMs).coerceAtLeast(0)
        val status = if (age > staleAfterMs) VideoStatus.STALE else VideoStatus.PLAYING
        return state.copy(status = status, lastFrameAgeMs = age)
    }

    fun onError(state: VideoState, message: String): VideoState =
        state.copy(status = VideoStatus.ERROR, lastError = message, retries = state.retries + 1)

    /**
     * Watchdog. Some failures never raise a player error (e.g. a TCP proxy that
     * accepts the connection while the RTSP server is down), so the session
     * is reopened when no frame arrives within [connectTimeoutMs] of opening,
     * or when the stream stays frozen for more than 4 × [staleAfterMs].
     * Returns the reason, or null when no restart is needed.
     */
    fun restartReason(
        state: VideoState,
        openedAtMs: Long?,
        lastFrameAtMs: Long?,
        nowMs: Long,
        staleAfterMs: Long,
        connectTimeoutMs: Long,
    ): String? = when {
        openedAtMs == null -> null
        state.status == VideoStatus.CONNECTING && lastFrameAtMs == null &&
            nowMs - openedAtMs > connectTimeoutMs -> "Sin fotogramas tras ${connectTimeoutMs / 1000} s"
        state.status == VideoStatus.STALE && lastFrameAtMs != null &&
            nowMs - lastFrameAtMs > staleAfterMs * 4 -> "Vídeo congelado ${(nowMs - lastFrameAtMs) / 1000} s"
        else -> null
    }
}
