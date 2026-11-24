package org.safeflight.android.control;

import org.safeflight.android.state.LinkState;
import org.safeflight.android.state.LinkStatus;
import org.safeflight.android.state.TelemetryState;

import java.util.ArrayList;
import java.util.List;

/**
 * Single decision point for every vehicle command.
 *
 * <p>Physical commands are disabled at compile time ({@link #PHYSICAL_COMMANDS_ENABLED}).
 * The pre-conditions are still evaluated so that the operator sees why a
 * command would be refused, and so that a future implementation keeps one
 * audited entry point (authorisation, confirmation, vehicle state, ACK with
 * timeout, no duplicate commands). Independently of this gate, the MAVLink
 * layer contains no command encoder: the only frame the app can send is the
 * optional GCS heartbeat.
 */
public final class CommandGate {
    public static final boolean PHYSICAL_COMMANDS_ENABLED = false;

    public static final String DISABLED_REASON =
            "Controles deshabilitados: pendientes de pruebas SITL, análisis de seguridad y autorización operativa";

    private CommandGate() {
    }

    public static CommandDecision evaluate(FlightCommand command, TelemetryState telemetry, LinkState link) {
        List<String> reasons = new ArrayList<>();
        if (!PHYSICAL_COMMANDS_ENABLED) {
            reasons.add(DISABLED_REASON);
        }
        if (link.status != LinkStatus.CONNECTED) {
            reasons.add("Sin telemetría MAVLink vigente");
        }
        if (telemetry.vehicleSystemId == null) {
            reasons.add("Vehículo no identificado");
        }
        switch (command) {
            case ARM:
                if (Boolean.TRUE.equals(telemetry.armed)) {
                    reasons.add("El vehículo ya está armado");
                }
                break;
            case DISARM:
            case LAND:
                if (Boolean.FALSE.equals(telemetry.armed)) {
                    reasons.add("El vehículo no está armado");
                }
                break;
            default:
                break;
        }
        if (reasons.isEmpty() && PHYSICAL_COMMANDS_ENABLED) {
            return CommandDecision.allowed();
        }
        return CommandDecision.blocked(reasons);
    }
}
