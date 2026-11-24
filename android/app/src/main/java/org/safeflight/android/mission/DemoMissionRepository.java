package org.safeflight.android.mission;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** Clearly labelled sample data so that the screen can be developed and reviewed. */
public final class DemoMissionRepository implements MissionRepository {
    private final List<Mission> missions;

    public DemoMissionRepository() {
        List<Mission> list = new ArrayList<>();
        list.add(new Mission("DEMO-001", "Inspección perímetro norte", "Dron", MissionStatus.PENDING,
                ExecutionMode.SIMULATED, "Pendiente de aprobación del operador", null, null, "—"));
        list.add(new Mission("DEMO-002", "Reconocimiento de ruta", "Rover", MissionStatus.APPROVED,
                ExecutionMode.SIMULATED, "Aprobada, a la espera de ejecución", null, null, "—"));
        list.add(new Mission("DEMO-003", "Búsqueda coordinada", "Dron + Rover", MissionStatus.RUNNING,
                ExecutionMode.SIMULATED, "Fase 2 de 4 (simulación Gazebo)", null, null, "—"));
        list.add(new Mission("DEMO-004", "Mapeo de zona A", "Dron", MissionStatus.COMPLETED,
                ExecutionMode.SIMULATED, "Completada", "12 waypoints cubiertos", null, "—"));
        list.add(new Mission("DEMO-005", "Entrega de muestra", "Rover", MissionStatus.FAILED,
                ExecutionMode.SIMULATED, "Abortada por el supervisor", null, "Obstáculo no evitable", "—"));
        missions = Collections.unmodifiableList(list);
    }

    @Override
    public MissionSourceKind getSource() {
        return MissionSourceKind.DEMO;
    }

    @Override
    public List<Mission> getMissions() {
        return missions;
    }
}
