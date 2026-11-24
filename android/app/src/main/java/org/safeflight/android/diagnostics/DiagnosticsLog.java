package org.safeflight.android.diagnostics;

import android.util.Log;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

/**
 * In-memory ring buffer (newest first) shown in the Connection screen and
 * mirrored to logcat with the tag {@code SafeFlight/<source>}. Thread-safe:
 * the MAVLink thread and the main thread write to it.
 */
public final class DiagnosticsLog {

    /** Notified (on the writing thread) after every new entry. */
    public interface Listener {
        void onLogChanged(List<LogEntry> entries);
    }

    private final int capacity;
    private final List<LogEntry> entries = new ArrayList<>();
    private final List<Listener> listeners = new CopyOnWriteArrayList<>();
    private volatile boolean verbose = false;

    public DiagnosticsLog() {
        this(200);
    }

    public DiagnosticsLog(int capacity) {
        this.capacity = capacity;
    }

    public void setVerbose(boolean verbose) {
        this.verbose = verbose;
    }

    public void addListener(Listener listener) {
        listeners.add(listener);
    }

    public void removeListener(Listener listener) {
        listeners.remove(listener);
    }

    /** Copy of the current entries, newest first. */
    public List<LogEntry> getEntries() {
        synchronized (entries) {
            return Collections.unmodifiableList(new ArrayList<>(entries));
        }
    }

    public void log(LogLevel level, String source, String message) {
        if (level == LogLevel.DEBUG && !verbose) {
            return;
        }
        List<LogEntry> snapshot;
        synchronized (entries) {
            entries.add(0, new LogEntry(System.currentTimeMillis(), level, source, message));
            while (entries.size() > capacity) {
                entries.remove(entries.size() - 1);
            }
            snapshot = Collections.unmodifiableList(new ArrayList<>(entries));
        }
        try {
            String tag = "SafeFlight/" + source;
            switch (level) {
                case DEBUG:
                    Log.d(tag, message);
                    break;
                case INFO:
                    Log.i(tag, message);
                    break;
                case WARN:
                    Log.w(tag, message);
                    break;
                default:
                    Log.e(tag, message);
                    break;
            }
        } catch (RuntimeException ignored) {
            // android.util.Log is not available in some JVM unit test setups.
        }
        for (Listener listener : listeners) {
            listener.onLogChanged(snapshot);
        }
    }

    public void info(String source, String message) {
        log(LogLevel.INFO, source, message);
    }

    public void warn(String source, String message) {
        log(LogLevel.WARN, source, message);
    }

    public void error(String source, String message) {
        log(LogLevel.ERROR, source, message);
    }

    public void debug(String source, String message) {
        log(LogLevel.DEBUG, source, message);
    }
}
