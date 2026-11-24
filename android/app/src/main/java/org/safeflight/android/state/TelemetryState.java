package org.safeflight.android.state;

import java.util.ArrayList;
import java.util.List;

/**
 * Vehicle telemetry as shown to the operator.
 *
 * <p>Every field uses a boxed type ({@code Integer}, {@code Double}...):
 * {@code null} means "unknown" and is rendered as such. Values are never
 * invented and sentinel values defined by MAVLink (e.g. UINT16_MAX) map to
 * {@code null}. Conversions follow shared/protocols/mavlink-telemetry-contract.md.
 *
 * <p>Treat an instance as read-only: {@link TelemetryReducer} always works on a
 * {@link #copy()}, so a state already handed to the UI never changes.
 */
public final class TelemetryState {
    public Integer vehicleSystemId;
    public Integer vehicleComponentId;
    public Integer vehicleType;
    public Integer autopilot;
    public Boolean armed;
    public Long customMode;
    public String flightMode;
    public Integer systemStatus;
    public Double batteryVoltageV;
    public Double batteryCurrentA;
    public Integer batteryRemainingPct;
    public Double latDeg;
    public Double lonDeg;
    public Double altMslM;
    public Double relativeAltM;
    public Double headingDeg;
    public Double groundspeedMps;
    public Double airspeedMps;
    public Double climbMps;
    public Integer gpsFixType;
    public Integer satellitesVisible;
    public Double hdop;
    public Long lastHeartbeatAtMs;
    /** Newest first, at most {@link TelemetryReducer#MAX_MESSAGES}. */
    public List<StatusMessage> messages = new ArrayList<>();
    public CommandAckInfo lastCommandAck;

    /** Empty state: everything unknown. */
    public TelemetryState() {
    }

    /** State with an identified vehicle (used by tests and previews). */
    public static TelemetryState identifiedVehicle(int systemId, int componentId, Boolean armed) {
        TelemetryState s = new TelemetryState();
        s.vehicleSystemId = systemId;
        s.vehicleComponentId = componentId;
        s.armed = armed;
        return s;
    }

    /** Field-by-field copy (the message list is copied too). */
    public TelemetryState copy() {
        TelemetryState c = new TelemetryState();
        c.vehicleSystemId = vehicleSystemId;
        c.vehicleComponentId = vehicleComponentId;
        c.vehicleType = vehicleType;
        c.autopilot = autopilot;
        c.armed = armed;
        c.customMode = customMode;
        c.flightMode = flightMode;
        c.systemStatus = systemStatus;
        c.batteryVoltageV = batteryVoltageV;
        c.batteryCurrentA = batteryCurrentA;
        c.batteryRemainingPct = batteryRemainingPct;
        c.latDeg = latDeg;
        c.lonDeg = lonDeg;
        c.altMslM = altMslM;
        c.relativeAltM = relativeAltM;
        c.headingDeg = headingDeg;
        c.groundspeedMps = groundspeedMps;
        c.airspeedMps = airspeedMps;
        c.climbMps = climbMps;
        c.gpsFixType = gpsFixType;
        c.satellitesVisible = satellitesVisible;
        c.hdop = hdop;
        c.lastHeartbeatAtMs = lastHeartbeatAtMs;
        c.messages = new ArrayList<>(messages);
        c.lastCommandAck = lastCommandAck;
        return c;
    }
}
