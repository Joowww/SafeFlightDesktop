package org.safeflight.android.config;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

/**
 * Converts profiles to and from the JSON layout of
 * shared/schemas/connection-profiles.schema.json (snake_case keys).
 *
 * <p>Reading: unknown keys are ignored and missing keys take the default
 * value. A profile without "id" or "name", or a value of the wrong type,
 * raises {@link JSONException} (the repository then restores the defaults).
 * Writing: every field is written, including defaults.
 */
public final class ProfileJson {

    private ProfileJson() {
    }

    // ------------------------------------------------------------------ write
    public static String toJson(ProfilesDocument doc) {
        try {
            JSONObject root = new JSONObject();
            root.put("schema_version", doc.schemaVersion);
            root.put("active_profile_id", doc.activeProfileId);
            JSONArray profiles = new JSONArray();
            for (ConnectionProfile p : doc.profiles) {
                profiles.put(profileToJson(p));
            }
            root.put("profiles", profiles);
            return root.toString(2);
        } catch (JSONException e) {
            throw new IllegalStateException("profile serialization failed", e);
        }
    }

    static JSONObject profileToJson(ConnectionProfile p) throws JSONException {
        JSONObject m = new JSONObject();
        m.put("transport", p.mavlink.transport);
        m.put("local_host", p.mavlink.localHost);
        m.put("local_port", p.mavlink.localPort);
        m.put("remote_host", p.mavlink.remoteHost);
        m.put("remote_port", p.mavlink.remotePort);
        m.put("serial_device", p.mavlink.serialDevice);
        m.put("baud_rate", p.mavlink.baudRate);
        m.put("connection_string", p.mavlink.connectionString);
        m.put("send_gcs_heartbeat", p.mavlink.sendGcsHeartbeat);

        JSONObject v = new JSONObject();
        v.put("mode", p.video.mode);
        v.put("rtp_udp_port", p.video.rtpUdpPort);
        v.put("rtsp_url", p.video.rtspUrl);
        v.put("rtsp_transport", p.video.rtspTransport);

        JSONObject t = new JSONObject();
        t.put("connect_timeout_s", p.timeouts.connectTimeoutS);
        t.put("heartbeat_timeout_s", p.timeouts.heartbeatTimeoutS);
        t.put("telemetry_stale_s", p.timeouts.telemetryStaleS);
        t.put("video_stale_s", p.timeouts.videoStaleS);
        t.put("video_reconnect_interval_s", p.timeouts.videoReconnectIntervalS);

        JSONObject d = new JSONObject();
        d.put("verbose_logging", p.diagnostics.verboseLogging);

        JSONObject o = new JSONObject();
        o.put("id", p.id);
        o.put("name", p.name);
        o.put("kind", p.kind);
        o.put("builtin", p.builtin);
        o.put("notes", p.notes);
        o.put("mavlink", m);
        o.put("video", v);
        o.put("timeouts", t);
        o.put("diagnostics", d);
        return o;
    }

    // ------------------------------------------------------------------- read
    public static ProfilesDocument fromJson(String text) throws JSONException {
        JSONObject root = new JSONObject(text);
        List<ConnectionProfile> profiles = new ArrayList<>();
        JSONArray array = root.has("profiles") ? root.getJSONArray("profiles") : new JSONArray();
        for (int i = 0; i < array.length(); i++) {
            profiles.add(profileFromJson(array.getJSONObject(i)));
        }
        return new ProfilesDocument(
                integer(root, "schema_version", 1),
                string(root, "active_profile_id", ""),
                profiles);
    }

    static ConnectionProfile profileFromJson(JSONObject o) throws JSONException {
        ConnectionProfile p = new ConnectionProfile(o.getString("id"), o.getString("name"));
        p.kind = string(o, "kind", p.kind);
        p.builtin = bool(o, "builtin", p.builtin);
        p.notes = string(o, "notes", p.notes);

        JSONObject m = object(o, "mavlink");
        p.mavlink.transport = string(m, "transport", p.mavlink.transport);
        p.mavlink.localHost = string(m, "local_host", p.mavlink.localHost);
        p.mavlink.localPort = integer(m, "local_port", p.mavlink.localPort);
        p.mavlink.remoteHost = string(m, "remote_host", p.mavlink.remoteHost);
        p.mavlink.remotePort = integer(m, "remote_port", p.mavlink.remotePort);
        p.mavlink.serialDevice = string(m, "serial_device", p.mavlink.serialDevice);
        p.mavlink.baudRate = integer(m, "baud_rate", p.mavlink.baudRate);
        p.mavlink.connectionString = string(m, "connection_string", p.mavlink.connectionString);
        p.mavlink.sendGcsHeartbeat = bool(m, "send_gcs_heartbeat", p.mavlink.sendGcsHeartbeat);

        JSONObject v = object(o, "video");
        p.video.mode = string(v, "mode", p.video.mode);
        p.video.rtpUdpPort = integer(v, "rtp_udp_port", p.video.rtpUdpPort);
        p.video.rtspUrl = string(v, "rtsp_url", p.video.rtspUrl);
        p.video.rtspTransport = string(v, "rtsp_transport", p.video.rtspTransport);

        JSONObject t = object(o, "timeouts");
        p.timeouts.connectTimeoutS = number(t, "connect_timeout_s", p.timeouts.connectTimeoutS);
        p.timeouts.heartbeatTimeoutS = number(t, "heartbeat_timeout_s", p.timeouts.heartbeatTimeoutS);
        p.timeouts.telemetryStaleS = number(t, "telemetry_stale_s", p.timeouts.telemetryStaleS);
        p.timeouts.videoStaleS = number(t, "video_stale_s", p.timeouts.videoStaleS);
        p.timeouts.videoReconnectIntervalS =
                number(t, "video_reconnect_interval_s", p.timeouts.videoReconnectIntervalS);

        JSONObject d = object(o, "diagnostics");
        p.diagnostics.verboseLogging = bool(d, "verbose_logging", p.diagnostics.verboseLogging);
        return p;
    }

    // Helpers: a missing or null key gives the default; a wrong type throws.
    private static boolean present(JSONObject o, String key) {
        return o.has(key) && !o.isNull(key);
    }

    private static JSONObject object(JSONObject o, String key) throws JSONException {
        return present(o, key) ? o.getJSONObject(key) : new JSONObject();
    }

    private static String string(JSONObject o, String key, String def) throws JSONException {
        if (!present(o, key)) {
            return def;
        }
        Object value = o.get(key);
        if (!(value instanceof String)) {
            throw new JSONException(key + " debe ser texto");
        }
        return (String) value;
    }

    private static int integer(JSONObject o, String key, int def) throws JSONException {
        return present(o, key) ? o.getInt(key) : def;
    }

    private static double number(JSONObject o, String key, double def) throws JSONException {
        return present(o, key) ? o.getDouble(key) : def;
    }

    private static boolean bool(JSONObject o, String key, boolean def) throws JSONException {
        return present(o, key) ? o.getBoolean(key) : def;
    }
}
