package org.safeflight.android.control;

import org.junit.Test;
import org.safeflight.android.state.LinkState;
import org.safeflight.android.state.LinkStatus;
import org.safeflight.android.state.TelemetryState;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public class CommandGateTest {

    @Test
    public void physicalCommandsAreDisabledAtCompileTime() {
        assertFalse(CommandGate.PHYSICAL_COMMANDS_ENABLED);
    }

    @Test
    public void everyCommandIsBlockedEvenWithHealthyLink() {
        TelemetryState telemetry = TelemetryState.identifiedVehicle(1, 1, false);
        LinkState link = new LinkState(LinkStatus.CONNECTED, 100L, "udp://test", null, 0);
        for (FlightCommand command : FlightCommand.values()) {
            CommandDecision decision = CommandGate.evaluate(command, telemetry, link);
            assertTrue(command.name(), decision.isBlocked());
            assertFalse(command.name(), decision.isAllowed());
            assertTrue(decision.getReasons().contains(CommandGate.DISABLED_REASON));
        }
    }

    @Test
    public void everyCommandIsBlockedWhateverTheVehicleState() {
        LinkState link = new LinkState(LinkStatus.CONNECTED, 100L, "udp://test", null, 0);
        for (Boolean armed : new Boolean[] {true, false, null}) {
            TelemetryState telemetry = TelemetryState.identifiedVehicle(1, 1, armed);
            for (FlightCommand command : FlightCommand.values()) {
                assertTrue(command + " armed=" + armed, CommandGate.evaluate(command, telemetry, link).isBlocked());
            }
        }
    }

    @Test
    public void armAutoAndMissionCommandsAreAmongTheBlockedOnes() {
        // The commands that matter most for safety exist and are refused.
        for (FlightCommand command : new FlightCommand[] {
                FlightCommand.ARM, FlightCommand.TAKEOFF, FlightCommand.SET_MODE, FlightCommand.START_MISSION}) {
            assertTrue(CommandGate.evaluate(command, new TelemetryState(), new LinkState()).isBlocked());
        }
    }

    @Test
    public void preconditionsAreReported() {
        CommandDecision decision = CommandGate.evaluate(FlightCommand.LAND, new TelemetryState(), new LinkState());
        boolean telemetryReason = false;
        boolean vehicleReason = false;
        for (String reason : decision.getReasons()) {
            telemetryReason |= reason.contains("telemetría");
            vehicleReason |= reason.contains("Vehículo no identificado");
        }
        assertTrue(telemetryReason);
        assertTrue(vehicleReason);
    }
}
