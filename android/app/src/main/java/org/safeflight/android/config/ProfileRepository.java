package org.safeflight.android.config;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

/**
 * Persistent profile collection, stored as JSON under {@link #KEY}.
 * Corrupt or unreadable data never prevents start-up: the defaults are
 * restored, the old text is kept under {@link #KEY_CORRUPT_BACKUP} and a
 * warning is exposed through {@link #getLastWarning()}.
 *
 * <p>Every change creates a new {@link ProfilesDocument}, saves it and notifies
 * the listeners. Use it from the main thread.
 */
public final class ProfileRepository {
    public static final int SCHEMA_VERSION = 1;
    public static final String KEY = "connection_profiles_json";
    public static final String KEY_CORRUPT_BACKUP = "connection_profiles_json_corrupt";

    /** Notified after every change of the stored document. */
    public interface Listener {
        void onProfilesChanged(ProfilesDocument document);
    }

    private final KeyValueStore store;
    private final List<Listener> listeners = new CopyOnWriteArrayList<>();
    private ProfilesDocument document =
            new ProfilesDocument(SCHEMA_VERSION, "", Collections.<ConnectionProfile>emptyList());
    private String lastWarning;

    public ProfileRepository(KeyValueStore store) {
        this.store = store;
    }

    public void addListener(Listener listener) {
        listeners.add(listener);
    }

    public void removeListener(Listener listener) {
        listeners.remove(listener);
    }

    public ProfilesDocument getDocument() {
        return document;
    }

    public ConnectionProfile getActive() {
        return document.active();
    }

    public String getLastWarning() {
        return lastWarning;
    }

    /** Reads the stored profiles (or the defaults) and returns this repository. */
    public ProfileRepository load() {
        String raw = store.getString(KEY);
        ProfilesDocument parsed = null;
        if (raw != null) {
            try {
                parsed = ProfileJson.fromJson(raw);
            } catch (Exception e) {
                lastWarning = "Perfiles ilegibles; se restauran los valores por defecto ("
                        + e.getClass().getSimpleName() + ")";
                store.putString(KEY_CORRUPT_BACKUP, raw);
            }
        }
        if (parsed == null) {
            document = defaults();
        } else if (parsed.schemaVersion > SCHEMA_VERSION) {
            lastWarning = "Versión de perfiles no soportada (" + parsed.schemaVersion + "); valores por defecto";
            document = defaults();
        } else {
            document = withBuiltins(parsed);
        }
        persist();
        return this;
    }

    private static ProfilesDocument defaults() {
        return new ProfilesDocument(SCHEMA_VERSION, "siyi-local", DefaultProfiles.all());
    }

    /** Removes duplicated ids and adds any missing factory profile. */
    private static ProfilesDocument withBuiltins(ProfilesDocument doc) {
        List<ConnectionProfile> profiles = new ArrayList<>();
        for (ConnectionProfile p : doc.profiles) {
            if (findIn(profiles, p.id) == null) {
                profiles.add(p);
            }
        }
        for (ConnectionProfile builtin : DefaultProfiles.all()) {
            if (findIn(profiles, builtin.id) == null) {
                profiles.add(builtin);
            }
        }
        String active = findIn(profiles, doc.activeProfileId) != null ? doc.activeProfileId : profiles.get(0).id;
        return new ProfilesDocument(SCHEMA_VERSION, active, profiles);
    }

    public void select(String id) {
        if (document.find(id) == null) {
            throw new IllegalArgumentException("perfil desconocido: " + id);
        }
        update(new ProfilesDocument(SCHEMA_VERSION, id, document.profiles));
    }

    /** Saves a copy of {@code profile}; returns validation errors (nothing is saved if any). */
    public List<String> save(ConnectionProfile profile) {
        List<String> errors = ProfileValidator.validate(profile);
        if (!errors.isEmpty()) {
            return errors;
        }
        ConnectionProfile existing = document.find(profile.id);
        ConnectionProfile stored = profile.copy();
        stored.builtin = existing != null && existing.builtin;
        List<ConnectionProfile> profiles = new ArrayList<>(document.profiles);
        if (existing != null) {
            profiles.set(profiles.indexOf(existing), stored);
        } else {
            profiles.add(stored);
        }
        update(new ProfilesDocument(SCHEMA_VERSION, document.activeProfileId, profiles));
        return Collections.emptyList();
    }

    public ConnectionProfile duplicate(String id) {
        ConnectionProfile source = require(id);
        ConnectionProfile clone = source.copy();
        clone.id = uniqueId(source.id + "-copy");
        String name = source.name + " (copia)";
        clone.name = name.length() > 64 ? name.substring(0, 64) : name;
        clone.builtin = false;
        List<ConnectionProfile> profiles = new ArrayList<>(document.profiles);
        profiles.add(clone);
        update(new ProfilesDocument(SCHEMA_VERSION, document.activeProfileId, profiles));
        return clone;
    }

    /**
     * Resets only the profile {@code id}. Factory profiles get their factory
     * values; custom profiles keep their id and name and get the application
     * defaults (they have no original values to return to). Other profiles are
     * untouched.
     */
    public ConnectionProfile restore(String id) {
        ConnectionProfile current = require(id);
        ConnectionProfile reset = DefaultProfiles.builtin(id);
        if (reset == null) {
            reset = new ConnectionProfile(current.id, current.name);
        }
        List<ConnectionProfile> profiles = new ArrayList<>(document.profiles);
        profiles.set(profiles.indexOf(current), reset);
        update(new ProfilesDocument(SCHEMA_VERSION, document.activeProfileId, profiles));
        return reset;
    }

    /** Deletes a custom profile. Factory profiles cannot be deleted (use restore). */
    public void delete(String id) {
        ConnectionProfile profile = require(id);
        if (profile.builtin) {
            throw new IllegalArgumentException("los perfiles de fábrica no se eliminan; usar restaurar");
        }
        List<ConnectionProfile> profiles = new ArrayList<>(document.profiles);
        profiles.remove(profile);
        String active = document.activeProfileId.equals(id) ? profiles.get(0).id : document.activeProfileId;
        update(new ProfilesDocument(SCHEMA_VERSION, active, profiles));
    }

    public String newProfileId() {
        return uniqueId("custom");
    }

    private ConnectionProfile require(String id) {
        ConnectionProfile p = document.find(id);
        if (p == null) {
            throw new IllegalArgumentException("perfil desconocido: " + id);
        }
        return p;
    }

    private String uniqueId(String base) {
        String prefix = base.length() > 40 ? base.substring(0, 40) : base;
        String candidate = prefix;
        int n = 2;
        while (document.find(candidate) != null) {
            candidate = prefix + "-" + n++;
        }
        return candidate;
    }

    private static ConnectionProfile findIn(List<ConnectionProfile> profiles, String id) {
        for (ConnectionProfile p : profiles) {
            if (p.id.equals(id)) {
                return p;
            }
        }
        return null;
    }

    private void update(ProfilesDocument next) {
        document = next;
        persist();
    }

    private void persist() {
        store.putString(KEY, ProfileJson.toJson(document));
        for (Listener listener : listeners) {
            listener.onProfilesChanged(document);
        }
    }
}
