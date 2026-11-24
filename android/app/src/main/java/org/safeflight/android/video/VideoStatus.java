package org.safeflight.android.video;

public enum VideoStatus {
    /** Video disabled or not started. */
    IDLE,
    /** Opening the RTSP session / buffering. */
    CONNECTING,
    /** Frames are being rendered. */
    PLAYING,
    /** Session open but no frame rendered for longer than {@code video_stale_s}. */
    STALE,
    /** Player error; a retry is scheduled. */
    ERROR,
}
