package org.safeflight.android.mavlink;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import org.safeflight.android.config.MavlinkSettings;
import org.safeflight.android.diagnostics.DiagnosticsLog;
import org.safeflight.android.state.LinkStatus;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.util.function.BooleanSupplier;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

/** Real UDP loopback: frames from the shared vectors sent to the client socket. */
public class MavlinkClientUdpTest {

    private static byte[] frame(String name) throws Exception {
        JSONArray vectors = SharedVectorsTest.vectors();
        for (int i = 0; i < vectors.length(); i++) {
            JSONObject v = vectors.getJSONObject(i);
            if (v.getString("name").equals(name)) {
                return SharedVectorsTest.hex(v.getString("frame_hex"));
            }
        }
        throw new AssertionError("vector not found: " + name);
    }

    private static int freePort() throws Exception {
        try (DatagramSocket s = new DatagramSocket()) {
            return s.getLocalPort() < 1024 ? freePort() : s.getLocalPort();
        }
    }

    /** Polls {@code condition} every 50 ms; fails after {@code timeoutMs}. */
    private static void waitFor(String what, long timeoutMs, BooleanSupplier condition) throws InterruptedException {
        long deadline = System.currentTimeMillis() + timeoutMs;
        while (!condition.getAsBoolean()) {
            if (System.currentTimeMillis() > deadline) {
                throw new AssertionError("timeout waiting for " + what);
            }
            Thread.sleep(50);
        }
    }

    private static MavlinkSettings listen(int port) {
        MavlinkSettings s = new MavlinkSettings();
        s.transport = "udp_listen";
        s.localHost = "127.0.0.1";
        s.localPort = port;
        return s;
    }

    @Test
    public void receivesTelemetryAndDetectsLossAndRecovery() throws Exception {
        int port = freePort();
        MavlinkClient client = new MavlinkClient(new DiagnosticsLog(), 200);
        client.connect(listen(port), 0.5);
        DatagramSocket sender = new DatagramSocket();
        InetAddress target = InetAddress.getByName("127.0.0.1");
        byte[] heartbeat = frame("heartbeat_armed_guided");
        byte[] battery = frame("sys_status_battery");
        try {
            long deadline = System.currentTimeMillis() + 5000;
            while (client.getLink().status != LinkStatus.CONNECTED || client.getTelemetry().batteryVoltageV == null) {
                assertTrue("no connection", System.currentTimeMillis() < deadline);
                sender.send(new DatagramPacket(heartbeat, heartbeat.length, target, port));
                sender.send(new DatagramPacket(battery, battery.length, target, port));
                Thread.sleep(100);
            }
            assertEquals(Boolean.TRUE, client.getTelemetry().armed);
            assertEquals("GUIDED", client.getTelemetry().flightMode);
            assertEquals(15.8, client.getTelemetry().batteryVoltageV, 1e-6);

            // Silence: STALE (> 0.5 s) then LOST (> 1.5 s).
            waitFor("STALE", 5000, () -> client.getLink().status == LinkStatus.STALE);
            waitFor("LOST", 5000, () -> client.getLink().status == LinkStatus.LOST);

            // Recovery without reconnecting the socket.
            deadline = System.currentTimeMillis() + 5000;
            while (client.getLink().status != LinkStatus.CONNECTED) {
                assertTrue("no recovery", System.currentTimeMillis() < deadline);
                sender.send(new DatagramPacket(heartbeat, heartbeat.length, target, port));
                Thread.sleep(100);
            }
            assertEquals(0, client.getLink().reconnectAttempts);
        } finally {
            sender.close();
            client.close();
        }
        assertEquals(LinkStatus.DISCONNECTED, client.getLink().status);
        assertTrue(!client.isRunning());
    }

    @Test
    public void bindErrorIsReportedAndRetried() throws Exception {
        // Occupy a UDP port so the client cannot bind it.
        DatagramSocket busy = new DatagramSocket(0, InetAddress.getByName("127.0.0.1"));
        MavlinkClient client = new MavlinkClient(new DiagnosticsLog(), 100);
        try {
            client.connect(listen(busy.getLocalPort()), 1.0);
            waitFor("ERROR", 5000, () -> client.getLink().status == LinkStatus.ERROR);
            waitFor("2 retries", 5000, () -> client.getLink().reconnectAttempts >= 2);
        } finally {
            client.close();
            busy.close();
        }
    }

    @Test
    public void reconnectingReplacesThePreviousSocket() throws Exception {
        int first = freePort();
        MavlinkClient client = new MavlinkClient(new DiagnosticsLog(), 100);
        try {
            client.connect(listen(first), 1.0);
            waitFor("socket open", 3000, () -> client.getLink().status == LinkStatus.WAITING_HEARTBEAT);
            int second = freePort();
            client.connect(listen(second), 1.0);
            // The first port is released: it can be bound again.
            Thread.sleep(300);
            try (DatagramSocket again = new DatagramSocket(first, InetAddress.getByName("127.0.0.1"))) {
                assertEquals(first, again.getLocalPort());
            }
        } finally {
            client.close();
        }
    }
}
