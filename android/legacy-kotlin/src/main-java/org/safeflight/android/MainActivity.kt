package org.safeflight.android

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import org.safeflight.android.ui.MainViewModel
import org.safeflight.android.ui.SafeFlightRoot
import org.safeflight.android.ui.theme.SafeFlightTheme
import org.safeflight.android.video.VideoController

class MainActivity : ComponentActivity() {
    private val viewModel: MainViewModel by viewModels { MainViewModel.Factory }
    private lateinit var video: VideoController

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Ground-station screen must stay on while supervising a vehicle.
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        val container = (application as SafeFlightApplication).container
        video = VideoController(this, container.log)

        // The decoder is released when the activity is not visible and
        // re-created with the active profile when it becomes visible again.
        lifecycle.addObserver(object : DefaultLifecycleObserver {
            override fun onStart(owner: LifecycleOwner) = startVideo()
            override fun onStop(owner: LifecycleOwner) = video.stop()
        })

        setContent {
            SafeFlightTheme {
                SafeFlightRoot(
                    viewModel = viewModel,
                    video = video,
                    onRestartVideo = ::startVideo,
                    onStopVideo = { video.stop() },
                )
            }
        }
    }

    private fun startVideo() {
        val profile = viewModel.activeProfile
        video.start(profile.video, profile.timeouts.videoStaleS, profile.timeouts.videoReconnectIntervalS)
    }
}
