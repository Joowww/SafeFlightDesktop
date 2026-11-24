package org.safeflight.android.config;

import java.util.Objects;

/** "timeouts" section of a connection profile (seconds). */
public final class TimeoutSettings {
    public double connectTimeoutS = 90.0;
    public double heartbeatTimeoutS = 30.0;
    public double telemetryStaleS = 3.0;
    public double videoStaleS = 2.0;
    public double videoReconnectIntervalS = 1.0;

    public TimeoutSettings copy() {
        TimeoutSettings c = new TimeoutSettings();
        c.connectTimeoutS = connectTimeoutS;
        c.heartbeatTimeoutS = heartbeatTimeoutS;
        c.telemetryStaleS = telemetryStaleS;
        c.videoStaleS = videoStaleS;
        c.videoReconnectIntervalS = videoReconnectIntervalS;
        return c;
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) {
            return true;
        }
        if (!(o instanceof TimeoutSettings)) {
            return false;
        }
        TimeoutSettings t = (TimeoutSettings) o;
        return connectTimeoutS == t.connectTimeoutS && heartbeatTimeoutS == t.heartbeatTimeoutS
                && telemetryStaleS == t.telemetryStaleS && videoStaleS == t.videoStaleS
                && videoReconnectIntervalS == t.videoReconnectIntervalS;
    }

    @Override
    public int hashCode() {
        return Objects.hash(connectTimeoutS, heartbeatTimeoutS, telemetryStaleS, videoStaleS, videoReconnectIntervalS);
    }
}
