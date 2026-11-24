package org.safeflight.android.mission;

import java.util.List;

/**
 * Read-only view of missions. The planned implementation will be a client of
 * the multi-agent supervisor (Hermes/LangGraph); see
 * docs/architecture/integration-points.md. No such client exists yet, and
 * Android does not import .plan files or execute missions.
 */
public interface MissionRepository {
    MissionSourceKind getSource();

    List<Mission> getMissions();
}
