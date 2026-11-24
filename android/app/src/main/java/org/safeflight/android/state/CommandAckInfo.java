package org.safeflight.android.state;

/** Last COMMAND_ACK seen on the link (commands sent by another station). */
public final class CommandAckInfo {
    public final int command;
    public final int result;
    public final long receivedAtMs;

    public CommandAckInfo(int command, int result, long receivedAtMs) {
        this.command = command;
        this.result = result;
        this.receivedAtMs = receivedAtMs;
    }
}
