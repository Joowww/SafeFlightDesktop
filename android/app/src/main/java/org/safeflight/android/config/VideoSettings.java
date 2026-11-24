package org.safeflight.android.config;

import java.util.Objects;

/** "video" section of a connection profile. Android plays RTSP only. */
public final class VideoSettings {
    /** "rtsp", "none" or (Desktop only) "rtp_udp". */
    public String mode = "rtsp";
    public int rtpUdpPort = 5004;
    public String rtspUrl = "";
    /** "tcp" or "udp" (RTP interleaved over TCP is the robust default). */
    public String rtspTransport = "tcp";

    public VideoSettings copy() {
        VideoSettings c = new VideoSettings();
        c.mode = mode;
        c.rtpUdpPort = rtpUdpPort;
        c.rtspUrl = rtspUrl;
        c.rtspTransport = rtspTransport;
        return c;
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) {
            return true;
        }
        if (!(o instanceof VideoSettings)) {
            return false;
        }
        VideoSettings v = (VideoSettings) o;
        return rtpUdpPort == v.rtpUdpPort && Objects.equals(mode, v.mode) && Objects.equals(rtspUrl, v.rtspUrl)
                && Objects.equals(rtspTransport, v.rtspTransport);
    }

    @Override
    public int hashCode() {
        return Objects.hash(mode, rtpUdpPort, rtspUrl, rtspTransport);
    }
}
