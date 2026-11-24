package org.safeflight.android.config;

import java.util.Objects;

/**
 * Connection profile. The JSON layout follows
 * shared/schemas/connection-profiles.schema.json, also used by SafeFlight
 * Desktop (see {@link ProfileJson}). Android supports the UDP transports and
 * RTSP video only; other values are kept when read but rejected by
 * {@link ProfileValidator}.
 *
 * <p>Fields are public for readability. Objects stored in
 * {@link ProfileRepository} must not be modified directly: edit a
 * {@link #copy()} and save it.
 */
public final class ConnectionProfile {
    public String id;
    public String name;
    public String kind = "custom";
    public boolean builtin = false;
    public String notes = "";
    public MavlinkSettings mavlink = new MavlinkSettings();
    public VideoSettings video = new VideoSettings();
    public TimeoutSettings timeouts = new TimeoutSettings();
    public DiagnosticsSettings diagnostics = new DiagnosticsSettings();

    public ConnectionProfile(String id, String name) {
        this.id = id;
        this.name = name;
    }

    /** Deep copy. */
    public ConnectionProfile copy() {
        ConnectionProfile c = new ConnectionProfile(id, name);
        c.kind = kind;
        c.builtin = builtin;
        c.notes = notes;
        c.mavlink = mavlink.copy();
        c.video = video.copy();
        c.timeouts = timeouts.copy();
        c.diagnostics = diagnostics.copy();
        return c;
    }

    public String mavlinkEndpointLabel() {
        switch (mavlink.transport) {
            case "udp_listen":
                return "UDP escucha " + mavlink.localHost + ":" + mavlink.localPort;
            case "udp_connect":
                return "UDP → " + mavlink.remoteHost + ":" + mavlink.remotePort;
            default:
                return mavlink.transport + " (no soportado en Android)";
        }
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) {
            return true;
        }
        if (!(o instanceof ConnectionProfile)) {
            return false;
        }
        ConnectionProfile p = (ConnectionProfile) o;
        return builtin == p.builtin && Objects.equals(id, p.id) && Objects.equals(name, p.name)
                && Objects.equals(kind, p.kind) && Objects.equals(notes, p.notes)
                && Objects.equals(mavlink, p.mavlink) && Objects.equals(video, p.video)
                && Objects.equals(timeouts, p.timeouts) && Objects.equals(diagnostics, p.diagnostics);
    }

    @Override
    public int hashCode() {
        return Objects.hash(id, name, kind, builtin, notes, mavlink, video, timeouts, diagnostics);
    }
}
