package org.safeflight.android.state;

/**
 * Pure state machine for link supervision. Time is passed in as a parameter,
 * which makes the thresholds testable without sockets or real delays.
 */
public final class LinkSupervisor {
    private final long staleAfterMs;
    private final long lostAfterMs;

    public LinkSupervisor(long staleAfterMs) {
        this.staleAfterMs = staleAfterMs;
        this.lostAfterMs = staleAfterMs * 3;
    }

    public long getLostAfterMs() {
        return lostAfterMs;
    }

    public LinkState evaluate(boolean connectionRequested, String socketError, Long lastHeartbeatAtMs,
                              long nowMs, LinkState previous) {
        if (!connectionRequested) {
            return previous.withStatus(LinkStatus.DISCONNECTED, null);
        }
        if (socketError != null) {
            return previous.withError(LinkStatus.ERROR, socketError);
        }
        if (lastHeartbeatAtMs == null) {
            return previous.withStatus(LinkStatus.WAITING_HEARTBEAT, null);
        }
        long age = Math.max(0, nowMs - lastHeartbeatAtMs);
        LinkStatus status;
        if (age > lostAfterMs) {
            status = LinkStatus.LOST;
        } else if (age > staleAfterMs) {
            status = LinkStatus.STALE;
        } else {
            status = LinkStatus.CONNECTED;
        }
        return previous.withStatus(status, age);
    }
}
