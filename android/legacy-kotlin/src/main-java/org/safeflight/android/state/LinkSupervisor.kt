package org.safeflight.android.state

/** Telemetry link states derived only from received vehicle heartbeats. */
enum class LinkStatus {
    /** No connection requested. */
    DISCONNECTED,
    /** Socket open, no vehicle heartbeat received yet. */
    WAITING_HEARTBEAT,
    /** Last heartbeat younger than the stale threshold. */
    CONNECTED,
    /** Heartbeat older than `telemetry_stale_s`: values may be outdated. */
    STALE,
    /** Heartbeat older than 3 × `telemetry_stale_s`: link considered lost. */
    LOST,
    /** Socket or configuration error; a reconnection is scheduled. */
    ERROR,
}

data class LinkState(
    val status: LinkStatus = LinkStatus.DISCONNECTED,
    val heartbeatAgeMs: Long? = null,
    val endpoint: String = "",
    val lastError: String? = null,
    val reconnectAttempts: Int = 0,
)

/**
 * Pure state machine for link supervision. Time is injected, which makes the
 * thresholds testable without sockets or real delays.
 */
class LinkSupervisor(private val staleAfterMs: Long) {
    val lostAfterMs: Long = staleAfterMs * 3

    fun evaluate(
        connectionRequested: Boolean,
        socketError: String?,
        lastHeartbeatAtMs: Long?,
        nowMs: Long,
        previous: LinkState,
    ): LinkState {
        if (!connectionRequested) return previous.copy(status = LinkStatus.DISCONNECTED, heartbeatAgeMs = null)
        if (socketError != null) return previous.copy(status = LinkStatus.ERROR, lastError = socketError)
        if (lastHeartbeatAtMs == null) {
            return previous.copy(status = LinkStatus.WAITING_HEARTBEAT, heartbeatAgeMs = null)
        }
        val age = (nowMs - lastHeartbeatAtMs).coerceAtLeast(0)
        val status = when {
            age > lostAfterMs -> LinkStatus.LOST
            age > staleAfterMs -> LinkStatus.STALE
            else -> LinkStatus.CONNECTED
        }
        return previous.copy(status = status, heartbeatAgeMs = age)
    }
}
