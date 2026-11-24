package org.safeflight.android.video;

/** Pure transitions for video supervision (unit tested on the JVM, no player involved). */
public final class VideoSupervisor {

    private VideoSupervisor() {
    }

    public static VideoState onFrame(VideoState state, long nowMs, Integer width, Integer height) {
        return state.withFrame(width, height);
    }

    public static VideoState onTick(VideoState state, Long lastFrameAtMs, long nowMs, long staleAfterMs) {
        if (state.status == VideoStatus.IDLE || state.status == VideoStatus.ERROR) {
            return state;
        }
        if (lastFrameAtMs == null) {
            return state;
        }
        long age = Math.max(0, nowMs - lastFrameAtMs);
        VideoStatus status = age > staleAfterMs ? VideoStatus.STALE : VideoStatus.PLAYING;
        return state.withStatus(status, age);
    }

    public static VideoState onError(VideoState state, String message) {
        return state.withError(message);
    }

    /** Longest wait between reconnection attempts while no frame arrives. */
    public static final long MAX_RETRY_DELAY_MS = 10_000;

    /**
     * Delay before the next reconnection: the profile interval for the first
     * failure, then doubled for every further consecutive failure without any
     * frame, up to {@link #MAX_RETRY_DELAY_MS}. An unreachable camera thus
     * costs little CPU, and a working stream reconnects quickly again because
     * the counter is reset by the first frame.
     */
    public static long retryDelayMs(long baseMs, int consecutiveFailures) {
        long delay = baseMs;
        for (int i = 1; i < consecutiveFailures && delay < MAX_RETRY_DELAY_MS; i++) {
            delay *= 2;
        }
        return Math.min(Math.max(delay, baseMs), Math.max(baseMs, MAX_RETRY_DELAY_MS));
    }

    /**
     * Watchdog. Some failures never raise a player error (e.g. a TCP proxy that
     * accepts the connection while the RTSP server is down), so the session is
     * reopened when no frame arrives within {@code connectTimeoutMs} of opening,
     * or when the stream stays frozen for more than 4 x {@code staleAfterMs}.
     * Returns the reason, or {@code null} when no restart is needed.
     */
    public static String restartReason(VideoState state, Long openedAtMs, Long lastFrameAtMs, long nowMs,
                                       long staleAfterMs, long connectTimeoutMs) {
        if (openedAtMs == null) {
            return null;
        }
        if (state.status == VideoStatus.CONNECTING && lastFrameAtMs == null
                && nowMs - openedAtMs > connectTimeoutMs) {
            return "Sin fotogramas tras " + (connectTimeoutMs / 1000) + " s";
        }
        if (state.status == VideoStatus.STALE && lastFrameAtMs != null
                && nowMs - lastFrameAtMs > staleAfterMs * 4) {
            return "Vídeo congelado " + ((nowMs - lastFrameAtMs) / 1000) + " s";
        }
        return null;
    }
}
