package org.safeflight.android.state;

import org.safeflight.android.mavlink.ArduCopterModes;
import org.safeflight.android.mavlink.MavConstants;
import org.safeflight.android.mavlink.MavlinkMessage;

/** Applies decoded MAVLink messages to a {@link TelemetryState}. */
public final class TelemetryReducer {
    public static final int MAX_MESSAGES = 30;
    private static final int UINT16_MAX = 65535;

    private TelemetryReducer() {
    }

    /**
     * Returns a new state with {@code message} applied ({@code state} is never
     * modified). The first vehicle heartbeat selects the vehicle system and
     * component; messages from other systems (GCS, other vehicles) are ignored
     * so they cannot overwrite the vehicle state.
     */
    public static TelemetryState reduce(TelemetryState state, MavlinkMessage message, long nowMs) {
        int sysId = message.header.systemId;

        if (message instanceof MavlinkMessage.Heartbeat) {
            MavlinkMessage.Heartbeat hb = (MavlinkMessage.Heartbeat) message;
            if (!hb.isVehicle()) {
                return state;
            }
            int compId = hb.header.componentId;
            if (state.vehicleSystemId != null
                    && (state.vehicleSystemId != sysId || state.vehicleComponentId != compId)) {
                return state;
            }
            TelemetryState s = state.copy();
            s.vehicleSystemId = sysId;
            s.vehicleComponentId = compId;
            s.vehicleType = hb.type;
            s.autopilot = hb.autopilot;
            s.armed = hb.isArmed();
            s.customMode = hb.customMode;
            s.flightMode = hb.autopilot == MavConstants.MAV_AUTOPILOT_ARDUPILOTMEGA
                    ? ArduCopterModes.name(hb.customMode)
                    : "UNKNOWN(" + hb.customMode + ")";
            s.systemStatus = hb.systemStatus;
            s.lastHeartbeatAtMs = nowMs;
            return s;
        }

        // Everything else only counts once the vehicle is known, and only from it.
        if (state.vehicleSystemId == null || sysId != state.vehicleSystemId) {
            return state;
        }
        TelemetryState s = state.copy();
        if (message instanceof MavlinkMessage.SysStatus) {
            MavlinkMessage.SysStatus m = (MavlinkMessage.SysStatus) message;
            s.batteryVoltageV = m.voltageBatteryMv == UINT16_MAX ? null : m.voltageBatteryMv / 1000.0;
            s.batteryCurrentA = m.currentBatteryCa == -1 ? null : m.currentBatteryCa / 100.0;
            s.batteryRemainingPct = m.batteryRemaining == -1 ? null : m.batteryRemaining;
        } else if (message instanceof MavlinkMessage.GlobalPositionInt) {
            MavlinkMessage.GlobalPositionInt m = (MavlinkMessage.GlobalPositionInt) message;
            boolean noFix = m.latE7 == 0 && m.lonE7 == 0;
            s.latDeg = noFix ? null : m.latE7 / 1e7;
            s.lonDeg = noFix ? null : m.lonE7 / 1e7;
            s.altMslM = m.altMm / 1000.0;
            s.relativeAltM = m.relativeAltMm / 1000.0;
            s.headingDeg = m.hdgCdeg == UINT16_MAX ? null : m.hdgCdeg / 100.0;
        } else if (message instanceof MavlinkMessage.VfrHud) {
            MavlinkMessage.VfrHud m = (MavlinkMessage.VfrHud) message;
            s.groundspeedMps = finiteOrNull(m.groundspeed);
            s.airspeedMps = finiteOrNull(m.airspeed);
            s.climbMps = finiteOrNull(m.climb);
        } else if (message instanceof MavlinkMessage.GpsRawInt) {
            MavlinkMessage.GpsRawInt m = (MavlinkMessage.GpsRawInt) message;
            s.gpsFixType = m.fixType;
            s.satellitesVisible = m.satellitesVisible == 255 ? null : m.satellitesVisible;
            s.hdop = m.eph == UINT16_MAX ? null : m.eph / 100.0;
        } else if (message instanceof MavlinkMessage.StatusText) {
            MavlinkMessage.StatusText m = (MavlinkMessage.StatusText) message;
            s.messages.add(0, new StatusMessage(m.severity, m.text, nowMs));
            while (s.messages.size() > MAX_MESSAGES) {
                s.messages.remove(s.messages.size() - 1);
            }
        } else if (message instanceof MavlinkMessage.CommandAck) {
            MavlinkMessage.CommandAck m = (MavlinkMessage.CommandAck) message;
            s.lastCommandAck = new CommandAckInfo(m.command, m.result, nowMs);
        } else {
            return state;
        }
        return s;
    }

    private static Double finiteOrNull(float value) {
        return Float.isFinite(value) ? (double) value : null;
    }

    /** Human-readable GPS fix label; {@code null} when unknown. */
    public static String fixLabel(Integer fixType) {
        if (fixType == null) {
            return null;
        }
        switch (fixType) {
            case 0:
            case 1:
                return "SIN FIX";
            case 2:
                return "2D";
            case 3:
                return "3D";
            case 4:
                return "DGPS";
            case 5:
                return "RTK FLOAT";
            case 6:
                return "RTK FIX";
            default:
                return "TIPO " + fixType;
        }
    }
}
