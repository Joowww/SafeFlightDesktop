package org.safeflight.android.control;

import java.util.Collections;
import java.util.List;

/**
 * Result of {@link CommandGate#evaluate}. A decision is either "blocked" with
 * at least one reason, or "allowed". "Allowed" cannot be produced while
 * {@link CommandGate#PHYSICAL_COMMANDS_ENABLED} is false.
 */
public final class CommandDecision {
    private final boolean allowed;
    private final List<String> reasons;

    private CommandDecision(boolean allowed, List<String> reasons) {
        this.allowed = allowed;
        this.reasons = Collections.unmodifiableList(reasons);
    }

    static CommandDecision blocked(List<String> reasons) {
        return new CommandDecision(false, reasons);
    }

    static CommandDecision allowed() {
        return new CommandDecision(true, Collections.<String>emptyList());
    }

    public boolean isAllowed() {
        return allowed;
    }

    public boolean isBlocked() {
        return !allowed;
    }

    /** Why the command is refused (empty only when allowed). */
    public List<String> getReasons() {
        return reasons;
    }
}
