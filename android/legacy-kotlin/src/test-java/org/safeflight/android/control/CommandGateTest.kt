package org.safeflight.android.control

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.safeflight.android.state.LinkState
import org.safeflight.android.state.LinkStatus
import org.safeflight.android.state.TelemetryState

class CommandGateTest {
    @Test
    fun physicalCommandsAreDisabledAtCompileTime() {
        assertFalse(CommandGate.PHYSICAL_COMMANDS_ENABLED)
    }

    @Test
    fun everyCommandIsBlockedEvenWithHealthyLink() {
        val telemetry = TelemetryState(vehicleSystemId = 1, vehicleComponentId = 1, armed = false)
        val link = LinkState(status = LinkStatus.CONNECTED, heartbeatAgeMs = 100)
        for (command in FlightCommand.entries) {
            val decision = CommandGate.evaluate(command, telemetry, link)
            assertTrue(command.name, decision is CommandDecision.Blocked)
            assertTrue((decision as CommandDecision.Blocked).reasons.contains(CommandGate.DISABLED_REASON))
        }
    }

    @Test
    fun preconditionsAreReported() {
        val decision = CommandGate.evaluate(FlightCommand.LAND, TelemetryState(), LinkState()) as CommandDecision.Blocked
        assertTrue(decision.reasons.any { it.contains("telemetría") })
        assertTrue(decision.reasons.any { it.contains("Vehículo no identificado") })
    }
}
