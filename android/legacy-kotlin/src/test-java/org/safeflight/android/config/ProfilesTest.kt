package org.safeflight.android.config

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

private class MemoryStore : KeyValueStore {
    val map = mutableMapOf<String, String>()
    override fun getString(key: String) = map[key]
    override fun putString(key: String, value: String) { map[key] = value }
}

class ProfilesTest {

    @Test
    fun defaultsAreValidOnAndroid() {
        DefaultProfiles.all().forEach { assertEquals(it.id, emptyList<String>(), ProfileValidator.validate(it)) }
    }

    @Test
    fun persistenceRoundTrip() {
        val store = MemoryStore()
        val repo = ProfileRepository(store).load()
        val edited = repo.active.copy(mavlink = repo.active.mavlink.copy(localPort = 14600))
        assertTrue(repo.save(edited).isEmpty())
        val reloaded = ProfileRepository(store).load()
        assertEquals(14600, reloaded.active.mavlink.localPort)
    }

    @Test
    fun corruptDataRestoresDefaultsAndKeepsBackup() {
        val store = MemoryStore()
        store.putString(ProfileRepository.KEY, "{ not json")
        val repo = ProfileRepository(store).load()
        assertEquals(4, repo.document.value.profiles.size)
        assertNotNull(repo.lastWarning)
        assertEquals("{ not json", store.map[ProfileRepository.KEY_CORRUPT_BACKUP])
    }

    @Test
    fun invalidProfileIsNotSaved() {
        val repo = ProfileRepository(MemoryStore()).load()
        val bad = repo.active.copy(mavlink = repo.active.mavlink.copy(localPort = 80))
        assertFalse(repo.save(bad).isEmpty())
        assertEquals(14550, repo.active.mavlink.localPort)
    }

    @Test
    fun udpConnectRequiresGcsHeartbeat() {
        val p = DefaultProfiles.all().first().let {
            it.copy(mavlink = it.mavlink.copy(transport = "udp_connect", remoteHost = "192.168.144.30", remotePort = 14550))
        }
        assertTrue(ProfileValidator.validate(p).any { it.contains("heartbeat") })
        assertTrue(ProfileValidator.validate(p.copy(mavlink = p.mavlink.copy(sendGcsHeartbeat = true))).isEmpty())
    }

    @Test
    fun duplicateRestoreDelete() {
        val repo = ProfileRepository(MemoryStore()).load()
        val clone = repo.duplicate("siyi-local")
        assertFalse(clone.builtin)
        repo.save(repo.document.value.profiles.first { it.id == "siyi-local" }.copy(name = "Cambiado"))
        assertEquals("SIYI LOCAL", repo.restore("siyi-local").name)
        assertTrue(runCatching { repo.delete("sitl") }.isFailure)
        repo.delete(clone.id)
        assertTrue(repo.document.value.profiles.none { it.id == clone.id })
    }

    @Test
    fun resetAffectsOnlyTheSelectedProfile() {
        val repo = ProfileRepository(MemoryStore()).load()
        val clone = repo.duplicate("siyi-local")
        repo.save(clone.copy(name = "Lab", mavlink = clone.mavlink.copy(localPort = 14600)))
        val sitlBefore = repo.document.value.profiles.first { it.id == "sitl" }
        val reset = repo.restore(clone.id)
        assertEquals("Lab", reset.name)
        assertEquals(14550, reset.mavlink.localPort)
        assertFalse(reset.builtin)
        assertEquals(sitlBefore, repo.document.value.profiles.first { it.id == "sitl" })
        assertEquals(5, repo.document.value.profiles.size)
    }

    /** The example file shared with Desktop must be readable on Android. */
    @Test
    fun sharedExampleIsReadable() {
        val text = javaClass.classLoader!!.getResource("examples/connection-profiles.example.json")!!.readText()
        val doc = ProfileJson.decodeFromString(ProfilesDocument.serializer(), text)
        assertEquals(1, doc.schemaVersion)
        val ids = doc.profiles.map { it.id }
        assertTrue(ids.containsAll(listOf("siyi-local", "cellular-vpn", "sitl")))
        // Desktop-only features are detected, not silently accepted.
        val rtpProfile = doc.profiles.first { it.video.mode == "rtp_udp" }
        assertTrue(ProfileValidator.validate(rtpProfile).any { it.startsWith("RTP/UDP") })
    }
}
