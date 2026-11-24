package org.safeflight.android;

import android.os.Bundle;
import android.view.WindowManager;

import androidx.annotation.IdRes;
import androidx.appcompat.app.AppCompatActivity;
import androidx.fragment.app.Fragment;
import androidx.fragment.app.FragmentManager;
import androidx.fragment.app.FragmentTransaction;
import androidx.lifecycle.Lifecycle;
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
 * <p>The navigation rail on the left chooses the screen shown in
 * {@code fragment_container}: Vuelo → {@link FlightFragment},
 * Conexión → {@link ConnectionFragment}, Misiones → {@link MissionsFragment}.
 * Each screen is created on its first visit and then reused (see {@link #showScreen}).
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

    private static final String[] SCREENS = {"flight", "connection", "missions"};

    /**
     * Shows a screen. Each screen is created once and then only shown or hidden,
     * so changing screen does not inflate layouts or rebuild views again.
     * Hidden screens keep their views, release the video and skip redrawing
     * until they are shown again (FlightFragment/ConnectionFragment.onHiddenChanged).
     */
    private void showScreen(@IdRes int itemId) {
        String tag;
        if (itemId == R.id.nav_connection) {
            tag = "connection";
        } else if (itemId == R.id.nav_missions) {
            tag = "missions";
        } else {
            tag = "flight";
        }
        FragmentManager fm = getSupportFragmentManager();
        FragmentTransaction tx = fm.beginTransaction().setReorderingAllowed(true);
        for (String other : SCREENS) {
            Fragment f = fm.findFragmentByTag(other);
            if (f != null && !other.equals(tag) && !f.isHidden()) {
                // STARTED (not CREATED: that would destroy the view). Hidden screens stop
                // drawing and release the video themselves in onHiddenChanged().
                tx.hide(f).setMaxLifecycle(f, Lifecycle.State.STARTED);
            }
        }
        Fragment screen = fm.findFragmentByTag(tag);
        if (screen == null) {
            screen = newScreen(tag);
            tx.add(R.id.fragment_container, screen, tag);   // first visit only
        } else {
            tx.show(screen);
        }
        tx.setMaxLifecycle(screen, Lifecycle.State.RESUMED);
        tx.commitNow();
        NavTrace.measure(getWindow().getDecorView(), fm, tag, lastTouchUpMs);
    }

    private static Fragment newScreen(String tag) {
        switch (tag) {
            case "connection":
                return new ConnectionFragment();
            case "missions":
                return new MissionsFragment();
            default:
                return new FlightFragment();
        }
    }

    /** Time of the last finger lift, used by {@link NavTrace} (debug builds only). */
    private long lastTouchUpMs = 0;

    @Override
    public boolean dispatchTouchEvent(android.view.MotionEvent event) {
        if (event.getActionMasked() == android.view.MotionEvent.ACTION_UP) {
            lastTouchUpMs = event.getEventTime();
        }
        return super.dispatchTouchEvent(event);
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
