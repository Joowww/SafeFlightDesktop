package org.safeflight.android;

import android.content.Context;
import android.content.SharedPreferences;

import org.safeflight.android.config.KeyValueStore;

/** {@link KeyValueStore} backed by the private preferences file {@code safeflight.xml}. */
final class SharedPreferencesStore implements KeyValueStore {
    private final SharedPreferences prefs;

    SharedPreferencesStore(Context context) {
        prefs = context.getSharedPreferences("safeflight", Context.MODE_PRIVATE);
    }

    @Override
    public String getString(String key) {
        return prefs.getString(key, null);
    }

    @Override
    public void putString(String key, String value) {
        prefs.edit().putString(key, value).apply();
    }
}
