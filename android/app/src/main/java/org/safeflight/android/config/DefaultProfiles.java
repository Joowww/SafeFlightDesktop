package org.safeflight.android.config;

import java.util.ArrayList;
import java.util.List;

/** Factory profiles (same ids and values as the Kotlin version and Desktop). */
public final class DefaultProfiles {
    /** Provisional SIYI address of the Raspberry Pi RTSP server (to be verified). */
    public static final String SIYI_RTSP_URL = "rtsp://192.168.144.30:8554/raspicam";

    private DefaultProfiles() {
    }

    /** New instances every call, so callers may modify them freely. */
    public static List<ConnectionProfile> all() {
        List<ConnectionProfile> list = new ArrayList<>();
        list.add(profile("siyi-local", "SIYI LOCAL", "siyi_local",
                "Red SIYI 192.168.144.0/24. Valores PROVISIONALES: verificar la IP de la Raspberry "
                        + "y el reenvío MAVLink hacia este mando antes de usar.",
                SIYI_RTSP_URL));
        list.add(profile("cellular-vpn", "5G / VPN", "cellular_vpn",
                "Enlace secundario de mantenimiento a través de la VPN. Requiere que MAVProxy "
                        + "reenvíe a la IP VPN de este dispositivo.",
                SIYI_RTSP_URL));
        list.add(profile("raspberry-lab", "RASPBERRY / CUBE (LAB)", "custom",
                "Raspberry Pi del laboratorio (172.16.15.85) con Cube Orange en /dev/ttyACM0 a 57600. "
                        + "MAVProxy reenvía MAVLink a este equipo. Verificar la IP del equipo antes de conectar; "
                        + "primera conexión siempre en SOLO MONITORIZACIÓN. En Android: solo monitorización; "
                        + "MAVProxy necesita una salida --out=udpout:<IP_ANDROID>:14550. Vídeo por RTSP "
                        + "(MediaMTX en la Raspberry).",
                "rtsp://172.16.15.85:8554/cam"));
        list.add(profile("sitl", "SITL / SIMULACIÓN", "sitl",
                "SITL o scripts/mavlink_test_sender.py. En el emulador Android usar 'UDP hacia remoto' "
                        + "10.0.2.2:14551 con el generador en modo --serve 14551.",
                "rtsp://10.0.2.2:18554/test"));
        return list;
    }

    /** Factory profile with this id, or {@code null} for custom profiles. */
    public static ConnectionProfile builtin(String id) {
        for (ConnectionProfile p : all()) {
            if (p.id.equals(id)) {
                return p;
            }
        }
        return null;
    }

    private static ConnectionProfile profile(String id, String name, String kind, String notes, String rtspUrl) {
        ConnectionProfile p = new ConnectionProfile(id, name);
        p.kind = kind;
        p.builtin = true;
        p.notes = notes;
        p.mavlink.transport = "udp_listen";
        p.mavlink.localHost = "0.0.0.0";
        p.mavlink.localPort = 14550;
        p.video.mode = "rtsp";
        p.video.rtspUrl = rtspUrl;
        p.video.rtspTransport = "tcp";
        return p;
    }
}
