package org.safeflight.android.control;

/** Flight operations shown in the UI. None of them is executable. */
public enum FlightCommand {
    ARM("ARM"),
    DISARM("DISARM"),
    TAKEOFF("TAKEOFF"),
    LAND("LAND"),
    SET_MODE("MODO"),
    START_MISSION("INICIAR MISIÓN"),
    ABORT_MISSION("DETENER MISIÓN");

    public final String label;

    FlightCommand(String label) {
        this.label = label;
    }
}
