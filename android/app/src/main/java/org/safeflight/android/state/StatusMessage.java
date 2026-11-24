package org.safeflight.android.state;

/** STATUSTEXT received from the autopilot. */
public final class StatusMessage {
    public final int severity;
    public final String text;
    public final long receivedAtMs;

    public StatusMessage(int severity, String text, long receivedAtMs) {
        this.severity = severity;
        this.text = text;
        this.receivedAtMs = receivedAtMs;
    }
}
