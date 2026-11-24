package org.safeflight.android.mavlink;

import java.util.HashMap;
import java.util.Map;

/** ArduCopter custom_mode table (same table as SafeFlight Desktop). */
public final class ArduCopterModes {
    private static final Map<Long, String> NAMES = new HashMap<>();

    static {
        String[][] table = {
            {"0", "STABILIZE"}, {"1", "ACRO"}, {"2", "ALT_HOLD"}, {"3", "AUTO"}, {"4", "GUIDED"},
            {"5", "LOITER"}, {"6", "RTL"}, {"7", "CIRCLE"}, {"9", "LAND"}, {"11", "DRIFT"},
            {"13", "SPORT"}, {"14", "FLIP"}, {"15", "AUTOTUNE"}, {"16", "POSHOLD"}, {"17", "BRAKE"},
            {"18", "THROW"}, {"19", "AVOID_ADSB"}, {"20", "GUIDED_NOGPS"}, {"21", "SMART_RTL"},
            {"22", "FLOWHOLD"}, {"23", "FOLLOW"}, {"24", "ZIGZAG"}, {"25", "SYSTEMID"},
            {"26", "AUTOROTATE"}, {"27", "AUTO_RTL"},
        };
        for (String[] row : table) {
            NAMES.put(Long.parseLong(row[0]), row[1]);
        }
    }

    private ArduCopterModes() {
    }

    /** Mode name, or {@code UNKNOWN(n)} so that an unknown mode is never shown as valid. */
    public static String name(long customMode) {
        String name = NAMES.get(customMode);
        return name != null ? name : "UNKNOWN(" + customMode + ")";
    }
}
