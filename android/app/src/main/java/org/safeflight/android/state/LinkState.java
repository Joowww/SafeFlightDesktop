package org.safeflight.android.state;

/**
 * Immutable snapshot of the telemetry link. The {@code withX} methods return a
 * modified copy, so a snapshot that has been handed to the UI never changes.
 */
public final class LinkState {
    public final LinkStatus status;
    /** Age of the last vehicle heartbeat in ms, or {@code null} when unknown. */
    public final Long heartbeatAgeMs;
    public final String endpoint;
    public final String lastError;
    public final int reconnectAttempts;

    public LinkState() {
        this(LinkStatus.DISCONNECTED, null, "", null, 0);
    }

    public LinkState(LinkStatus status, Long heartbeatAgeMs, String endpoint, String lastError,
                     int reconnectAttempts) {
        this.status = status;
        this.heartbeatAgeMs = heartbeatAgeMs;
        this.endpoint = endpoint;
        this.lastError = lastError;
        this.reconnectAttempts = reconnectAttempts;
    }

    public LinkState withStatus(LinkStatus newStatus, Long newHeartbeatAgeMs) {
        return new LinkState(newStatus, newHeartbeatAgeMs, endpoint, lastError, reconnectAttempts);
    }

    public LinkState withError(LinkStatus newStatus, String error) {
        return new LinkState(newStatus, heartbeatAgeMs, endpoint, error, reconnectAttempts);
    }

    public LinkState withLastError(String error) {
        return new LinkState(status, heartbeatAgeMs, endpoint, error, reconnectAttempts);
    }

    public LinkState withReconnectAttempts(int attempts) {
        return new LinkState(status, heartbeatAgeMs, endpoint, lastError, attempts);
    }
}
