package org.safeflight.android.config;

/**
 * Storage abstraction: SharedPreferences in the app ({@code SharedPreferencesStore}),
 * a simple map in unit tests.
 */
public interface KeyValueStore {
    /** Stored value, or {@code null}. */
    String getString(String key);

    void putString(String key, String value);
}
