package org.safeflight.android.mavlink;

import org.safeflight.android.config.MavlinkSettings;
import org.safeflight.android.diagnostics.DiagnosticsLog;
import org.safeflight.android.state.LinkState;
import org.safeflight.android.state.LinkStatus;
import org.safeflight.android.state.LinkSupervisor;
import org.safeflight.android.state.TelemetryReducer;
import org.safeflight.android.state.TelemetryState;

import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.net.SocketTimeoutException;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Receive-only MAVLink client over UDP.
 *
 * <ul>
 *   <li>{@code udp_listen}: binds a local port; the vehicle side (MAVProxy,
 *       mavlink-router) sends to this device.</li>
 *   <li>{@code udp_connect}: sends GCS heartbeats to a remote endpoint so it
 *       learns this device's address, then receives its telemetry.</li>
 * </ul>
 *
 * <p>Threads: one receive thread reads datagrams and updates the telemetry; a
 * supervisor task re-evaluates the link every 250 ms from the age of the last
 * vehicle heartbeat ({@link LinkSupervisor}). Socket errors trigger a
 * controlled reconnection after {@code reconnectDelayMs}. The client never
 * sends commands. Listeners are called on these background threads.
 */
public final class MavlinkClient {

    /** Receives every state change (on a background thread). */
    public interface Listener {
        void onTelemetry(TelemetryState telemetry);

        void onLink(LinkState link);

        void onCounters(MavlinkCounters counters);
    }

    private static final long SUPERVISION_PERIOD_MS = 250;

    private final DiagnosticsLog log;
    private final long reconnectDelayMs;
    private final List<Listener> listeners = new CopyOnWriteArrayList<>();
    /** Guards read-modify-write updates of {@link #link} (never held while waiting for threads). */
    private final Object linkLock = new Object();

    private volatile TelemetryState telemetry = new TelemetryState();
    private volatile LinkState link = new LinkState();
    private volatile MavlinkCounters counters = new MavlinkCounters();

    private volatile DatagramSocket socket;
    private volatile String socketError;
    private volatile boolean connectionRequested;
    private AtomicBoolean running;
    private Thread receiveThread;
    private ScheduledExecutorService supervisorExecutor;

    public MavlinkClient(DiagnosticsLog log) {
        this(log, 2000);
    }

    public MavlinkClient(DiagnosticsLog log, long reconnectDelayMs) {
        this.log = log;
        this.reconnectDelayMs = reconnectDelayMs;
    }

    public void addListener(Listener listener) {
        listeners.add(listener);
    }

    public void removeListener(Listener listener) {
        listeners.remove(listener);
    }

    public TelemetryState getTelemetry() {
        return telemetry;
    }

    public LinkState getLink() {
        return link;
    }

    public MavlinkCounters getCounters() {
        return counters;
    }

    public synchronized boolean isRunning() {
        return receiveThread != null && receiveThread.isAlive();
    }

    /** Starts receiving with {@code settings}; any previous connection is closed first. */
    public synchronized void connect(MavlinkSettings settings, double telemetryStaleS) {
        disconnectAndWait();
        LinkSupervisor supervisor = new LinkSupervisor((long) (telemetryStaleS * 1000));
        String endpoint;
        switch (settings.transport) {
            case "udp_listen":
                endpoint = "udp://" + settings.localHost + ":" + settings.localPort + " (escucha)";
                break;
            case "udp_connect":
                endpoint = "udp://" + settings.remoteHost + ":" + settings.remotePort + " (remoto)";
                break;
            default:
                endpoint = settings.transport;
                break;
        }
        setTelemetry(new TelemetryState());
        setCounters(new MavlinkCounters());
        socketError = null;
        connectionRequested = true;
        synchronized (linkLock) {
            setLink(new LinkState(LinkStatus.WAITING_HEARTBEAT, null, endpoint, null, 0));
        }
        log.info("MAVLink", "Conectando " + endpoint);

        final MavlinkSettings copy = settings.copy();
        final AtomicBoolean flag = new AtomicBoolean(true);
        running = flag;
        receiveThread = new Thread(() -> receiveLoop(copy, flag), "mavlink-receive");
        receiveThread.setDaemon(true);
        receiveThread.start();

        supervisorExecutor = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "mavlink-supervisor");
            t.setDaemon(true);
            return t;
        });
        supervisorExecutor.scheduleWithFixedDelay(() -> supervise(supervisor),
                0, SUPERVISION_PERIOD_MS, TimeUnit.MILLISECONDS);
    }

    private void supervise(LinkSupervisor supervisor) {
        synchronized (linkLock) {
            if (!connectionRequested) {
                return;
            }
            LinkState previous = link;
            LinkState next = supervisor.evaluate(connectionRequested, socketError, telemetry.lastHeartbeatAtMs,
                    System.currentTimeMillis(), previous);
            logTransition(previous.status, next);
            setLink(next);
        }
    }

    private void logTransition(LinkStatus previous, LinkState next) {
        if (previous == next.status) {
            return;
        }
        switch (next.status) {
            case CONNECTED:
                log.info("MAVLink", "Heartbeat del vehículo recibido");
                break;
            case STALE:
                log.warn("MAVLink", "Telemetría obsoleta (" + next.heartbeatAgeMs + " ms sin heartbeat)");
                break;
            case LOST:
                log.error("MAVLink", "Pérdida de telemetría (" + next.heartbeatAgeMs + " ms sin heartbeat)");
                break;
            case ERROR:
                log.error("MAVLink", "Error de enlace: " + next.lastError);
                break;
            default:
                break;
        }
    }

    private void receiveLoop(MavlinkSettings settings, AtomicBoolean running) {
        MavlinkParser parser = new MavlinkParser();
        GcsHeartbeatEncoder encoder = new GcsHeartbeatEncoder();
        byte[] buffer = new byte[2048];
        int attempts = 0;
        while (running.get()) {
            try {
                DatagramSocket sock = openSocket(settings);
                socket = sock;
                socketError = null;
                synchronized (linkLock) {
                    setLink(link.withLastError(null).withReconnectAttempts(attempts));
                }
                InetSocketAddress remote = "udp_connect".equals(settings.transport)
                        ? new InetSocketAddress(InetAddress.getByName(settings.remoteHost), settings.remotePort)
                        : null;
                long lastGcsHeartbeat = 0;
                SocketAddress lastSender = null;
                while (running.get()) {
                    long now = System.currentTimeMillis();
                    if (settings.sendGcsHeartbeat && now - lastGcsHeartbeat >= 1000) {
                        SocketAddress target = remote != null ? remote : lastSender;
                        if (target != null) {
                            byte[] frame = encoder.encode();
                            sock.send(new DatagramPacket(frame, frame.length, target));
                            MavlinkCounters c = counters;
                            setCounters(new MavlinkCounters(c.datagrams, c.framesAccepted, c.framesRejected,
                                    c.gcsHeartbeatsSent + 1));
                        }
                        lastGcsHeartbeat = now;
                    }
                    DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
                    try {
                        sock.receive(packet);
                    } catch (SocketTimeoutException timeout) {
                        continue;
                    }
                    lastSender = packet.getSocketAddress();
                    List<MavlinkMessage> messages = parser.feed(packet.getData(), packet.getOffset(), packet.getLength());
                    long receivedAt = System.currentTimeMillis();
                    TelemetryState state = telemetry;
                    for (MavlinkMessage message : messages) {
                        state = TelemetryReducer.reduce(state, message, receivedAt);
                    }
                    if (state != telemetry) {
                        setTelemetry(state);
                    }
                    MavlinkParser.Stats stats = parser.getStats();
                    MavlinkCounters c = counters;
                    setCounters(new MavlinkCounters(c.datagrams + 1, stats.framesAccepted,
                            stats.unsupportedOrInvalid, c.gcsHeartbeatsSent));
                }
            } catch (Exception e) {
                if (!running.get()) {
                    break;
                }
                attempts += 1;
                socketError = e.getClass().getSimpleName() + ": " + e.getMessage();
                log.error("MAVLink", "Socket: " + socketError + ". Reintento en " + (reconnectDelayMs / 1000.0) + " s");
                synchronized (linkLock) {
                    setLink(link.withReconnectAttempts(attempts));
                }
            } finally {
                closeSocket();
            }
            if (running.get()) {
                try {
                    Thread.sleep(reconnectDelayMs);
                } catch (InterruptedException interrupted) {
                    break;
                }
            }
        }
    }

    private static DatagramSocket openSocket(MavlinkSettings settings) throws IOException {
        DatagramSocket sock;
        switch (settings.transport) {
            case "udp_listen":
                sock = new DatagramSocket(null);
                sock.bind(new InetSocketAddress(InetAddress.getByName(settings.localHost), settings.localPort));
                break;
            case "udp_connect":
                sock = new DatagramSocket();
                break;
            default:
                throw new IllegalArgumentException("transporte no soportado: " + settings.transport);
        }
        sock.setSoTimeout(250);
        return sock;
    }

    private void closeSocket() {
        DatagramSocket s = socket;
        socket = null;
        if (s != null) {
            s.close();
        }
    }

    /** Stops receiving and releases the socket. Safe to call repeatedly. */
    public synchronized void disconnect() {
        connectionRequested = false;
        boolean wasRunning = running != null;
        if (running != null) {
            running.set(false);
        }
        running = null;
        if (supervisorExecutor != null) {
            supervisorExecutor.shutdownNow();
            supervisorExecutor = null;
        }
        if (receiveThread != null) {
            receiveThread.interrupt();
        }
        closeSocket(); // unblocks receive() immediately
        if (wasRunning) {
            log.info("MAVLink", "Desconectado");
        }
        synchronized (linkLock) {
            setLink(link.withStatus(LinkStatus.DISCONNECTED, null));
        }
    }

    /** Disconnects and waits (up to 2 s) for the receive thread to finish. */
    private void disconnectAndWait() {
        Thread previous = receiveThread;
        disconnect();
        receiveThread = null;
        if (previous != null) {
            try {
                previous.join(2000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
    }

    /** Releases every resource; equivalent to {@link #disconnect()}. */
    public synchronized void close() {
        disconnectAndWait();
    }

    private void setTelemetry(TelemetryState value) {
        telemetry = value;
        for (Listener l : listeners) {
            l.onTelemetry(value);
        }
    }

    private void setLink(LinkState value) {
        link = value;
        for (Listener l : listeners) {
            l.onLink(value);
        }
    }

    private void setCounters(MavlinkCounters value) {
        counters = value;
        for (Listener l : listeners) {
            l.onCounters(value);
        }
    }
}
