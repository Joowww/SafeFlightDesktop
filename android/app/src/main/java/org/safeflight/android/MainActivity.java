package org.safeflight.android;

import android.os.Bundle;
import android.view.WindowManager;

import androidx.annotation.IdRes;
import androidx.appcompat.app.AppCompatActivity;
import androidx.fragment.app.Fragment;
import androidx.lifecycle.ViewModelProvider;

import com.google.android.material.snackbar.Snackbar;

import org.safeflight.android.config.ConnectionProfile;
import org.safeflight.android.databinding.ActivityMainBinding;
import org.safeflight.android.ui.ConnectionFragment;
import org.safeflight.android.ui.FlightFragment;
import org.safeflight.android.ui.MainViewModel;
import org.safeflight.android.ui.MissionsFragment;
import org.safeflight.android.ui.VideoHost;
import org.safeflight.android.video.VideoController;

/**
 * The only activity (layout: res/layout/activity_main.xml).
 *
 * <p>The navigation rail on the left swaps the screen shown in
 * {@code fragment_container}: Vuelo → {@link FlightFragment},
 * Conexión → {@link ConnectionFragment}, Misiones → {@link MissionsFragment}.
 * The activity owns the RTSP player: it starts in {@link #onStart()} and the
 * decoder is released in {@link #onStop()} (screen off, app in background).
 */
public final class MainActivity extends AppCompatActivity implements VideoHost {
    private ActivityMainBinding binding;
    private MainViewModel viewModel;
    private VideoController video;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        binding = ActivityMainBinding.inflate(getLayoutInflater());
        setContentView(binding.getRoot());
        // Ground-station screen must stay on while supervising a vehicle.
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        AppContainer container = ((SafeFlightApplication) getApplication()).getContainer();
        viewModel = new ViewModelProvider(this, MainViewModel.factory(container)).get(MainViewModel.class);
        video = new VideoController(this, container.log);

        binding.navRail.setOnItemSelectedListener(item -> {
            showScreen(item.getItemId());
            return true;
        });
        if (savedInstanceState == null) {
            // First start: Flight screen. After a recreation the FragmentManager and the
            // rail restore the previous screen and selection by themselves.
            binding.navRail.getMenu().findItem(R.id.nav_flight).setChecked(true);
            showScreen(R.id.nav_flight);
        }

        // One-shot messages (e.g. "ARM no disponible: ...").
        viewModel.getMessage().observe(this, message -> {
            if (message != null) {
                Snackbar.make(binding.root, message, Snackbar.LENGTH_LONG).show();
                viewModel.consumeMessage();
            }
        });
    }

    private void showScreen(@IdRes int itemId) {
        Fragment screen;
        if (itemId == R.id.nav_connection) {
            screen = new ConnectionFragment();
        } else if (itemId == R.id.nav_missions) {
            screen = new MissionsFragment();
        } else {
            screen = new FlightFragment();
        }
        getSupportFragmentManager().beginTransaction()
                .replace(R.id.fragment_container, screen)
                .commit();
    }

    @Override
    protected void onStart() {
        super.onStart();
        restartVideo();
    }

    @Override
    protected void onStop() {
        video.stop();
        super.onStop();
    }

    // ------------------------------------------------------------- VideoHost
    @Override
    public VideoController getVideo() {
        return video;
    }

    @Override
    public void restartVideo() {
        ConnectionProfile profile = viewModel.getActiveProfile();
        video.start(profile.video, profile.timeouts.videoStaleS, profile.timeouts.videoReconnectIntervalS);
    }

    @Override
    public void stopVideo() {
        video.stop();
    }
}
