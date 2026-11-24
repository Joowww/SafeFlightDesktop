package org.safeflight.android.mavlink

import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.flow.first
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Test
import org.safeflight.android.config.MavlinkSettings
import org.safeflight.android.diagnostics.DiagnosticsLog
import org.safeflight.android.state.LinkStatus
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress

/** Real UDP loopback: frames from the shared vectors sent to the client socket. */
class MavlinkClientUdpTest {
    private fun frame(name: String): ByteArray {
        val v = Json.parseToJsonElement(
            javaClass.classLoader!!.getResource("protocols/mavlink-test-vectors.json")!!.readText(),
        ).jsonObject.getValue("vectors").jsonArray.map { it.jsonObject }
            .first { it.getValue("name").jsonPrimitive.content == name }
        val s = v.getValue("frame_hex").jsonPrimitive.content
        return ByteArray(s.length / 2) { s.substring(it * 2, it * 2 + 2).toInt(16).toByte() }
    }

    private fun freePort(): Int = DatagramSocket().use { it.localPort }.let { if (it < 1024) freePort() else it }

    @Test
    fun receivesTelemetryAndDetectsLossAndRecovery() = runBlocking {
        val port = freePort()
        val client = MavlinkClient(DiagnosticsLog(), reconnectDelayMs = 200)
        client.connect(MavlinkSettings(transport = "udp_listen", localHost = "127.0.0.1", localPort = port), telemetryStaleS = 0.5)
        val sender = DatagramSocket()
        val target = InetAddress.getByName("127.0.0.1")
        fun send(bytes: ByteArray) = sender.send(DatagramPacket(bytes, bytes.size, target, port))
        try {
            withTimeout(5000) {
                while (client.link.value.status != LinkStatus.CONNECTED) {
                    send(frame("heartbeat_armed_guided"))
                    send(frame("sys_status_battery"))
                    kotlinx.coroutines.delay(100)
                }
            }
            val t = client.telemetry.first { it.batteryVoltageV != null }
            assertEquals(true, t.armed)
            assertEquals("GUIDED", t.flightMode)
            assertEquals(15.8, t.batteryVoltageV!!, 1e-6)

            // Silence: STALE (> 0.5 s) then LOST (> 1.5 s).
            withTimeout(5000) { client.link.first { it.status == LinkStatus.STALE } }
            withTimeout(5000) { client.link.first { it.status == LinkStatus.LOST } }

            // Recovery without reconnecting.
            withTimeout(5000) {
                while (client.link.value.status != LinkStatus.CONNECTED) {
                    send(frame("heartbeat_armed_guided"))
                    kotlinx.coroutines.delay(100)
                }
            }
            assertEquals(0, client.link.value.reconnectAttempts)
        } finally {
            sender.close()
            client.close()
        }
        assertEquals(LinkStatus.DISCONNECTED, client.link.value.status)
    }

    @Test
    fun bindErrorIsReportedAndRetried() = runBlocking {
        // Occupy a UDP port so the client cannot bind it.
        val busy = DatagramSocket(0, InetAddress.getByName("127.0.0.1"))
        val client = MavlinkClient(DiagnosticsLog(), reconnectDelayMs = 100)
        try {
            client.connect(
                MavlinkSettings(transport = "udp_listen", localHost = "127.0.0.1", localPort = busy.localPort),
                telemetryStaleS = 1.0,
            )
            withTimeout(5000) { client.link.first { it.status == LinkStatus.ERROR } }
            withTimeout(5000) { client.link.first { it.reconnectAttempts >= 2 } }
        } finally {
            client.close()
            busy.close()
        }
        Unit
    }
}
