package org.safeflight.android.config

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Storage abstraction so that the repository can be unit tested on the JVM. */
interface KeyValueStore {
    fun getString(key: String): String?
    fun putString(key: String, value: String)
}

/**
 * Persistent profile collection. Corrupt or unreadable data never prevents
 * start-up: defaults are restored and a warning is exposed.
 */
class ProfileRepository(private val store: KeyValueStore) {
    private val _document = MutableStateFlow(ProfilesDocument())
    val document: StateFlow<ProfilesDocument> = _document.asStateFlow()

    var lastWarning: String? = null
        private set

    val active: ConnectionProfile
        get() = _document.value.let { doc ->
            doc.profiles.firstOrNull { it.id == doc.activeProfileId } ?: doc.profiles.first()
        }

    fun load(): ProfileRepository {
        val raw = store.getString(KEY)
        val parsed = raw?.let {
            try {
                ProfileJson.decodeFromString(ProfilesDocument.serializer(), it)
            } catch (e: Exception) {
                lastWarning = "Perfiles ilegibles; se restauran los valores por defecto (${e.javaClass.simpleName})"
                store.putString(KEY_CORRUPT_BACKUP, it)
                null
            }
        }
        val doc = when {
            parsed == null -> ProfilesDocument(activeProfileId = "siyi-local", profiles = DefaultProfiles.all())
            parsed.schemaVersion > SCHEMA_VERSION -> {
                lastWarning = "Versión de perfiles no soportada (${parsed.schemaVersion}); valores por defecto"
                ProfilesDocument(activeProfileId = "siyi-local", profiles = DefaultProfiles.all())
            }
            else -> withBuiltins(parsed)
        }
        _document.value = doc
        persist()
        return this
    }

    private fun withBuiltins(doc: ProfilesDocument): ProfilesDocument {
        val unique = doc.profiles.distinctBy { it.id }
        val missing = DefaultProfiles.all().filter { builtin -> unique.none { it.id == builtin.id } }
        val profiles = unique + missing
        val active = if (profiles.any { it.id == doc.activeProfileId }) doc.activeProfileId else profiles.first().id
        return doc.copy(schemaVersion = SCHEMA_VERSION, activeProfileId = active, profiles = profiles)
    }

    fun select(id: String) {
        require(_document.value.profiles.any { it.id == id }) { "perfil desconocido: $id" }
        _document.value = _document.value.copy(activeProfileId = id)
        persist()
    }

    /** Saves [profile]; returns validation errors (nothing is saved if any). */
    fun save(profile: ConnectionProfile): List<String> {
        val errors = ProfileValidator.validate(profile)
        if (errors.isNotEmpty()) return errors
        val doc = _document.value
        val existing = doc.profiles.firstOrNull { it.id == profile.id }
        val stored = profile.copy(builtin = existing?.builtin ?: false)
        val profiles = if (existing != null) {
            doc.profiles.map { if (it.id == profile.id) stored else it }
        } else {
            doc.profiles + stored
        }
        _document.value = doc.copy(profiles = profiles)
        persist()
        return emptyList()
    }

    fun duplicate(id: String): ConnectionProfile {
        val source = _document.value.profiles.first { it.id == id }
        val clone = source.copy(id = uniqueId("${source.id}-copy"), name = "${source.name} (copia)".take(64), builtin = false)
        _document.value = _document.value.copy(profiles = _document.value.profiles + clone)
        persist()
        return clone
    }

    /**
     * Resets only the profile [id]. Factory profiles get their factory values;
     * custom profiles keep their id and name and get the application defaults
     * (they have no original values to return to). Other profiles are untouched.
     */
    fun restore(id: String): ConnectionProfile {
        val current = _document.value.profiles.first { it.id == id }
        val default = DefaultProfiles.builtin(id)
            ?: ConnectionProfile(id = current.id, name = current.name, kind = "custom", builtin = false)
        _document.value = _document.value.copy(profiles = _document.value.profiles.map { if (it.id == id) default else it })
        persist()
        return default
    }

    fun delete(id: String) {
        val doc = _document.value
        val profile = doc.profiles.first { it.id == id }
        require(!profile.builtin) { "los perfiles de fábrica no se eliminan; usar restaurar" }
        val profiles = doc.profiles.filterNot { it.id == id }
        val active = if (doc.activeProfileId == id) profiles.first().id else doc.activeProfileId
        _document.value = doc.copy(profiles = profiles, activeProfileId = active)
        persist()
    }

    fun newProfileId(): String = uniqueId("custom")

    private fun uniqueId(base: String): String {
        var candidate = base.take(40)
        var n = 2
        while (_document.value.profiles.any { it.id == candidate }) candidate = "${base.take(40)}-${n++}"
        return candidate
    }

    private fun persist() {
        store.putString(KEY, ProfileJson.encodeToString(ProfilesDocument.serializer(), _document.value))
    }

    companion object {
        const val SCHEMA_VERSION = 1
        const val KEY = "connection_profiles_json"
        const val KEY_CORRUPT_BACKUP = "connection_profiles_json_corrupt"
    }
}
