package org.safeflight.android;

import android.content.Context;

import org.safeflight.android.config.ProfileRepository;
import org.safeflight.android.diagnostics.DiagnosticsLog;
import org.safeflight.android.mavlink.MavlinkClient;
import org.safeflight.android.mission.DemoMissionRepository;
import org.safeflight.android.mission.MissionRepository;

/**
 * Manual dependency container: the long-lived objects of the app, created once
 * in {@link SafeFlightApplication#onCreate()}. They survive screen changes and
 * activity recreation. (No dependency-injection framework is needed.)
 */
public final class AppContainer {
    public final DiagnosticsLog log;
    public final ProfileRepository profiles;
    public final MavlinkClient mavlink;
    public final MissionRepository missions;

    AppContainer(Context context) {
        log = new DiagnosticsLog();
        profiles = new ProfileRepository(new SharedPreferencesStore(context)).load();
        mavlink = new MavlinkClient(log);
        missions = new DemoMissionRepository();

        if (profiles.getLastWarning() != null) {
            log.warn("Perfiles", profiles.getLastWarning());
        }
        log.info("App", "SafeFlight " + BuildConfig.VERSION_NAME + " iniciado; perfil activo: "
                + profiles.getActive().name);
    }
}
