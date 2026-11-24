package org.safeflight.android.mavlink;

/** Reception counters shown in the Connection screen (immutable snapshot). */
public final class MavlinkCounters {
    public final long datagrams;
    public final long framesAccepted;
    public final long framesRejected;
    public final long gcsHeartbeatsSent;

    public MavlinkCounters() {
        this(0, 0, 0, 0);
    }

    public MavlinkCounters(long datagrams, long framesAccepted, long framesRejected, long gcsHeartbeatsSent) {
        this.datagrams = datagrams;
        this.framesAccepted = framesAccepted;
        this.framesRejected = framesRejected;
        this.gcsHeartbeatsSent = gcsHeartbeatsSent;
    }
}
