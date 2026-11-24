package org.safeflight.android.state;

import org.junit.Test;
import org.safeflight.android.mavlink.MavlinkHeader;
import org.safeflight.android.mavlink.MavlinkMessage;
import org.safeflight.android.video.VideoState;
import org.safeflight.android.video.VideoStatus;
import org.safeflight.android.video.VideoSupervisor;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;

public class StateMachinesTest {
    private final LinkSupervisor supervisor = new LinkSupervisor(3000);

    private static MavlinkMessage.Heartbeat hb(int sys, int comp, long mode) {
        return new MavlinkMessage.Heartbeat(new MavlinkHeader(2, 0, sys, comp, 0), mode, 2, 3, 0x81, 4, 3);
    }

    private static MavlinkMessage.SysStatus battery(int sys, int millivolts) {
        return new MavlinkMessage.SysStatus(new MavlinkHeader(2, 0, sys, 1, 1), millivolts, 100, 50, 0);
    }

    @Test
    public void linkThresholds() {
        LinkState s0 = new LinkState();
        assertEquals(LinkStatus.DISCONNECTED, supervisor.evaluate(false, null, 0L, 10, s0).status);
        assertEquals(LinkStatus.WAITING_HEARTBEAT, supervisor.evaluate(true, null, null, 10, s0).status);
        assertEquals(LinkStatus.CONNECTED, supervisor.evaluate(true, null, 1000L, 3999, s0).status);
        assertEquals(LinkStatus.STALE, supervisor.evaluate(true, null, 1000L, 4001, s0).status);
        assertEquals(LinkStatus.LOST, supervisor.evaluate(true, null, 1000L, 10_001, s0).status);
        assertEquals(LinkStatus.ERROR, supervisor.evaluate(true, "bind", 1000L, 1001, s0).status);
        assertEquals(Long.valueOf(9001L), supervisor.evaluate(true, null, 1000L, 10_001, s0).heartbeatAgeMs);
    }

    @Test
    public void reducerIgnoresOtherSystemsAndComponents() {
        TelemetryState s = TelemetryReducer.reduce(new TelemetryState(), hb(1, 1, 4), 100);
        assertEquals("GUIDED", s.flightMode);
        s = TelemetryReducer.reduce(s, hb(2, 1, 9), 200);   // another vehicle
        s = TelemetryReducer.reduce(s, hb(1, 154, 9), 300); // another component (e.g. gimbal)
        assertEquals("GUIDED", s.flightMode);
        assertEquals(Long.valueOf(100L), s.lastHeartbeatAtMs);
        // Data from another system cannot overwrite the battery either.
        s = TelemetryReducer.reduce(s, battery(2, 11000), 400);
        assertNull(s.batteryVoltageV);
    }

    @Test
    public void reducerNeverModifiesItsInput() {
        TelemetryState before = TelemetryReducer.reduce(new TelemetryState(), hb(1, 1, 4), 100);
        TelemetryState after = TelemetryReducer.reduce(before, battery(1, 15000), 200);
        assertNull(before.batteryVoltageV);
        assertEquals(15.0, after.batteryVoltageV, 1e-9);
    }

    @Test
    public void telemetryBeforeVehicleHeartbeatIsIgnored() {
        TelemetryState s = TelemetryReducer.reduce(new TelemetryState(), battery(1, 15000), 100);
        assertNull(s.batteryVoltageV);
    }

    @Test
    public void statusTextListIsBounded() {
        TelemetryState s = TelemetryState.identifiedVehicle(1, 1, null);
        for (int i = 0; i < 50; i++) {
            s = TelemetryReducer.reduce(s,
                    new MavlinkMessage.StatusText(new MavlinkHeader(2, 0, 1, 1, 253), 6, "m" + i), i);
        }
        assertEquals(TelemetryReducer.MAX_MESSAGES, s.messages.size());
        assertEquals("m49", s.messages.get(0).text);
    }

    @Test
    public void videoSupervision() {
        VideoState v = new VideoState(VideoStatus.CONNECTING, "");
        v = VideoSupervisor.onTick(v, null, 1000, 2000);
        assertEquals(VideoStatus.CONNECTING, v.status);
        v = VideoSupervisor.onFrame(v, 1000, 1280, 720);
        assertEquals(VideoStatus.PLAYING, v.status);
        v = VideoSupervisor.onTick(v, 1000L, 3500, 2000);
        assertEquals(VideoStatus.STALE, v.status);
        v = VideoSupervisor.onError(v, "timeout");
        assertEquals(VideoStatus.ERROR, v.status);
        assertEquals(1, v.retries);
        assertEquals(VideoStatus.ERROR, VideoSupervisor.onTick(v, 3400L, 3500, 2000).status);
    }

    @Test
    public void videoWatchdogRestartsSilentFailures() {
        VideoState connecting = new VideoState(VideoStatus.CONNECTING, "");
        // Opened at t=0, no frame: restart only after the connect timeout.
        assertNull(VideoSupervisor.restartReason(connecting, 0L, null, 9_000, 2000, 10_000));
        assertNotNull(VideoSupervisor.restartReason(connecting, 0L, null, 10_001, 2000, 10_000));
        // Frozen stream: restart after 4 x stale threshold.
        VideoState stale = new VideoState(VideoStatus.STALE, "");
        assertNull(VideoSupervisor.restartReason(stale, 0L, 1_000L, 8_000, 2000, 10_000));
        assertNotNull(VideoSupervisor.restartReason(stale, 0L, 1_000L, 9_001, 2000, 10_000));
        // Playing or stopped: never.
        assertNull(VideoSupervisor.restartReason(new VideoState(VideoStatus.PLAYING, ""), 0L, 1_000L, 60_000, 2000, 10_000));
        assertNull(VideoSupervisor.restartReason(new VideoState(VideoStatus.IDLE, ""), null, null, 60_000, 2000, 10_000));
    }

    @Test
    public void videoRetryDelayGrowsWhileNoFrameArrives() {
        // Profile interval 1 s: 1, 2, 4, 8 s, then capped at 10 s.
        assertEquals(1000, VideoSupervisor.retryDelayMs(1000, 1));
        assertEquals(2000, VideoSupervisor.retryDelayMs(1000, 2));
        assertEquals(4000, VideoSupervisor.retryDelayMs(1000, 3));
        assertEquals(8000, VideoSupervisor.retryDelayMs(1000, 4));
        assertEquals(10_000, VideoSupervisor.retryDelayMs(1000, 5));
        assertEquals(10_000, VideoSupervisor.retryDelayMs(1000, 50));
        // A profile interval above the cap is respected as configured.
        assertEquals(20_000, VideoSupervisor.retryDelayMs(20_000, 3));
    }
}
