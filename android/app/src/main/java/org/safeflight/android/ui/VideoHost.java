package org.safeflight.android.ui;

import org.safeflight.android.video.VideoController;

/**
 * Implemented by {@code MainActivity}, which owns the video player (it is
 * bound to the activity lifecycle). Screens reach it with
 * {@code (VideoHost) requireActivity()}.
 */
public interface VideoHost {
    VideoController getVideo();

    /** Restarts the video with the active profile. */
    void restartVideo();

    void stopVideo();
}
