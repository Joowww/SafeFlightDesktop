package org.safeflight.android.mavlink

/** ArduCopter custom_mode table (same table as SafeFlight Desktop). */
object ArduCopterModes {
    private val NAMES = mapOf(
        0L to "STABILIZE", 1L to "ACRO", 2L to "ALT_HOLD", 3L to "AUTO", 4L to "GUIDED",
        5L to "LOITER", 6L to "RTL", 7L to "CIRCLE", 9L to "LAND", 11L to "DRIFT",
        13L to "SPORT", 14L to "FLIP", 15L to "AUTOTUNE", 16L to "POSHOLD", 17L to "BRAKE",
        18L to "THROW", 19L to "AVOID_ADSB", 20L to "GUIDED_NOGPS", 21L to "SMART_RTL",
        22L to "FLOWHOLD", 23L to "FOLLOW", 24L to "ZIGZAG", 25L to "SYSTEMID",
        26L to "AUTOROTATE", 27L to "AUTO_RTL",
    )

    /** Mode name, or `UNKNOWN(n)` so that an unknown mode is never shown as valid. */
    fun name(customMode: Long): String = NAMES[customMode] ?: "UNKNOWN($customMode)"
}
