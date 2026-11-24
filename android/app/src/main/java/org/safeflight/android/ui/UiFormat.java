package org.safeflight.android.ui;

import androidx.annotation.ColorRes;

import org.safeflight.android.R;
import org.safeflight.android.state.LinkStatus;
import org.safeflight.android.video.VideoStatus;

import java.util.Locale;

/** Texts and colours shared by the screens (the colours are defined in res/values/colors.xml). */
public final class UiFormat {
    /** Shown for every unknown value. */
    public static final String UNKNOWN = "—";

    private UiFormat() {
    }

    /** Number with fixed decimals and unit, or {@link #UNKNOWN} for {@code null}. */
    public static String fmt(Double value, int decimals, String unit) {
        if (value == null) {
            return UNKNOWN;
        }
        return String.format(Locale.US, "%." + decimals + "f", value) + unit;
    }

    public static String fmt(Double value, int decimals) {
        return fmt(value, decimals, "");
    }

    public static String orUnknown(Object value) {
        return value == null ? UNKNOWN : String.valueOf(value);
    }

    @ColorRes
    public static int linkColor(LinkStatus status) {
        switch (status) {
            case CONNECTED:
                return R.color.sf_ok;
            case STALE:
            case WAITING_HEARTBEAT:
                return R.color.sf_warn;
            case LOST:
            case ERROR:
                return R.color.sf_danger;
            default:
                return R.color.sf_muted;
        }
    }

    public static String linkLabel(LinkStatus status) {
        switch (status) {
            case WAITING_HEARTBEAT:
                return "ESPERANDO HEARTBEAT";
            case CONNECTED:
                return "CONECTADO";
            case STALE:
                return "TELEMETRÍA OBSOLETA";
            case LOST:
                return "TELEMETRÍA PERDIDA";
            case ERROR:
                return "ERROR DE ENLACE";
            default:
                return "DESCONECTADO";
        }
    }

    @ColorRes
    public static int videoColor(VideoStatus status) {
        switch (status) {
            case PLAYING:
                return R.color.sf_ok;
            case CONNECTING:
            case STALE:
                return R.color.sf_warn;
            case ERROR:
                return R.color.sf_danger;
            default:
                return R.color.sf_muted;
        }
    }

    public static String videoLabel(VideoStatus status) {
        switch (status) {
            case CONNECTING:
                return "VÍDEO CONECTANDO";
            case PLAYING:
                return "VÍDEO EN DIRECTO";
            case STALE:
                return "VÍDEO CONGELADO";
            case ERROR:
                return "VÍDEO SIN SEÑAL";
            default:
                return "VÍDEO INACTIVO";
        }
    }

    /** MAVLink severity: 0-3 emergency..error, 4 warning, 5+ notice/info/debug. */
    @ColorRes
    public static int severityColor(int severity) {
        if (severity <= 3) {
            return R.color.sf_danger;
        }
        return severity == 4 ? R.color.sf_warn : R.color.sf_text;
    }
}
