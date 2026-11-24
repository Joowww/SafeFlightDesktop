package org.safeflight.android.diagnostics;

/** One line of the diagnostics log. */
public final class LogEntry {
    public final long atMs;
    public final LogLevel level;
    public final String source;
    public final String message;

    public LogEntry(long atMs, LogLevel level, String source, String message) {
        this.atMs = atMs;
        this.level = level;
        this.source = source;
        this.message = message;
    }
}
