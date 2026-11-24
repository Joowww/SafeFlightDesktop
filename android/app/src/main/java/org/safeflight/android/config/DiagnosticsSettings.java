package org.safeflight.android.config;

/** "diagnostics" section of a connection profile. */
public final class DiagnosticsSettings {
    public boolean verboseLogging = false;

    public DiagnosticsSettings copy() {
        DiagnosticsSettings c = new DiagnosticsSettings();
        c.verboseLogging = verboseLogging;
        return c;
    }

    @Override
    public boolean equals(Object o) {
        return o instanceof DiagnosticsSettings && ((DiagnosticsSettings) o).verboseLogging == verboseLogging;
    }

    @Override
    public int hashCode() {
        return verboseLogging ? 1 : 0;
    }
}
