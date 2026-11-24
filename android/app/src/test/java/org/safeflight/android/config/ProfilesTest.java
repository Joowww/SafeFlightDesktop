package org.safeflight.android.config;

import org.junit.Test;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

public class ProfilesTest {

    /** In-memory replacement of SharedPreferences. */
    static final class MemoryStore implements KeyValueStore {
        final Map<String, String> map = new HashMap<>();

        @Override
        public String getString(String key) {
            return map.get(key);
        }

        @Override
        public void putString(String key, String value) {
            map.put(key, value);
        }
    }

    private static boolean anyContains(List<String> list, String text) {
        for (String s : list) {
            if (s.contains(text)) {
                return true;
            }
        }
        return false;
    }

    @Test
    public void defaultsAreValidOnAndroid() {
        for (ConnectionProfile p : DefaultProfiles.all()) {
            assertTrue(p.id + ": " + ProfileValidator.validate(p), ProfileValidator.validate(p).isEmpty());
        }
    }

    @Test
    public void persistenceRoundTrip() {
        MemoryStore store = new MemoryStore();
        ProfileRepository repo = new ProfileRepository(store).load();
        ConnectionProfile edited = repo.getActive().copy();
        edited.mavlink.localPort = 14600;
        assertTrue(repo.save(edited).isEmpty());
        ProfileRepository reloaded = new ProfileRepository(store).load();
        assertEquals(14600, reloaded.getActive().mavlink.localPort);
    }

    @Test
    public void storedObjectsAreNotAliasedWithTheEditedCopy() {
        ProfileRepository repo = new ProfileRepository(new MemoryStore()).load();
        ConnectionProfile edited = repo.getActive().copy();
        edited.name = "No guardado";
        assertEquals("SIYI LOCAL", repo.getActive().name);
    }

    @Test
    public void corruptDataRestoresDefaultsAndKeepsBackup() {
        MemoryStore store = new MemoryStore();
        store.putString(ProfileRepository.KEY, "{ not json");
        ProfileRepository repo = new ProfileRepository(store).load();
        assertEquals(4, repo.getDocument().profiles.size());
        assertNotNull(repo.getLastWarning());
        assertEquals("{ not json", store.map.get(ProfileRepository.KEY_CORRUPT_BACKUP));
    }

    @Test
    public void wrongTypesAreTreatedAsCorrupt() {
        MemoryStore store = new MemoryStore();
        store.putString(ProfileRepository.KEY,
                "{\"schema_version\":1,\"profiles\":[{\"id\":\"x\",\"name\":\"X\",\"mavlink\":{\"local_port\":\"abc\"}}]}");
        ProfileRepository repo = new ProfileRepository(store).load();
        assertNotNull(repo.getLastWarning());
        assertEquals(4, repo.getDocument().profiles.size());
    }

    /**
     * org.json accepts numbers written as text ("80"). The value must still go
     * through ProfileValidator: dangerous or out-of-range values are refused,
     * whatever their JSON representation.
     */
    @Test
    public void numbersWrittenAsTextAreStillValidated() throws Exception {
        String[][] cases = {
            // {section, key, value as JSON text}
            {"mavlink", "local_port", "\"80\""},            // privileged port
            {"mavlink", "local_port", "\"70000\""},         // beyond 65535
            {"mavlink", "local_port", "\"-1\""},
            {"timeouts", "telemetry_stale_s", "\"1000\""},  // above 60 s
            {"timeouts", "telemetry_stale_s", "\"0\""},     // below 0.5 s
            {"timeouts", "telemetry_stale_s", "\"NaN\""},
            {"timeouts", "video_reconnect_interval_s", "\"Infinity\""},
            {"timeouts", "connect_timeout_s", "\"-5\""},
        };
        for (String[] c : cases) {
            String json = "{\"schema_version\":1,\"active_profile_id\":\"p\",\"profiles\":[{\"id\":\"p\","
                    + "\"name\":\"P\",\"video\":{\"mode\":\"none\"},\"" + c[0] + "\":{\"" + c[1] + "\":" + c[2] + "}}]}";
            ProfilesDocument doc = ProfileJson.fromJson(json);
            List<String> errors = ProfileValidator.validate(doc.profiles.get(0));
            assertFalse(c[1] + "=" + c[2] + " must be rejected", errors.isEmpty());
            assertTrue(c[1] + "=" + c[2] + ": " + errors, anyContains(errors, "fuera de rango"));
        }
        // A valid number written as text is read as that number and accepted.
        ProfilesDocument ok = ProfileJson.fromJson("{\"profiles\":[{\"id\":\"p\",\"name\":\"P\","
                + "\"video\":{\"mode\":\"none\"},\"mavlink\":{\"local_port\":\"14600\"}}]}");
        assertEquals(14600, ok.profiles.get(0).mavlink.localPort);
        assertTrue(ProfileValidator.validate(ok.profiles.get(0)).isEmpty());
    }

    @Test
    public void invalidStoredValuesAreNeverActivatedOnLoad() {
        // A stored profile with a dangerous value is loaded (it can be inspected and fixed)
        // but connectTelemetry() and save() refuse it through ProfileValidator.
        MemoryStore store = new MemoryStore();
        store.putString(ProfileRepository.KEY, "{\"schema_version\":1,\"active_profile_id\":\"p\",\"profiles\":"
                + "[{\"id\":\"p\",\"name\":\"P\",\"mavlink\":{\"local_port\":\"80\"}}]}");
        ProfileRepository repo = new ProfileRepository(store).load();
        assertFalse(ProfileValidator.validate(repo.getActive()).isEmpty());
        assertFalse(repo.save(repo.getActive().copy()).isEmpty());
    }

    @Test
    public void newerSchemaVersionFallsBackToDefaults() {
        MemoryStore store = new MemoryStore();
        store.putString(ProfileRepository.KEY, "{\"schema_version\":99,\"profiles\":[]}");
        ProfileRepository repo = new ProfileRepository(store).load();
        assertTrue(repo.getLastWarning().contains("99"));
        assertEquals("siyi-local", repo.getActive().id);
    }

    @Test
    public void invalidProfileIsNotSaved() {
        ProfileRepository repo = new ProfileRepository(new MemoryStore()).load();
        ConnectionProfile bad = repo.getActive().copy();
        bad.mavlink.localPort = 80;
        assertFalse(repo.save(bad).isEmpty());
        assertEquals(14550, repo.getActive().mavlink.localPort);
    }

    @Test
    public void udpConnectRequiresGcsHeartbeat() {
        ConnectionProfile p = DefaultProfiles.all().get(0);
        p.mavlink.transport = "udp_connect";
        p.mavlink.remoteHost = "192.168.144.30";
        p.mavlink.remotePort = 14550;
        assertTrue(anyContains(ProfileValidator.validate(p), "heartbeat"));
        p.mavlink.sendGcsHeartbeat = true;
        assertTrue(ProfileValidator.validate(p).isEmpty());
    }

    @Test
    public void duplicateRestoreDelete() {
        ProfileRepository repo = new ProfileRepository(new MemoryStore()).load();
        ConnectionProfile clone = repo.duplicate("siyi-local");
        assertFalse(clone.builtin);
        ConnectionProfile changed = repo.getDocument().find("siyi-local").copy();
        changed.name = "Cambiado";
        repo.save(changed);
        assertEquals("SIYI LOCAL", repo.restore("siyi-local").name);
        try {
            repo.delete("sitl");
            fail("factory profiles cannot be deleted");
        } catch (IllegalArgumentException expected) {
            // ok
        }
        repo.delete(clone.id);
        assertNull(repo.getDocument().find(clone.id));
    }

    @Test
    public void resetAffectsOnlyTheSelectedProfile() {
        ProfileRepository repo = new ProfileRepository(new MemoryStore()).load();
        ConnectionProfile clone = repo.duplicate("siyi-local");
        ConnectionProfile lab = clone.copy();
        lab.name = "Lab";
        lab.mavlink.localPort = 14600;
        repo.save(lab);
        ConnectionProfile sitlBefore = repo.getDocument().find("sitl");
        ConnectionProfile reset = repo.restore(clone.id);
        assertEquals("Lab", reset.name);
        assertEquals(14550, reset.mavlink.localPort);
        assertFalse(reset.builtin);
        assertEquals(sitlBefore, repo.getDocument().find("sitl"));
        assertEquals(5, repo.getDocument().profiles.size());
    }

    @Test
    public void listenersAreNotifiedOnEveryChange() {
        ProfileRepository repo = new ProfileRepository(new MemoryStore()).load();
        final int[] calls = {0};
        repo.addListener(doc -> calls[0]++);
        repo.select("sitl");
        repo.duplicate("sitl");
        assertEquals(2, calls[0]);
    }

    /** The example file shared with Desktop must be readable on Android. */
    @Test
    public void sharedExampleIsReadable() throws Exception {
        ProfilesDocument doc = ProfileJson.fromJson(readResource("examples/connection-profiles.example.json"));
        assertEquals(1, doc.schemaVersion);
        assertNotNull(doc.find("siyi-local"));
        assertNotNull(doc.find("cellular-vpn"));
        assertNotNull(doc.find("sitl"));
        // Desktop-only features are detected, not silently accepted.
        ConnectionProfile rtp = null;
        for (ConnectionProfile p : doc.profiles) {
            if ("rtp_udp".equals(p.video.mode)) {
                rtp = p;
            }
        }
        assertNotNull(rtp);
        boolean flagged = false;
        for (String e : ProfileValidator.validate(rtp)) {
            flagged |= e.startsWith("RTP/UDP");
        }
        assertTrue(flagged);
    }

    @Test
    public void jsonRoundTripKeepsEveryField() throws Exception {
        ConnectionProfile p = DefaultProfiles.all().get(2);
        p.mavlink.transport = "udp_connect";
        p.mavlink.remoteHost = "10.0.2.2";
        p.mavlink.remotePort = 14551;
        p.mavlink.sendGcsHeartbeat = true;
        p.video.mode = "none";
        p.video.rtspTransport = "udp";
        p.timeouts.telemetryStaleS = 1.5;
        p.diagnostics.verboseLogging = true;
        ProfilesDocument doc = new ProfilesDocument(1, p.id, java.util.Collections.singletonList(p));
        ProfilesDocument back = ProfileJson.fromJson(ProfileJson.toJson(doc));
        assertEquals(p, back.profiles.get(0));
        assertEquals(p.id, back.activeProfileId);
        // snake_case keys of the shared schema
        String json = ProfileJson.toJson(doc);
        assertTrue(json.contains("\"send_gcs_heartbeat\""));
        assertTrue(json.contains("\"telemetry_stale_s\""));
        assertTrue(json.contains("\"active_profile_id\""));
    }

    private static String readResource(String path) throws Exception {
        try (java.io.InputStream in = ProfilesTest.class.getClassLoader().getResourceAsStream(path)) {
            assertNotNull(path, in);
            return new String(in.readAllBytes(), java.nio.charset.StandardCharsets.UTF_8);
        }
    }
}
