package org.safeflight.android.mavlink;

/** MAV_TYPE / MAV_AUTOPILOT / flag values needed to classify heartbeats. */
public final class MavConstants {
    public static final int MAV_TYPE_GCS = 6;
    public static final int MAV_TYPE_ONBOARD_CONTROLLER = 18;
    public static final int MAV_AUTOPILOT_ARDUPILOTMEGA = 3;
    public static final int MAV_AUTOPILOT_INVALID = 8;
    public static final int MAV_MODE_FLAG_SAFETY_ARMED = 0x80;
    public static final int MAV_MODE_FLAG_CUSTOM_MODE_ENABLED = 0x01;
    public static final int MAV_STATE_ACTIVE = 4;

    private MavConstants() {
    }
}
