package org.safeflight.android.mavlink

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.double
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.long
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.safeflight.android.state.TelemetryReducer
import org.safeflight.android.state.TelemetryState

/**
 * Android side of the shared MAVLink contract: the frames in
 * shared/protocols/mavlink-test-vectors.json were encoded by pymavlink and are
 * also checked by tests/desktop/test_mavlink_vectors.py.
 */
class SharedVectorsTest {
    private val vectors = Json.parseToJsonElement(
        checkNotNull(javaClass.classLoader!!.getResource("protocols/mavlink-test-vectors.json")) {
            "shared vectors not on the test classpath"
        }.readText(),
    ).jsonObject.getValue("vectors").jsonArray.map { it.jsonObject }

    private fun hex(s: String) = ByteArray(s.length / 2) { s.substring(it * 2, it * 2 + 2).toInt(16).toByte() }

    @Test
    fun allVectorsMatchContract() {
        assertTrue("expected at least 15 vectors", vectors.size >= 15)
        for (v in vectors) {
            val name = v.getValue("name").jsonPrimitive.content
            val messages = MavlinkParser().feed(hex(v.getValue("frame_hex").jsonPrimitive.content))
            val expected = v["expected"]
            if (expected == null || expected is JsonNull) {
                assertTrue("$name: corrupted frame must be rejected", messages.isEmpty())
                continue
            }
            val expectMode = v["expect"]?.jsonPrimitive?.content
            if (expectMode == "last") assertTrue("$name: must recover", messages.isNotEmpty())
            else assertEquals("$name: message count", 1, messages.size)
            val msg = messages.last()
            assertEquals("$name: msg id", v.getValue("msg_id").jsonPrimitive.int, msg.header.messageId)
            check(name, msg, expected.jsonObject)
        }
    }

    private fun check(name: String, msg: MavlinkMessage, e: JsonObject) {
        fun dbl(key: String): Double? = e[key]?.takeUnless { it is JsonNull }?.jsonPrimitive?.double
        fun int(key: String): Int? = e[key]?.takeUnless { it is JsonNull }?.jsonPrimitive?.int
        fun near(key: String, actual: Double?) {
            val exp = dbl(key)
            if (exp == null) assertNull("$name.$key", actual) else assertEquals("$name.$key", exp, actual!!, 1e-6)
        }
        when (msg) {
            is MavlinkMessage.Heartbeat -> {
                assertEquals("$name.system_id", int("system_id"), msg.header.systemId)
                assertEquals("$name.component_id", int("component_id"), msg.header.componentId)
                assertEquals("$name.armed", e.getValue("armed").jsonPrimitive.boolean, msg.armed)
                assertEquals("$name.custom_mode", e.getValue("custom_mode").jsonPrimitive.long, msg.customMode)
                assertEquals("$name.is_vehicle", e.getValue("is_vehicle").jsonPrimitive.boolean, msg.isVehicle)
                val state = TelemetryReducer.reduce(TelemetryState(), msg, 1000)
                val expectedMode = e["flight_mode"]?.takeUnless { it is JsonNull }?.jsonPrimitive?.content
                assertEquals("$name.flight_mode", expectedMode, state.flightMode)
                if (!msg.isVehicle) assertNull("$name: GCS heartbeat must not set link", state.lastHeartbeatAtMs)
            }
            else -> {
                val state = TelemetryReducer.reduce(vehicleLocked(msg.header.systemId), msg, 1000)
                when (msg) {
                    is MavlinkMessage.SysStatus -> {
                        near("battery_voltage_v", state.batteryVoltageV)
                        near("battery_current_a", state.batteryCurrentA)
                        assertEquals("$name.remaining", int("battery_remaining_pct"), state.batteryRemainingPct)
                    }
                    is MavlinkMessage.GlobalPositionInt -> {
                        near("lat_deg", state.latDeg); near("lon_deg", state.lonDeg)
                        near("alt_msl_m", state.altMslM); near("relative_alt_m", state.relativeAltM)
                        near("heading_deg", state.headingDeg)
                    }
                    is MavlinkMessage.VfrHud -> {
                        near("groundspeed_mps", state.groundspeedMps?.let { round4(it) })
                        near("climb_mps", state.climbMps?.let { round4(it) })
                        assertEquals("$name.heading", int("heading_deg"), msg.heading)
                        assertEquals("$name.throttle", int("throttle_pct"), msg.throttle)
                    }
                    is MavlinkMessage.GpsRawInt -> {
                        assertEquals("$name.fix", int("fix_type"), state.gpsFixType)
                        assertEquals("$name.sats", int("satellites_visible"), state.satellitesVisible)
                        near("hdop", state.hdop)
                    }
                    is MavlinkMessage.StatusText -> {
                        assertEquals("$name.text", e.getValue("text").jsonPrimitive.content, state.messages.first().text)
                        assertEquals("$name.severity", int("severity"), state.messages.first().severity)
                    }
                    is MavlinkMessage.CommandAck -> {
                        assertEquals(int("command"), state.lastCommandAck?.command)
                        assertEquals(int("result"), state.lastCommandAck?.result)
                    }
                    is MavlinkMessage.Heartbeat -> Unit
                }
            }
        }
    }

    // pymavlink reports float32 fields widened to double; the vectors store the
    // decimal value, so compare at float precision.
    private fun round4(v: Double) = Math.round(v * 10000.0) / 10000.0

    private fun vehicleLocked(sysId: Int) = TelemetryState(vehicleSystemId = sysId, vehicleComponentId = 1)

    @Suppress("unused")
    private fun JsonElement.asText() = jsonPrimitive.content
}
