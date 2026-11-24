package org.safeflight.android.mavlink;

/**
 * Decoded telemetry messages. Each supported MAVLink message is a small
 * immutable subclass with public final fields; use {@code instanceof} to tell
 * them apart, e.g. {@code if (message instanceof MavlinkMessage.Heartbeat)}.
 */
public abstract class MavlinkMessage {
    public final MavlinkHeader header;

    protected MavlinkMessage(MavlinkHeader header) {
        this.header = header;
    }

    /** HEARTBEAT (#0): vehicle type, armed flag and flight mode. */
    public static final class Heartbeat extends MavlinkMessage {
        public final long customMode;
        public final int type;
        public final int autopilot;
        public final int baseMode;
        public final int systemStatus;
        public final int mavlinkVersion;

        public Heartbeat(MavlinkHeader header, long customMode, int type, int autopilot, int baseMode,
                         int systemStatus, int mavlinkVersion) {
            super(header);
            this.customMode = customMode;
            this.type = type;
            this.autopilot = autopilot;
            this.baseMode = baseMode;
            this.systemStatus = systemStatus;
            this.mavlinkVersion = mavlinkVersion;
        }

        public boolean isArmed() {
            return (baseMode & MavConstants.MAV_MODE_FLAG_SAFETY_ARMED) != 0;
        }

        /** False for ground stations and companion computers: they never define the vehicle. */
        public boolean isVehicle() {
            return autopilot != MavConstants.MAV_AUTOPILOT_INVALID
                    && type != MavConstants.MAV_TYPE_GCS
                    && type != MavConstants.MAV_TYPE_ONBOARD_CONTROLLER;
        }
    }

    /** SYS_STATUS (#1): battery. */
    public static final class SysStatus extends MavlinkMessage {
        public final int voltageBatteryMv;
        public final int currentBatteryCa;
        public final int batteryRemaining;
        public final int dropRateComm;

        public SysStatus(MavlinkHeader header, int voltageBatteryMv, int currentBatteryCa, int batteryRemaining,
                         int dropRateComm) {
            super(header);
            this.voltageBatteryMv = voltageBatteryMv;
            this.currentBatteryCa = currentBatteryCa;
            this.batteryRemaining = batteryRemaining;
            this.dropRateComm = dropRateComm;
        }
    }

    /** GPS_RAW_INT (#24): fix type, satellites and HDOP. */
    public static final class GpsRawInt extends MavlinkMessage {
        public final int fixType;
        public final int satellitesVisible;
        public final int eph;
        public final int latE7;
        public final int lonE7;

        public GpsRawInt(MavlinkHeader header, int fixType, int satellitesVisible, int eph, int latE7, int lonE7) {
            super(header);
            this.fixType = fixType;
            this.satellitesVisible = satellitesVisible;
            this.eph = eph;
            this.latE7 = latE7;
            this.lonE7 = lonE7;
        }
    }

    /** GLOBAL_POSITION_INT (#33): fused position, altitudes and heading. */
    public static final class GlobalPositionInt extends MavlinkMessage {
        public final int latE7;
        public final int lonE7;
        public final int altMm;
        public final int relativeAltMm;
        public final int vxCms;
        public final int vyCms;
        public final int vzCms;
        public final int hdgCdeg;

        public GlobalPositionInt(MavlinkHeader header, int latE7, int lonE7, int altMm, int relativeAltMm,
                                 int vxCms, int vyCms, int vzCms, int hdgCdeg) {
            super(header);
            this.latE7 = latE7;
            this.lonE7 = lonE7;
            this.altMm = altMm;
            this.relativeAltMm = relativeAltMm;
            this.vxCms = vxCms;
            this.vyCms = vyCms;
            this.vzCms = vzCms;
            this.hdgCdeg = hdgCdeg;
        }
    }

    /** VFR_HUD (#74): speeds, climb rate, heading and throttle. */
    public static final class VfrHud extends MavlinkMessage {
        public final float airspeed;
        public final float groundspeed;
        public final float alt;
        public final float climb;
        public final int heading;
        public final int throttle;

        public VfrHud(MavlinkHeader header, float airspeed, float groundspeed, float alt, float climb, int heading,
                      int throttle) {
            super(header);
            this.airspeed = airspeed;
            this.groundspeed = groundspeed;
            this.alt = alt;
            this.climb = climb;
            this.heading = heading;
            this.throttle = throttle;
        }
    }

    /** COMMAND_ACK (#77): answer of the autopilot to a command (sent by another station). */
    public static final class CommandAck extends MavlinkMessage {
        public final int command;
        public final int result;

        public CommandAck(MavlinkHeader header, int command, int result) {
            super(header);
            this.command = command;
            this.result = result;
        }
    }

    /** STATUSTEXT (#253): text message of the autopilot. */
    public static final class StatusText extends MavlinkMessage {
        public final int severity;
        public final String text;

        public StatusText(MavlinkHeader header, int severity, String text) {
            super(header);
            this.severity = severity;
            this.text = text;
        }
    }
}
