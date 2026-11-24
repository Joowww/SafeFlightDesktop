package org.safeflight.android.video;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;

import androidx.annotation.NonNull;
import androidx.annotation.OptIn;
import androidx.lifecycle.LiveData;
import androidx.lifecycle.MutableLiveData;
import androidx.media3.common.MediaItem;
import androidx.media3.common.PlaybackException;
import androidx.media3.common.Player;
import androidx.media3.common.VideoSize;
import androidx.media3.common.util.UnstableApi;
import androidx.media3.exoplayer.DefaultLoadControl;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.exoplayer.rtsp.RtspMediaSource;

import org.safeflight.android.config.VideoSettings;
import org.safeflight.android.diagnostics.DiagnosticsLog;

import java.util.Locale;

/**
 * RTSP/H.264 player built on Media3 ExoPlayer.
 *
 * <p>Responsibilities: low-latency buffering, frame-age supervision, controlled
 * retries after errors and release of the decoder when the screen stops
 * ({@link #stop()} is called from {@code MainActivity.onStop}).
 * Must be used from the main thread. The screens observe {@link #getState()}
 * and attach {@link #getPlayer()} to their {@code PlayerView}.
 */
@OptIn(markerClass = UnstableApi.class)
public final class VideoController {
    private static final long CONNECT_TIMEOUT_MS = 10_000L;
    private static final long TICK_MS = 250;

    private final Context context;
    private final DiagnosticsLog log;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final MutableLiveData<VideoState> state = new MutableLiveData<>(new VideoState());
    private final MutableLiveData<Player> playerLiveData = new MutableLiveData<>(null);

    private ExoPlayer player;
    private VideoSettings settings;
    private long staleAfterMs = 2000;
    private long retryDelayMs = 1000;
    private volatile Long lastFrameAtMs;
    private volatile long frameCounter = 0;
    private Long openedAtMs;
    private int attachedSurfaces = 0;
    private long lastPublishedTickMs = 0;
    /** Failures since the last rendered frame (drives the growing retry delay). */
    private int consecutiveFailures = 0;

    public VideoController(Context context, DiagnosticsLog log) {
        this.context = context.getApplicationContext();
        this.log = log;
    }

    public LiveData<VideoState> getState() {
        return state;
    }

    /** Current player instance; changes after every reconnection ({@code null} when stopped). */
    public LiveData<Player> getPlayer() {
        return playerLiveData;
    }

    public VideoState currentState() {
        VideoState s = state.getValue();
        return s != null ? s : new VideoState();
    }

    /**
     * Called by the screens that display the video. Without a surface no frame
     * is rendered, so freeze detection is suspended instead of reporting a
     * false "frozen video" and reopening the session in a loop.
     */
    public void onSurfaceAttached() {
        attachedSurfaces += 1;
        if (lastFrameAtMs != null) {
            lastFrameAtMs = System.currentTimeMillis();
        }
    }

    public void onSurfaceDetached() {
        attachedSurfaces = Math.max(0, attachedSurfaces - 1);
    }

    // ------------------------------------------------ deferred surface release
    // Releasing a video surface blocks the main thread while ExoPlayer moves the
    // decoder off it (~65-140 ms measured on the API 28 emulator). When a screen is
    // hidden, the release is postponed until the next frame has been drawn, so the
    // destination screen appears first. If another screen needs the video earlier,
    // it runs the pending release itself (flushPendingRelease) before attaching.
    private Runnable pendingRelease;

    /** Runs {@code release} after the next frame is drawn, unless flushed earlier. */
    public void releaseAfterNextFrame(Runnable release) {
        flushPendingRelease();
        pendingRelease = release;
        android.view.Choreographer.getInstance().postFrameCallback(frameTimeNanos ->
                // Frame callbacks run before the frame is drawn; posting from here runs after it.
                handler.post(this::flushPendingRelease));
    }

    /** Runs a pending release now (no-op when there is none). */
    public void flushPendingRelease() {
        Runnable release = pendingRelease;
        pendingRelease = null;
        if (release != null) {
            release.run();
        }
    }

    private final Runnable ticker = new Runnable() {
        @Override
        public void run() {
            long now = System.currentTimeMillis();
            if (attachedSurfaces == 0 && lastFrameAtMs != null) {
                // No visible surface: keep the session, do not judge freshness.
                handler.postDelayed(this, TICK_MS);
                return;
            }
            VideoState ticked = VideoSupervisor.onTick(currentState(), lastFrameAtMs, now, staleAfterMs)
                    .withFramesRendered(frameCounter);
            // Status changes are published at once; the frame age/counter at most once per second.
            if (ticked.status != currentState().status || now - lastPublishedTickMs >= 1000) {
                lastPublishedTickMs = now;
                setState(ticked);
            }
            String reason = VideoSupervisor.restartReason(currentState(), openedAtMs, lastFrameAtMs, now,
                    staleAfterMs, CONNECT_TIMEOUT_MS);
            if (reason != null) {
                log.warn("Vídeo", reason + "; reabriendo la sesión RTSP");
                setState(VideoSupervisor.onError(currentState(), reason));
                if (settings != null) {
                    openPlayer(settings);
                }
            }
            handler.postDelayed(this, TICK_MS);
        }
    };

    private final Runnable retry = () -> {
        if (settings != null) {
            openPlayer(settings);
        }
    };

    /** Applies {@code video} settings and starts playback when RTSP is configured. */
    public void start(VideoSettings video, double staleS, double reconnectIntervalS) {
        stop();
        settings = video.copy();
        consecutiveFailures = 0;
        staleAfterMs = (long) (staleS * 1000);
        retryDelayMs = Math.max(200, (long) (reconnectIntervalS * 1000));
        if (!"rtsp".equals(video.mode) || video.rtspUrl == null || video.rtspUrl.trim().isEmpty()) {
            setState(new VideoState(VideoStatus.IDLE, video.rtspUrl));
            log.info("Vídeo", "Vídeo desactivado en el perfil (" + video.mode + ")");
            return;
        }
        setState(new VideoState(VideoStatus.CONNECTING, video.rtspUrl));
        openPlayer(settings);
        handler.post(ticker);
    }

    private void openPlayer(VideoSettings video) {
        handler.removeCallbacks(retry);
        releasePlayer();
        lastFrameAtMs = null;
        frameCounter = 0;
        openedAtMs = System.currentTimeMillis();
        setState(currentState().withStatus(VideoStatus.CONNECTING, null));
        log.info("Vídeo", "Abriendo " + video.rtspUrl + " (" + video.rtspTransport.toUpperCase(Locale.ROOT) + ")");

        DefaultLoadControl loadControl = new DefaultLoadControl.Builder()
                // Small buffers: live supervision video, latency over smoothness.
                .setBufferDurationsMs(300, 1500, 150, 150)
                .setPrioritizeTimeOverSizeThresholds(true)
                .build();
        final ExoPlayer exo = new ExoPlayer.Builder(context).setLoadControl(loadControl).build();
        RtspMediaSource source = new RtspMediaSource.Factory()
                .setForceUseRtpTcp("tcp".equals(video.rtspTransport))
                .setTimeoutMs(8000)
                .createMediaSource(MediaItem.fromUri(video.rtspUrl));
        exo.setMediaSource(source);
        exo.setPlayWhenReady(true);

        // Called on the playback thread for every rendered frame.
        exo.setVideoFrameMetadataListener((presentationTimeUs, releaseTimeNs, format, mediaFormat) -> {
            lastFrameAtMs = System.currentTimeMillis();
            frameCounter += 1;
            if (frameCounter == 1) {
                handler.post(() -> {
                    if (player != exo) {
                        return;
                    }
                    consecutiveFailures = 0;
                    setState(VideoSupervisor.onFrame(currentState(), System.currentTimeMillis(),
                            format.width, format.height));
                    log.info("Vídeo", "Primer fotograma " + format.width + "x" + format.height);
                });
            }
        });

        exo.addListener(new Player.Listener() {
            @Override
            public void onPlayerError(@NonNull PlaybackException error) {
                if (player != exo) {
                    return; // event from a replaced player
                }
                String message = error.getErrorCodeName() + ": " + error.getMessage();
                setState(VideoSupervisor.onError(currentState(), message));
                scheduleRetry(message);
            }

            @Override
            public void onPlaybackStateChanged(int playbackState) {
                if (player != exo) {
                    return;
                }
                if (playbackState == Player.STATE_ENDED) {
                    log.warn("Vídeo", "Flujo finalizado por el servidor; reintentando");
                    setState(VideoSupervisor.onError(currentState(), "STATE_ENDED"));
                    scheduleRetry("STATE_ENDED");
                }
            }

            @Override
            public void onVideoSizeChanged(@NonNull VideoSize videoSize) {
                if (videoSize.width > 0) {
                    setState(currentState().withSize(videoSize.width, videoSize.height));
                }
            }
        });
        exo.prepare();
        player = exo;
        playerLiveData.setValue(exo);
    }

    /** Reopens the session after a delay that grows while no frame arrives. */
    private void scheduleRetry(String reason) {
        consecutiveFailures += 1;
        long delay = VideoSupervisor.retryDelayMs(retryDelayMs, consecutiveFailures);
        log.error("Vídeo", reason + ". Reintento en " + delay + " ms");
        handler.removeCallbacks(retry);
        handler.postDelayed(retry, delay);
    }

    /** Stops playback and releases the decoder (called from onStop). */
    public void stop() {
        handler.removeCallbacks(retry);
        handler.removeCallbacks(ticker);
        openedAtMs = null;
        releasePlayer();
        if (currentState().status != VideoStatus.IDLE) {
            log.info("Vídeo", "Reproducción detenida");
        }
        setState(currentState().withStatus(VideoStatus.IDLE, null));
    }

    private void releasePlayer() {
        playerLiveData.setValue(null);
        if (player != null) {
            player.release();
            player = null;
        }
    }

    private void setState(VideoState value) {
        state.setValue(value);
    }
}
