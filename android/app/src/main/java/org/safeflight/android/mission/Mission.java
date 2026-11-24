package org.safeflight.android.mission;

/** One mission as shown in the Missions screen (read-only). */
public final class Mission {
    public final String id;
    public final String title;
    public final String vehicle;
    public final MissionStatus status;
    public final ExecutionMode executionMode;
    public final String summary;
    /** Result text, or {@code null}. */
    public final String result;
    /** Failure text, or {@code null}. */
    public final String error;
    public final String updatedAt;

    public Mission(String id, String title, String vehicle, MissionStatus status, ExecutionMode executionMode,
                   String summary, String result, String error, String updatedAt) {
        this.id = id;
        this.title = title;
        this.vehicle = vehicle;
        this.status = status;
        this.executionMode = executionMode;
        this.summary = summary;
        this.result = result;
        this.error = error;
        this.updatedAt = updatedAt;
    }
}
