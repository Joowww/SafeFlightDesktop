package org.safeflight.android.ui;

import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;

import androidx.lifecycle.LiveData;
import androidx.lifecycle.MutableLiveData;

/**
 * LiveData that is refreshed at most once every {@code intervalMs}. Values may
 * be offered from any thread at any rate (a real autopilot sends tens of
 * messages per second); the screen receives the latest one at a calm pace,
 * and the last value is never lost.
 */
final class ThrottledLiveData<T> {
    private final MutableLiveData<T> live;
    private final long intervalMs;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Object lock = new Object();
    private T pending;
    private boolean scheduled = false;
    private long lastEmitMs = 0;

    ThrottledLiveData(T initial, long intervalMs) {
        this.live = new MutableLiveData<>(initial);
        this.intervalMs = intervalMs;
    }

    LiveData<T> asLiveData() {
        return live;
    }

    /** Thread-safe. */
    void offer(T value) {
        synchronized (lock) {
            pending = value;
            if (scheduled) {
                return;
            }
            scheduled = true;
            long wait = Math.max(0, intervalMs - (SystemClock.uptimeMillis() - lastEmitMs));
            handler.postDelayed(this::emit, wait);
        }
    }

    private void emit() {
        T value;
        synchronized (lock) {
            value = pending;
            scheduled = false;
            lastEmitMs = SystemClock.uptimeMillis();
        }
        live.setValue(value);
    }
}
