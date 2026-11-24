package org.safeflight.android;

import android.os.SystemClock;
import android.util.Log;
import android.view.View;
import android.view.ViewTreeObserver;

import androidx.fragment.app.Fragment;
import androidx.fragment.app.FragmentManager;

/**
 * Debug-only measurement of screen changes: time from the finger lifting off
 * the navigation rail (ACTION_UP event time) to the first frame in which the
 * destination screen is drawn visible. Logged as
 * {@code SafeFlight/Nav: <screen> <ms> ms}. Does nothing in release builds.
 */
final class NavTrace {
    private NavTrace() {
    }

    static void measure(View decor, FragmentManager fm, String tag, long tapUptimeMs) {
        if (!BuildConfig.DEBUG || tapUptimeMs <= 0) {
            return;
        }
        final ViewTreeObserver observer = decor.getViewTreeObserver();
        final boolean[] done = {false};
        observer.addOnDrawListener(new ViewTreeObserver.OnDrawListener() {
            @Override
            public void onDraw() {
                if (done[0]) {
                    return;
                }
                Fragment screen = fm.findFragmentByTag(tag);
                View view = screen != null ? screen.getView() : null;
                if (screen == null || !screen.isVisible() || view == null || view.getWidth() == 0) {
                    return;
                }
                done[0] = true;
                long ms = SystemClock.uptimeMillis() - tapUptimeMs;
                Log.d("SafeFlight/Nav", tag + " " + ms + " ms");
                ViewTreeObserver.OnDrawListener self = this;
                // A listener cannot be removed while the draw pass is running.
                decor.post(() -> {
                    if (observer.isAlive()) {
                        observer.removeOnDrawListener(self);
                    }
                });
            }
        });
    }
}
