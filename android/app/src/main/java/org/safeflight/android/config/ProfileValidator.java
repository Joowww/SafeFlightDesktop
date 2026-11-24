package org.safeflight.android.config;

import java.net.URI;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

/** Checks that a profile is usable on Android. Same rules as the Kotlin version. */
public final class ProfileValidator {
    private static final Pattern ID = Pattern.compile("^[a-z0-9][a-z0-9_-]{0,47}$");
    private static final Pattern HOST = Pattern.compile(
            "^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]{0,62}[A-Za-z0-9])?(\\.[A-Za-z0-9]([A-Za-z0-9-]{0,62}[A-Za-z0-9])?)*$");

    private ProfileValidator() {
    }

    public static boolean isBlank(String s) {
        return s == null || s.trim().isEmpty();
    }

    public static boolean validHost(String host) {
        return !isBlank(host) && !host.contains(" ") && HOST.matcher(host).matches();
    }

    public static boolean validRtspUrl(String url) {
        if (isBlank(url) || url.length() > 1024 || url.contains("\n") || url.contains("\r") || url.contains("\t")) {
            return false;
        }
        try {
            URI uri = new URI(url);
            String scheme = uri.getScheme();
            return ("rtsp".equals(scheme) || "rtsps".equals(scheme)) && !isBlank(uri.getHost())
                    && (uri.getPort() == -1 || (uri.getPort() >= 1 && uri.getPort() <= 65535));
        } catch (Exception e) {
            return false;
        }
    }

    /** Returns the list of problems; empty when the profile is usable on Android. */
    public static List<String> validate(ConnectionProfile profile) {
        List<String> errors = new ArrayList<>();
        if (profile.id == null || !ID.matcher(profile.id).matches()) {
            errors.add("id inválido");
        }
        if (isBlank(profile.name) || profile.name.length() > 64) {
            errors.add("nombre obligatorio (máx. 64)");
        }

        MavlinkSettings m = profile.mavlink;
        switch (m.transport) {
            case "udp_listen":
                if (!validHost(m.localHost)) {
                    errors.add("dirección local de escucha inválida");
                }
                if (m.localPort < 1024 || m.localPort > 65535) {
                    errors.add("puerto local fuera de rango (1024-65535)");
                }
                break;
            case "udp_connect":
                if (!validHost(m.remoteHost)) {
                    errors.add("dirección remota inválida");
                }
                if (m.remotePort < 1 || m.remotePort > 65535) {
                    errors.add("puerto remoto fuera de rango");
                }
                if (!m.sendGcsHeartbeat) {
                    errors.add("UDP hacia remoto requiere heartbeat de GCS para que el remoto conozca esta estación");
                }
                break;
            default:
                errors.add("transporte '" + m.transport + "' no soportado en Android (usar udp_listen o udp_connect)");
                break;
        }

        VideoSettings v = profile.video;
        switch (v.mode) {
            case "rtsp":
                if (!validRtspUrl(v.rtspUrl)) {
                    errors.add("URL RTSP inválida (rtsp://host:puerto/ruta)");
                }
                if (!"tcp".equals(v.rtspTransport) && !"udp".equals(v.rtspTransport)) {
                    errors.add("transporte RTSP debe ser tcp o udp");
                }
                break;
            case "none":
                break;
            case "rtp_udp":
                errors.add("RTP/UDP sin RTSP no está soportado en Android; publicar el vídeo mediante RTSP");
                break;
            default:
                errors.add("modo de vídeo desconocido");
                break;
        }

        TimeoutSettings t = profile.timeouts;
        checkRange(errors, "connect_timeout_s", t.connectTimeoutS, 5.0, 300.0);
        checkRange(errors, "heartbeat_timeout_s", t.heartbeatTimeoutS, 5.0, 120.0);
        checkRange(errors, "telemetry_stale_s", t.telemetryStaleS, 0.5, 60.0);
        checkRange(errors, "video_stale_s", t.videoStaleS, 0.5, 60.0);
        checkRange(errors, "video_reconnect_interval_s", t.videoReconnectIntervalS, 0.2, 30.0);
        return errors;
    }

    private static void checkRange(List<String> errors, String key, double value, double min, double max) {
        if (!(value >= min && value <= max)) {
            errors.add(key + " fuera de rango (" + min + "-" + max + ")");
        }
    }
}
