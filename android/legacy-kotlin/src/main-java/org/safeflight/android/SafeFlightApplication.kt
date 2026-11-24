package org.safeflight.android

import android.app.Application
import android.content.Context
import androidx.core.content.edit
import org.safeflight.android.config.KeyValueStore
import org.safeflight.android.config.ProfileRepository
import org.safeflight.android.diagnostics.DiagnosticsLog
import org.safeflight.android.mavlink.MavlinkClient
import org.safeflight.android.mission.DemoMissionRepository
import org.safeflight.android.mission.MissionRepository

/** Manual dependency container (no DI framework needed for the MVP). */
class AppContainer(context: Context) {
    val log = DiagnosticsLog()
    val profiles: ProfileRepository = ProfileRepository(SharedPreferencesStore(context)).load()
    val mavlink = MavlinkClient(log)
    val missions: MissionRepository = DemoMissionRepository()

    init {
        profiles.lastWarning?.let { log.warn("Perfiles", it) }
        log.info("App", "SafeFlight ${BuildConfig.VERSION_NAME} iniciado; perfil activo: ${profiles.active.name}")
    }
}

private class SharedPreferencesStore(context: Context) : KeyValueStore {
    private val prefs = context.getSharedPreferences("safeflight", Context.MODE_PRIVATE)
    override fun getString(key: String): String? = prefs.getString(key, null)
    override fun putString(key: String, value: String) {
        prefs.edit { putString(key, value) }
    }
}

class SafeFlightApplication : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }
}
