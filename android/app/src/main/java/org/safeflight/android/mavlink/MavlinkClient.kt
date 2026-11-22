package org.safeflight.android.mavlink

import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.safeflight.android.config.MavlinkSettings
import org.safeflight.android.diagnostics.DiagnosticsLog
import org.safeflight.android.state.LinkState
import org.safeflight.android.state.LinkStatus
import org.safeflight.android.state.LinkSupervisor
import org.safeflight.android.state.TelemetryReducer
import org.safeflight.android.state.TelemetryState
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.SocketException
import java.net.SocketTimeoutException

data class MavlinkCounters(
    val datagrams: Long = 0,
    val framesAccepted: Long = 0,
    val framesRejected: Long = 0,
    val gcsHeartbeatsSent: Long = 0,
)

/**
 * Receive-only MAVLink client over UDP.
 *
 *  * `udp_listen`: binds a local port; the vehicle side (MAVProxy/mavlink-router)
 *    sends to this device.
 *  * `udp_connect`: sends GCS heartbeats to a remote endpoint so it learns this
 *    device's address, then receives its telemetry.
 *
 * The client never sends commands. Socket errors trigger a controlled
 * reconnection after [reconnectDelayMs]; link loss is derived from the age of
 * the last vehicle heartbeat by [LinkSupervisor].
 */
class MavlinkClient(
    private val log: DiagnosticsLog,
    private val dispatcher: CoroutineDispatcher = Dispatchers.IO,
    private val clock: () -> Long = System::currentTimeMillis,
    private val reconnectDelayMs: Long = 2000,
) {
    private val scope = CoroutineScope(SupervisorJob() + dispatcher)
    private var receiveJob: Job? = null
    private var supervisorJob: Job? = null
    @Volatile private var socket: DatagramSocket? = null
    @Volatile private var socketError: String? = null
    @Volatile private var connectionRequested = false

    private val _telemetry = MutableStateFlow(TelemetryState())
    val telemetry: StateFlow<TelemetryState> = _telemetry.asStateFlow()

    private val _link = MutableStateFlow(LinkState())
    val link: StateFlow<LinkState> = _link.asStateFlow()

    private val _counters = MutableStateFlow(MavlinkCounters())
    val counters: StateFlow<MavlinkCounters> = _counters.asStateFlow()

    val isRunning: Boolean get() = receiveJob?.isActive == true

    fun connect(settings: MavlinkSettings, telemetryStaleS: Double) {
        disconnectBlocking()
        val supervisor = LinkSupervisor((telemetryStaleS * 1000).toLong())
        val endpoint = when (settings.transport) {
            "udp_listen" -> "udp://${settings.localHost}:${settings.localPort} (escucha)"
            "udp_connect" -> "udp://${settings.remoteHost}:${settings.remotePort} (remoto)"
            else -> settings.transport
        }
        _telemetry.value = TelemetryState()
        _counters.value = MavlinkCounters()
        socketError = null
        connectionRequested = true
        _link.value = LinkState(status = LinkStatus.WAITING_HEARTBEAT, endpoint = endpoint)
        log.info("MAVLink", "Conectando $endpoint")

        receiveJob = scope.launch { receiveLoop(settings) }
        supervisorJob = scope.launch {
            while (isActive) {
                _link.update {
                    supervisor.evaluate(connectionRequested, socketError, _telemetry.value.lastHeartbeatAtMs, clock(), it)
                        .also { next -> logTransition(it.status, next) }
                }
                delay(250)
            }
        }
    }

    private fun logTransition(previous: LinkStatus, next: LinkState) {
        if (previous == next.status) return
        when (next.status) {
            LinkStatus.CONNECTED -> log.info("MAVLink", "Heartbeat del vehículo recibido")
            LinkStatus.STALE -> log.warn("MAVLink", "Telemetría obsoleta (${next.heartbeatAgeMs} ms sin heartbeat)")
            LinkStatus.LOST -> log.error("MAVLink", "Pérdida de telemetría (${next.heartbeatAgeMs} ms sin heartbeat)")
            LinkStatus.ERROR -> log.error("MAVLink", "Error de enlace: ${next.lastError}")
            else -> Unit
        }
    }

    private suspend fun receiveLoop(settings: MavlinkSettings) {
        val parser = MavlinkParser()
        val encoder = GcsHeartbeatEncoder()
        val buffer = ByteArray(2048)
        var attempts = 0
        while (scope.isActive && currentCoroutineActive()) {
            try {
                val sock = openSocket(settings)
                socket = sock
                socketError = null
                _link.update { it.copy(lastError = null, reconnectAttempts = attempts) }
                val remote = if (settings.transport == "udp_connect") {
                    InetSocketAddress(InetAddress.getByName(settings.remoteHost), settings.remotePort)
                } else {
                    null
                }
                var lastGcsHeartbeat = 0L
                var lastSender: InetSocketAddress? = null
                while (currentCoroutineActive()) {
                    val now = clock()
                    if (settings.sendGcsHeartbeat && now - lastGcsHeartbeat >= 1000) {
                        val target = remote ?: lastSender
                        if (target != null) {
                            val frame = encoder.encode()
                            sock.send(DatagramPacket(frame, frame.size, target))
                            _counters.update { it.copy(gcsHeartbeatsSent = it.gcsHeartbeatsSent + 1) }
                        }
                        lastGcsHeartbeat = now
                    }
                    val packet = DatagramPacket(buffer, buffer.size)
                    try {
                        sock.receive(packet)
                    } catch (_: SocketTimeoutException) {
                        continue
                    }
                    lastSender = packet.socketAddress as? InetSocketAddress
                    val messages = parser.feed(packet.data, packet.offset, packet.length)
                    val receivedAt = clock()
                    var state = _telemetry.value
                    for (message in messages) state = TelemetryReducer.reduce(state, message, receivedAt)
                    _telemetry.value = state
                    val stats = parser.stats
                    _counters.update {
                        it.copy(
                            datagrams = it.datagrams + 1,
                            framesAccepted = stats.framesAccepted,
                            framesRejected = stats.unsupportedOrInvalid,
                        )
                    }
                }
            } catch (e: Exception) {
                if (!currentCoroutineActive()) break
                attempts += 1
                socketError = "${e.javaClass.simpleName}: ${e.message}"
                log.error("MAVLink", "Socket: $socketError. Reintento en ${reconnectDelayMs / 1000.0} s")
                _link.update { it.copy(reconnectAttempts = attempts) }
            } finally {
                closeSocket()
            }
            if (currentCoroutineActive()) delay(reconnectDelayMs)
        }
    }

    private suspend fun currentCoroutineActive(): Boolean = kotlin.coroutines.coroutineContext.isActive

    private fun openSocket(settings: MavlinkSettings): DatagramSocket {
        val sock = when (settings.transport) {
            "udp_listen" -> DatagramSocket(null).apply {
                bind(InetSocketAddress(InetAddress.getByName(settings.localHost), settings.localPort))
            }
            "udp_connect" -> DatagramSocket()
            else -> throw IllegalArgumentException("transporte no soportado: ${settings.transport}")
        }
        sock.soTimeout = 250
        return sock
    }

    private fun closeSocket() {
        try {
            socket?.close()
        } catch (_: SocketException) {
        }
        socket = null
    }

    /** Stops receiving and releases the socket. Safe to call repeatedly. */
    fun disconnect() {
        connectionRequested = false
        val jobs = listOfNotNull(receiveJob, supervisorJob)
        receiveJob = null
        supervisorJob = null
        jobs.forEach { it.cancel() }
        closeSocket() // unblocks receive() immediately
        if (jobs.isNotEmpty()) log.info("MAVLink", "Desconectado")
        _link.update { it.copy(status = LinkStatus.DISCONNECTED, heartbeatAgeMs = null) }
    }

    private fun disconnectBlocking() {
        val jobs = listOfNotNull(receiveJob, supervisorJob)
        disconnect()
        if (jobs.isNotEmpty()) {
            kotlinx.coroutines.runBlocking { jobs.forEach { it.cancelAndJoin() } }
        }
    }

    /** Releases every resource; the client must not be used afterwards. */
    fun close() {
        disconnect()
        scope.coroutineContext[Job]?.cancel()
    }
}
