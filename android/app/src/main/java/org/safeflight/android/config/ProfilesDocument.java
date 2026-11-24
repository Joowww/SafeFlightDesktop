package org.safeflight.android.config;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * The stored collection of profiles plus the active one. Immutable: the
 * repository creates a new document on every change, so the UI can detect a
 * change simply by comparing references.
 */
public final class ProfilesDocument {
    public final int schemaVersion;
    public final String activeProfileId;
    public final List<ConnectionProfile> profiles;

    public ProfilesDocument(int schemaVersion, String activeProfileId, List<ConnectionProfile> profiles) {
        this.schemaVersion = schemaVersion;
        this.activeProfileId = activeProfileId;
        this.profiles = Collections.unmodifiableList(new ArrayList<>(profiles));
    }

    /** Profile with this id, or {@code null}. */
    public ConnectionProfile find(String id) {
        for (ConnectionProfile p : profiles) {
            if (p.id.equals(id)) {
                return p;
            }
        }
        return null;
    }

    /** Active profile, falling back to the first one. */
    public ConnectionProfile active() {
        ConnectionProfile p = find(activeProfileId);
        return p != null ? p : profiles.get(0);
    }
}
