package org.safeflight.android.state

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import org.safeflight.android.mavlink.MavlinkHeader
import org.safeflight.android.mavlink.MavlinkMessage
import org.safeflight.android.video.VideoState
import org.safeflight.android.video.VideoStatus
import org.safeflight.android.video.VideoSupervisor

class StateMachinesTest {
    private val supervisor = LinkSupervisor(staleAfterMs = 3000)

    @Test
    fun linkThresholds() {
        val s0 = LinkState()
        assertEquals(LinkStatus.DISCONNECTED, supervisor.evaluate(false, null, 0, 10, s0).status)
        assertEquals(LinkStatus.WAITING_HEARTBEAT, supervisor.evaluate(true, null, null, 10, s0).status)
        assertEquals(LinkStatus.CONNECTED, supervisor.evaluate(true, null, 1000, 3999, s0).status)
        assertEquals(LinkStatus.STALE, supervisor.evaluate(true, null, 1000, 4001, s0).status)
        assertEquals(LinkStatus.LOST, supervisor.evaluate(true, null, 1000, 10_001, s0).status)
        assertEquals(LinkStatus.ERROR, supervisor.evaluate(true, "bind", 1000, 1001, s0).status)
        assertEquals(9001L, supervisor.evaluate(true, null, 1000, 10_001, s0).heartbeatAgeMs)
    }

    @Test
    fun reducerIgnoresOtherSystemsAndComponents() {
        fun hb(sys: Int, comp: Int, mode: Long) = MavlinkMessage.Heartbeat(
            MavlinkHeader(2, 0, sys, comp, 0), mode, 2, 3, 0x81, 4, 3,
        )
        var s = TelemetryReducer.reduce(TelemetryState(), hb(1, 1, 4), 100)
        assertEquals("GUIDED", s.flightMode)
        s = TelemetryReducer.reduce(s, hb(2, 1, 9), 200) // another vehicle
        s = TelemetryReducer.reduce(s, hb(1, 154, 9), 300) // another component (e.g. gimbal)
        assertEquals("GUIDED", s.flightMode)
        assertEquals(100L, s.lastHeartbeatAtMs)
        // Data from another system cannot overwrite the battery either.
        s = TelemetryReducer.reduce(s, MavlinkMessage.SysStatus(MavlinkHeader(2, 0, 2, 1, 1), 11000, 100, 50, 0), 400)
        assertNull(s.batteryVoltageV)
    }

    @Test
    fun telemetryBeforeVehicleHeartbeatIsIgnored() {
        val s = TelemetryReducer.reduce(
            TelemetryState(),
            MavlinkMessage.SysStatus(MavlinkHeader(2, 0, 1, 1, 1), 15000, 100, 50, 0),
            100,
        )
        assertNull(s.batteryVoltageV)
    }

    @Test
    fun statusTextListIsBounded() {
        var s = TelemetryState(vehicleSystemId = 1, vehicleComponentId = 1)
        repeat(50) { s = TelemetryReducer.reduce(s, MavlinkMessage.StatusText(MavlinkHeader(2, 0, 1, 1, 253), 6, "m$it"), it.toLong()) }
        assertEquals(TelemetryReducer.MAX_MESSAGES, s.messages.size)
        assertEquals("m49", s.messages.first().text)
    }

    @Test
    fun videoSupervision() {
        var v = VideoState(status = VideoStatus.CONNECTING)
        v = VideoSupervisor.onTick(v, null, 1000, 2000)
        assertEquals(VideoStatus.CONNECTING, v.status)
        v = VideoSupervisor.onFrame(v, 1000, 1280, 720)
        assertEquals(VideoStatus.PLAYING, v.status)
        v = VideoSupervisor.onTick(v, 1000, 3500, 2000)
        assertEquals(VideoStatus.STALE, v.status)
        v = VideoSupervisor.onError(v, "timeout")
        assertEquals(VideoStatus.ERROR, v.status)
        assertEquals(1, v.retries)
        assertEquals(VideoStatus.ERROR, VideoSupervisor.onTick(v, 3400, 3500, 2000).status)
    }

    @Test
    fun videoWatchdogRestartsSilentFailures() {
        val connecting = VideoState(status = VideoStatus.CONNECTING)
        // Opened at t=0, no frame: restart only after the connect timeout.
        assertNull(VideoSupervisor.restartReason(connecting, 0, null, 9_000, 2000, 10_000))
        assertEquals(true, VideoSupervisor.restartReason(connecting, 0, null, 10_001, 2000, 10_000) != null)
        // Frozen stream: restart after 4 x stale threshold.
        val stale = VideoState(status = VideoStatus.STALE)
        assertNull(VideoSupervisor.restartReason(stale, 0, 1_000, 8_000, 2000, 10_000))
        assertEquals(true, VideoSupervisor.restartReason(stale, 0, 1_000, 9_001, 2000, 10_000) != null)
        // Playing or stopped: never.
        assertNull(VideoSupervisor.restartReason(VideoState(status = VideoStatus.PLAYING), 0, 1_000, 60_000, 2000, 10_000))
        assertNull(VideoSupervisor.restartReason(VideoState(status = VideoStatus.IDLE), null, null, 60_000, 2000, 10_000))
    }
}
