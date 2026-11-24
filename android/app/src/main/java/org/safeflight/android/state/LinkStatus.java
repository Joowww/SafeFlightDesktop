package org.safeflight.android.state;

/** Telemetry link states derived only from received vehicle heartbeats. */
public enum LinkStatus {
    /** No connection requested. */
    DISCONNECTED,
    /** Socket open, no vehicle heartbeat received yet. */
    WAITING_HEARTBEAT,
    /** Last heartbeat younger than the stale threshold. */
    CONNECTED,
    /** Heartbeat older than {@code telemetry_stale_s}: values may be outdated. */
    STALE,
    /** Heartbeat older than 3 x {@code telemetry_stale_s}: link considered lost. */
    LOST,
    /** Socket or configuration error; a reconnection is scheduled. */
    ERROR,
}
