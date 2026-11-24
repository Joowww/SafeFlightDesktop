package org.safeflight.android.video;

/** Immutable snapshot of the video player; {@code withX} methods return modified copies. */
public final class VideoState {
    public final VideoStatus status;
    public final String url;
    public final Long lastFrameAgeMs;
    public final long framesRendered;
    public final Integer width;
    public final Integer height;
    public final String lastError;
    public final int retries;

    public VideoState() {
        this(VideoStatus.IDLE, "");
    }

    public VideoState(VideoStatus status, String url) {
        this(status, url, null, 0, null, null, null, 0);
    }

    public VideoState(VideoStatus status, String url, Long lastFrameAgeMs, long framesRendered, Integer width,
                      Integer height, String lastError, int retries) {
        this.status = status;
        this.url = url;
        this.lastFrameAgeMs = lastFrameAgeMs;
        this.framesRendered = framesRendered;
        this.width = width;
        this.height = height;
        this.lastError = lastError;
        this.retries = retries;
    }

    public VideoState withStatus(VideoStatus newStatus, Long newLastFrameAgeMs) {
        return new VideoState(newStatus, url, newLastFrameAgeMs, framesRendered, width, height, lastError, retries);
    }

    public VideoState withFramesRendered(long frames) {
        return new VideoState(status, url, lastFrameAgeMs, frames, width, height, lastError, retries);
    }

    public VideoState withSize(Integer newWidth, Integer newHeight) {
        return new VideoState(status, url, lastFrameAgeMs, framesRendered, newWidth, newHeight, lastError, retries);
    }

    VideoState withFrame(Integer newWidth, Integer newHeight) {
        return new VideoState(VideoStatus.PLAYING, url, 0L, framesRendered + 1,
                newWidth != null ? newWidth : width, newHeight != null ? newHeight : height, null, retries);
    }

    VideoState withError(String message) {
        return new VideoState(VideoStatus.ERROR, url, lastFrameAgeMs, framesRendered, width, height, message,
                retries + 1);
    }
}
