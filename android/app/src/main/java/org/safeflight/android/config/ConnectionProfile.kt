package org.safeflight.android.config

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.net.URI

/**
 * Connection profile. The JSON layout follows
 * shared/schemas/connection-profiles.schema.json, also used by SafeFlight
 * Desktop. Android supports the UDP transports and RTSP video only; other
 * values are kept when read but rejected by [ProfileValidator].
 */
@Serializable
data class ConnectionProfile(
    val id: String,
    val name: String,
    val kind: String = "custom",
    val builtin: Boolean = false,
    val notes: String = "",
    val mavlink: MavlinkSettings = MavlinkSettings(),
    val video: VideoSettings = VideoSettings(),
    val timeouts: TimeoutSettings = TimeoutSettings(),
    val diagnostics: DiagnosticsSettings = DiagnosticsSettings(),
) {
    fun mavlinkEndpointLabel(): String = when (mavlink.transport) {
        "udp_listen" -> "UDP escucha ${mavlink.localHost}:${mavlink.localPort}"
        "udp_connect" -> "UDP → ${mavlink.remoteHost}:${mavlink.remotePort}"
        else -> "${mavlink.transport} (no soportado en Android)"
    }
}

@Serializable
data class MavlinkSettings(
    val transport: String = "udp_listen",
    @SerialName("local_host") val localHost: String = "0.0.0.0",
    @SerialName("local_port") val localPort: Int = 14550,
    @SerialName("remote_host") val remoteHost: String = "",
    @SerialName("remote_port") val remotePort: Int = 14550,
    @SerialName("serial_device") val serialDevice: String = "",
    @SerialName("baud_rate") val baudRate: Int = 57600,
    @SerialName("connection_string") val connectionString: String = "",
    /** Android only: send a GCS HEARTBEAT at 1 Hz (see GcsHeartbeatEncoder). */
    @SerialName("send_gcs_heartbeat") val sendGcsHeartbeat: Boolean = false,
)

@Serializable
data class VideoSettings(
    val mode: String = "rtsp",
    @SerialName("rtp_udp_port") val rtpUdpPort: Int = 5004,
    @SerialName("rtsp_url") val rtspUrl: String = "",
    @SerialName("rtsp_transport") val rtspTransport: String = "tcp",
)

@Serializable
data class TimeoutSettings(
    @SerialName("connect_timeout_s") val connectTimeoutS: Double = 90.0,
    @SerialName("heartbeat_timeout_s") val heartbeatTimeoutS: Double = 30.0,
    @SerialName("telemetry_stale_s") val telemetryStaleS: Double = 3.0,
    @SerialName("video_stale_s") val videoStaleS: Double = 2.0,
    @SerialName("video_reconnect_interval_s") val videoReconnectIntervalS: Double = 1.0,
)

@Serializable
data class DiagnosticsSettings(
    @SerialName("verbose_logging") val verboseLogging: Boolean = false,
)

@Serializable
data class ProfilesDocument(
    @SerialName("schema_version") val schemaVersion: Int = 1,
    @SerialName("active_profile_id") val activeProfileId: String = "",
    val profiles: List<ConnectionProfile> = emptyList(),
)

val ProfileJson: Json = Json {
    ignoreUnknownKeys = true
    encodeDefaults = true
    prettyPrint = true
}

object ProfileValidator {
    private val idRegex = Regex("^[a-z0-9][a-z0-9_-]{0,47}$")
    private val hostRegex = Regex(
        "^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]{0,62}[A-Za-z0-9])?(\\.[A-Za-z0-9]([A-Za-z0-9-]{0,62}[A-Za-z0-9])?)*$",
    )
    private val timeoutLimits = mapOf(
        "connect_timeout_s" to (5.0..300.0),
        "heartbeat_timeout_s" to (5.0..120.0),
        "telemetry_stale_s" to (0.5..60.0),
        "video_stale_s" to (0.5..60.0),
        "video_reconnect_interval_s" to (0.2..30.0),
    )

    fun validHost(host: String): Boolean = host.isNotBlank() && !host.contains(' ') && hostRegex.matches(host)

    fun validRtspUrl(url: String): Boolean {
        if (url.isBlank() || url.length > 1024 || url.any { it == '\n' || it == '\r' || it == '\t' }) return false
        return try {
            val uri = URI(url)
            (uri.scheme == "rtsp" || uri.scheme == "rtsps") && !uri.host.isNullOrBlank() &&
                (uri.port == -1 || uri.port in 1..65535)
        } catch (e: Exception) {
            false
        }
    }

    /** Returns the list of problems; empty when the profile is usable on Android. */
    fun validate(profile: ConnectionProfile): List<String> {
        val errors = mutableListOf<String>()
        if (!idRegex.matches(profile.id)) errors += "id inválido"
        if (profile.name.isBlank() || profile.name.length > 64) errors += "nombre obligatorio (máx. 64)"
        val m = profile.mavlink
        when (m.transport) {
            "udp_listen" -> {
                if (!validHost(m.localHost)) errors += "dirección local de escucha inválida"
                if (m.localPort !in 1024..65535) errors += "puerto local fuera de rango (1024-65535)"
            }
            "udp_connect" -> {
                if (!validHost(m.remoteHost)) errors += "dirección remota inválida"
                if (m.remotePort !in 1..65535) errors += "puerto remoto fuera de rango"
                if (!m.sendGcsHeartbeat) {
                    errors += "UDP hacia remoto requiere heartbeat de GCS para que el remoto conozca esta estación"
                }
            }
            else -> errors += "transporte '${m.transport}' no soportado en Android (usar udp_listen o udp_connect)"
        }
        val v = profile.video
        when (v.mode) {
            "rtsp" -> {
                if (!validRtspUrl(v.rtspUrl)) errors += "URL RTSP inválida (rtsp://host:puerto/ruta)"
                if (v.rtspTransport !in setOf("tcp", "udp")) errors += "transporte RTSP debe ser tcp o udp"
            }
            "none" -> Unit
            "rtp_udp" -> errors += "RTP/UDP sin RTSP no está soportado en Android; publicar el vídeo mediante RTSP"
            else -> errors += "modo de vídeo desconocido"
        }
        val t = profile.timeouts
        val values = mapOf(
            "connect_timeout_s" to t.connectTimeoutS,
            "heartbeat_timeout_s" to t.heartbeatTimeoutS,
            "telemetry_stale_s" to t.telemetryStaleS,
            "video_stale_s" to t.videoStaleS,
            "video_reconnect_interval_s" to t.videoReconnectIntervalS,
        )
        for ((key, value) in values) {
            val range = timeoutLimits.getValue(key)
            if (value !in range) errors += "$key fuera de rango (${range.start}-${range.endInclusive})"
        }
        return errors
    }
}

object DefaultProfiles {
    /** Provisional SIYI address of the Raspberry Pi RTSP server (to be verified). */
    const val SIYI_RTSP_URL = "rtsp://192.168.144.30:8554/raspicam"

    fun all(): List<ConnectionProfile> = listOf(
        ConnectionProfile(
            id = "siyi-local",
            name = "SIYI LOCAL",
            kind = "siyi_local",
            builtin = true,
            notes = "Red SIYI 192.168.144.0/24. Valores PROVISIONALES: verificar la IP de la Raspberry " +
                "y el reenvío MAVLink hacia este mando antes de usar.",
            mavlink = MavlinkSettings(transport = "udp_listen", localHost = "0.0.0.0", localPort = 14550),
            video = VideoSettings(mode = "rtsp", rtspUrl = SIYI_RTSP_URL, rtspTransport = "tcp"),
        ),
        ConnectionProfile(
            id = "cellular-vpn",
            name = "5G / VPN",
            kind = "cellular_vpn",
            builtin = true,
            notes = "Enlace secundario de mantenimiento a través de la VPN. Requiere que MAVProxy " +
                "reenvíe a la IP VPN de este dispositivo.",
            mavlink = MavlinkSettings(transport = "udp_listen", localHost = "0.0.0.0", localPort = 14550),
            video = VideoSettings(mode = "rtsp", rtspUrl = SIYI_RTSP_URL, rtspTransport = "tcp"),
        ),
        ConnectionProfile(
            id = "raspberry-lab",
            name = "RASPBERRY / CUBE (LAB)",
            kind = "custom",
            builtin = true,
            notes = "Raspberry Pi del laboratorio (172.16.15.85) con Cube Orange en /dev/ttyACM0 a 57600. MAVProxy reenvía MAVLink a este equipo. Verificar la IP del equipo antes de conectar; primera conexión siempre en SOLO MONITORIZACIÓN. En Android: solo monitorización; MAVProxy necesita una salida " +
                "--out=udpout:<IP_ANDROID>:14550. Vídeo por RTSP (MediaMTX en la Raspberry).",
            mavlink = MavlinkSettings(transport = "udp_listen", localHost = "0.0.0.0", localPort = 14550),
            video = VideoSettings(mode = "rtsp", rtspUrl = "rtsp://172.16.15.85:8554/cam", rtspTransport = "tcp"),
        ),
        ConnectionProfile(
            id = "sitl",
            name = "SITL / SIMULACIÓN",
            kind = "sitl",
            builtin = true,
            notes = "SITL o scripts/mavlink_test_sender.py. En el emulador Android usar 'UDP hacia remoto' " +
                "10.0.2.2:14551 con el generador en modo --serve 14551.",
            mavlink = MavlinkSettings(transport = "udp_listen", localHost = "0.0.0.0", localPort = 14550),
            video = VideoSettings(mode = "rtsp", rtspUrl = "rtsp://10.0.2.2:18554/test", rtspTransport = "tcp"),
        ),
    )

    fun builtin(id: String): ConnectionProfile? = all().firstOrNull { it.id == id }
}
