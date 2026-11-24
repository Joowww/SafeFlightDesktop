package org.safeflight.android.config;

import java.util.Objects;

/** "mavlink" section of a connection profile (JSON keys in snake_case, see ProfileJson). */
public final class MavlinkSettings {
    /** "udp_listen" or "udp_connect" on Android; Desktop also uses serial/tcp. */
    public String transport = "udp_listen";
    public String localHost = "0.0.0.0";
    public int localPort = 14550;
    public String remoteHost = "";
    public int remotePort = 14550;
    public String serialDevice = "";
    public int baudRate = 57600;
    public String connectionString = "";
    /** Android only: send a GCS HEARTBEAT at 1 Hz (see GcsHeartbeatEncoder). */
    public boolean sendGcsHeartbeat = false;

    public MavlinkSettings copy() {
        MavlinkSettings c = new MavlinkSettings();
        c.transport = transport;
        c.localHost = localHost;
        c.localPort = localPort;
        c.remoteHost = remoteHost;
        c.remotePort = remotePort;
        c.serialDevice = serialDevice;
        c.baudRate = baudRate;
        c.connectionString = connectionString;
        c.sendGcsHeartbeat = sendGcsHeartbeat;
        return c;
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) {
            return true;
        }
        if (!(o instanceof MavlinkSettings)) {
            return false;
        }
        MavlinkSettings m = (MavlinkSettings) o;
        return localPort == m.localPort && remotePort == m.remotePort && baudRate == m.baudRate
                && sendGcsHeartbeat == m.sendGcsHeartbeat && Objects.equals(transport, m.transport)
                && Objects.equals(localHost, m.localHost) && Objects.equals(remoteHost, m.remoteHost)
                && Objects.equals(serialDevice, m.serialDevice) && Objects.equals(connectionString, m.connectionString);
    }

    @Override
    public int hashCode() {
        return Objects.hash(transport, localHost, localPort, remoteHost, remotePort, serialDevice, baudRate,
                connectionString, sendGcsHeartbeat);
    }
}
