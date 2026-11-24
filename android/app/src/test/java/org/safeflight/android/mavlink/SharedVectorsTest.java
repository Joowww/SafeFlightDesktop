package org.safeflight.android.mavlink;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import org.safeflight.android.state.TelemetryReducer;
import org.safeflight.android.state.TelemetryState;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

/**
 * Android side of the shared MAVLink contract: the frames in
 * shared/protocols/mavlink-test-vectors.json were encoded by pymavlink and are
 * also checked by tests/desktop/test_mavlink_vectors.py.
 */
public class SharedVectorsTest {

    static String resource(String path) throws Exception {
        try (InputStream in = SharedVectorsTest.class.getClassLoader().getResourceAsStream(path)) {
            assertNotNull("shared contract not on the test classpath: " + path, in);
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    static JSONArray vectors() throws Exception {
        return new JSONObject(resource("protocols/mavlink-test-vectors.json")).getJSONArray("vectors");
    }

    static byte[] hex(String s) {
        byte[] out = new byte[s.length() / 2];
        for (int i = 0; i < out.length; i++) {
            out[i] = (byte) Integer.parseInt(s.substring(i * 2, i * 2 + 2), 16);
        }
        return out;
    }

    @Test
    public void allVectorsMatchContract() throws Exception {
        JSONArray vectors = vectors();
        assertTrue("expected at least 15 vectors", vectors.length() >= 15);
        for (int i = 0; i < vectors.length(); i++) {
            JSONObject v = vectors.getJSONObject(i);
            String name = v.getString("name");
            List<MavlinkMessage> messages = new MavlinkParser().feed(hex(v.getString("frame_hex")));
            if (!v.has("expected") || v.isNull("expected")) {
                assertTrue(name + ": corrupted frame must be rejected", messages.isEmpty());
                continue;
            }
            if ("last".equals(v.optString("expect", null))) {
                assertTrue(name + ": must recover", !messages.isEmpty());
            } else {
                assertEquals(name + ": message count", 1, messages.size());
            }
            MavlinkMessage msg = messages.get(messages.size() - 1);
            assertEquals(name + ": msg id", v.getInt("msg_id"), msg.header.messageId);
            check(name, msg, v.getJSONObject("expected"));
        }
    }

    private static Double dbl(JSONObject e, String key) throws Exception {
        return e.has(key) && !e.isNull(key) ? e.getDouble(key) : null;
    }

    private static Integer integer(JSONObject e, String key) throws Exception {
        return e.has(key) && !e.isNull(key) ? e.getInt(key) : null;
    }

    private static void near(String name, JSONObject e, String key, Double actual) throws Exception {
        Double expected = dbl(e, key);
        if (expected == null) {
            assertNull(name + "." + key, actual);
        } else {
            assertNotNull(name + "." + key, actual);
            assertEquals(name + "." + key, expected, actual, 1e-6);
        }
    }

    // pymavlink reports float32 fields widened to double; the vectors store the
    // decimal value, so compare at float precision.
    private static Double round4(Double v) {
        return v == null ? null : Math.round(v * 10000.0) / 10000.0;
    }

    private static void check(String name, MavlinkMessage msg, JSONObject e) throws Exception {
        if (msg instanceof MavlinkMessage.Heartbeat) {
            MavlinkMessage.Heartbeat hb = (MavlinkMessage.Heartbeat) msg;
            assertEquals(name + ".system_id", integer(e, "system_id"), Integer.valueOf(hb.header.systemId));
            assertEquals(name + ".component_id", integer(e, "component_id"), Integer.valueOf(hb.header.componentId));
            assertEquals(name + ".armed", e.getBoolean("armed"), hb.isArmed());
            assertEquals(name + ".custom_mode", e.getLong("custom_mode"), hb.customMode);
            assertEquals(name + ".is_vehicle", e.getBoolean("is_vehicle"), hb.isVehicle());
            TelemetryState state = TelemetryReducer.reduce(new TelemetryState(), hb, 1000);
            String expectedMode = e.has("flight_mode") && !e.isNull("flight_mode") ? e.getString("flight_mode") : null;
            assertEquals(name + ".flight_mode", expectedMode, state.flightMode);
            if (!hb.isVehicle()) {
                assertNull(name + ": GCS heartbeat must not set link", state.lastHeartbeatAtMs);
            }
            return;
        }
        TelemetryState state = TelemetryReducer.reduce(
                TelemetryState.identifiedVehicle(msg.header.systemId, 1, null), msg, 1000);
        if (msg instanceof MavlinkMessage.SysStatus) {
            near(name, e, "battery_voltage_v", state.batteryVoltageV);
            near(name, e, "battery_current_a", state.batteryCurrentA);
            assertEquals(name + ".remaining", integer(e, "battery_remaining_pct"), state.batteryRemainingPct);
        } else if (msg instanceof MavlinkMessage.GlobalPositionInt) {
            near(name, e, "lat_deg", state.latDeg);
            near(name, e, "lon_deg", state.lonDeg);
            near(name, e, "alt_msl_m", state.altMslM);
            near(name, e, "relative_alt_m", state.relativeAltM);
            near(name, e, "heading_deg", state.headingDeg);
        } else if (msg instanceof MavlinkMessage.VfrHud) {
            MavlinkMessage.VfrHud hud = (MavlinkMessage.VfrHud) msg;
            near(name, e, "groundspeed_mps", round4(state.groundspeedMps));
            near(name, e, "climb_mps", round4(state.climbMps));
            assertEquals(name + ".heading", integer(e, "heading_deg"), Integer.valueOf(hud.heading));
            assertEquals(name + ".throttle", integer(e, "throttle_pct"), Integer.valueOf(hud.throttle));
        } else if (msg instanceof MavlinkMessage.GpsRawInt) {
            assertEquals(name + ".fix", integer(e, "fix_type"), state.gpsFixType);
            assertEquals(name + ".sats", integer(e, "satellites_visible"), state.satellitesVisible);
            near(name, e, "hdop", state.hdop);
        } else if (msg instanceof MavlinkMessage.StatusText) {
            assertEquals(name + ".text", e.getString("text"), state.messages.get(0).text);
            assertEquals(name + ".severity", integer(e, "severity"), Integer.valueOf(state.messages.get(0).severity));
        } else if (msg instanceof MavlinkMessage.CommandAck) {
            assertNotNull(state.lastCommandAck);
            assertEquals(integer(e, "command"), Integer.valueOf(state.lastCommandAck.command));
            assertEquals(integer(e, "result"), Integer.valueOf(state.lastCommandAck.result));
        }
    }
}
