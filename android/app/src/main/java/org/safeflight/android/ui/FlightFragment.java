package org.safeflight.android.ui;

import android.content.res.ColorStateList;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.annotation.OptIn;
import androidx.annotation.Nullable;
import androidx.core.content.ContextCompat;
import androidx.fragment.app.Fragment;
import androidx.lifecycle.Lifecycle;
import androidx.media3.common.util.UnstableApi;
import androidx.lifecycle.ViewModelProvider;

import com.google.android.material.button.MaterialButton;

import org.safeflight.android.R;
import org.safeflight.android.control.FlightCommand;
import org.safeflight.android.databinding.FragmentFlightBinding;
import org.safeflight.android.state.LinkState;
import org.safeflight.android.state.LinkStatus;
import org.safeflight.android.state.StatusMessage;
import org.safeflight.android.state.TelemetryReducer;
import org.safeflight.android.state.TelemetryState;
import org.safeflight.android.video.VideoController;
import org.safeflight.android.video.VideoState;
import org.safeflight.android.video.VideoStatus;

import static org.safeflight.android.ui.UiFormat.UNKNOWN;
import static org.safeflight.android.ui.UiFormat.fmt;

/**
 * Flight screen (layout: res/layout/fragment_flight.xml).
 *
 * <p>Shows the main video, the link/video/armed/mode chips and the telemetry
 * panel. The control buttons are always locked: tapping one asks
 * {@link MainViewModel#requestCommand}, which only explains why it is refused.
 */
public final class FlightFragment extends Fragment {
    private FragmentFlightBinding binding;
    private MainViewModel viewModel;
    private VideoController video;
    private boolean messagesRendered = false;
    private Object lastFirstMessage;

    @Nullable
    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, @Nullable ViewGroup container,
                             @Nullable Bundle savedInstanceState) {
        binding = FragmentFlightBinding.inflate(inflater, container, false);
        return binding.getRoot();
    }

    @Override
    public void onViewCreated(@NonNull View view, @Nullable Bundle savedInstanceState) {
        viewModel = new ViewModelProvider(requireActivity()).get(MainViewModel.class);
        video = ((VideoHost) requireActivity()).getVideo();

        createControlButtons();

        // The PlayerView shows the current player instance while this screen holds the video.
        video.getPlayer().observe(getViewLifecycleOwner(), player -> {
            if (videoAttached) {
                binding.playerView.setPlayer(player);
            }
        });

        // Any change of telemetry, link or video redraws the screen (skipped while hidden).
        viewModel.getTelemetry().observe(getViewLifecycleOwner(), t -> render());
        viewModel.getLink().observe(getViewLifecycleOwner(), l -> render());
        video.getState().observe(getViewLifecycleOwner(), v -> render());
    }

    // ------------------------------------------------- visibility and video
    // The screen keeps its views while another screen is shown (MainActivity.showScreen),
    // but releases the video and stops redrawing until it is visible again.
    private boolean videoAttached = false;

    @Override
    public void onStart() {
        super.onStart();
        if (!isHidden()) {
            attachVideo();
        }
    }

    @Override
    public void onStop() {
        detachVideo();
        super.onStop();
    }

    @Override
    public void onHiddenChanged(boolean hidden) {
        super.onHiddenChanged(hidden);
        if (hidden) {
            // Released after the destination screen is drawn (see VideoController.releaseAfterNextFrame);
            // skipped if this screen is shown again before that.
            video.releaseAfterNextFrame(() -> {
                if (isHidden()) {
                    detachVideo();
                }
            });
        } else if (getViewLifecycleOwner().getLifecycle().getCurrentState().isAtLeast(Lifecycle.State.STARTED)) {
            attachVideo();
            render(); // show the latest values at once
        }
    }

    private void attachVideo() {
        video.flushPendingRelease(); // another screen's surface is released before this one is used
        if (videoAttached || binding == null) {
            return;
        }
        videoAttached = true;
        video.onSurfaceAttached();
        setSurfaceVisible(true);
        binding.playerView.setPlayer(video.getPlayer().getValue());
    }

    private void detachVideo() {
        if (!videoAttached || binding == null) {
            return;
        }
        videoAttached = false;
        binding.playerView.setPlayer(null);
        setSurfaceVisible(false);
        video.onSurfaceDetached();
    }

    /**
     * On Android 9 a SurfaceView keeps showing its last frame when only its parent is
     * hidden, so the video surface itself is hidden while this screen is not visible.
     */
    @OptIn(markerClass = UnstableApi.class)
    private void setSurfaceVisible(boolean visible) {
        View surface = binding.playerView.getVideoSurfaceView();
        if (surface != null) {
            surface.setVisibility(visible ? View.VISIBLE : View.GONE);
        }
    }

    @Override
    public void onDestroyView() {
        detachVideo();
        binding = null;
        messagesRendered = false;
        super.onDestroyView();
    }

    /** One locked button per {@link FlightCommand}, two per row. */
    private void createControlButtons() {
        LinearLayout row = null;
        FlightCommand[] commands = FlightCommand.values();
        for (int i = 0; i < commands.length; i++) {
            if (i % 2 == 0) {
                row = new LinearLayout(requireContext());
                row.setOrientation(LinearLayout.HORIZONTAL);
                binding.controlsContainer.addView(row);
            }
            final FlightCommand command = commands[i];
            MaterialButton button = new MaterialButton(requireContext(), null,
                    com.google.android.material.R.attr.materialButtonOutlinedStyle);
            button.setText("🔒 " + command.label);
            button.setTextSize(11);
            // One line, small side padding: "🔒 INICIAR MISIÓN" must fit without wrapping.
            button.setSingleLine(true);
            button.setEllipsize(android.text.TextUtils.TruncateAt.END);
            int pad = (int) (4 * getResources().getDisplayMetrics().density);
            button.setPaddingRelative(pad, button.getPaddingTop(), pad, button.getPaddingBottom());
            button.setTextColor(ContextCompat.getColor(requireContext(), R.color.sf_locked));
            button.setStrokeColor(ColorStateList.valueOf(ContextCompat.getColor(requireContext(), R.color.sf_outline)));
            // Visually locked, still tappable so that the operator learns why it is blocked.
            button.setOnClickListener(v -> viewModel.requestCommand(command));
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0,
                    ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
            params.setMarginEnd(6);
            row.addView(button, params);
        }
        if (commands.length % 2 == 1 && row != null) {
            row.addView(new View(requireContext()), new LinearLayout.LayoutParams(0, 1, 1f));
        }
    }

    private void render() {
        if (binding == null || isHidden()) {
            return; // hidden screens do not redraw; onHiddenChanged(false) renders on return
        }
        TelemetryState t = viewModel.getTelemetry().getValue();
        LinkState link = viewModel.getLink().getValue();
        VideoState v = video.currentState();
        if (t == null || link == null) {
            return;
        }
        boolean current = link.status == LinkStatus.CONNECTED;

        // --- chips over the video ---
        binding.chipMavlink.bind("MAVLINK " + UiFormat.linkLabel(link.status), UiFormat.linkColor(link.status),
                link.heartbeatAgeMs != null ? "HB " + fmt(link.heartbeatAgeMs / 1000.0, 1, " s") : null);
        binding.chipVideo.bind(UiFormat.videoLabel(v.status), UiFormat.videoColor(v.status),
                v.lastFrameAgeMs != null ? v.lastFrameAgeMs + " ms" : null);

        String armedText = t.armed == null ? "ARMADO: " + UNKNOWN : (t.armed ? "ARMADO" : "DESARMADO");
        int armedColor;
        if (!current || t.armed == null) {
            armedColor = R.color.sf_muted;
        } else {
            armedColor = t.armed ? R.color.sf_danger : R.color.sf_ok;
        }
        // Last known values are greyed out and labelled while the link is not current.
        binding.chipArmed.bind(armedText, armedColor, !current && t.armed != null ? "último" : null);
        binding.chipMode.bind("MODO " + (t.flightMode != null ? t.flightMode : UNKNOWN),
                current ? R.color.sf_accent : R.color.sf_muted,
                !current && t.flightMode != null ? "último" : null);

        // --- message in the middle of the video ---
        if (v.status != VideoStatus.PLAYING) {
            binding.videoMessage.setVisibility(View.VISIBLE);
            binding.videoMessage.setText(UiFormat.videoLabel(v.status) + (v.lastError != null ? "\n" + v.lastError : ""));
            binding.videoMessage.setTextColor(ContextCompat.getColor(requireContext(), UiFormat.videoColor(v.status)));
        } else {
            binding.videoMessage.setVisibility(View.GONE);
        }

        // --- lost / stale banner ---
        if (link.status == LinkStatus.LOST || link.status == LinkStatus.STALE) {
            boolean lost = link.status == LinkStatus.LOST;
            binding.linkBanner.setVisibility(View.VISIBLE);
            binding.linkBanner.setText(lost ? "PÉRDIDA DE TELEMETRÍA — valores no actualizados" : "TELEMETRÍA OBSOLETA");
            binding.linkBanner.setBackgroundTintList(ColorStateList.valueOf(
                    ContextCompat.getColor(requireContext(), lost ? R.color.sf_danger : R.color.sf_warn)));
        } else {
            binding.linkBanner.setVisibility(View.GONE);
        }

        // --- telemetry panel ---
        int valueColor = current ? R.color.sf_text : R.color.sf_warn;
        binding.rowRelAlt.setValue(fmt(t.relativeAltM, 1, " m"), valueColor);
        binding.rowMslAlt.setValue(fmt(t.altMslM, 1, " m"), valueColor);
        binding.rowGroundSpeed.setValue(fmt(t.groundspeedMps, 1, " m/s"), valueColor);
        binding.rowClimb.setValue(fmt(t.climbMps, 1, " m/s"), valueColor);
        binding.rowHeading.setValue(fmt(t.headingDeg, 0, "°"), valueColor);
        binding.rowVoltage.setValue(fmt(t.batteryVoltageV, 2, " V"), valueColor);
        binding.rowCurrent.setValue(fmt(t.batteryCurrentA, 1, " A"), valueColor);
        binding.rowRemaining.setValue(t.batteryRemainingPct != null ? t.batteryRemainingPct + " %" : UNKNOWN, valueColor);
        String fix = TelemetryReducer.fixLabel(t.gpsFixType);
        binding.rowFix.setValue(fix != null ? fix : UNKNOWN, valueColor);
        binding.rowSatellites.setValue(UiFormat.orUnknown(t.satellitesVisible), valueColor);
        binding.rowHdop.setValue(fmt(t.hdop, 2), valueColor);
        binding.rowLat.setValue(fmt(t.latDeg, 6), valueColor);
        binding.rowLon.setValue(fmt(t.lonDeg, 6), valueColor);

        renderMessages(t);
    }

    private void renderMessages(TelemetryState t) {
        // Telemetry arrives several times per second; rebuild the list only when it changed.
        Object key = t.messages.isEmpty() ? null : t.messages.get(0);
        if (messagesRendered && key == lastFirstMessage) {
            return;
        }
        messagesRendered = true;
        lastFirstMessage = key;
        LinearLayout box = binding.messagesContainer;
        box.removeAllViews();
        if (t.messages.isEmpty()) {
            box.addView(messageView(UNKNOWN, R.color.sf_muted));
            return;
        }
        for (int i = 0; i < Math.min(6, t.messages.size()); i++) {
            StatusMessage m = t.messages.get(i);
            box.addView(messageView(m.text, UiFormat.severityColor(m.severity)));
        }
    }

    private TextView messageView(String text, int colorRes) {
        TextView tv = new TextView(requireContext());
        tv.setText(text);
        tv.setTextSize(12);
        tv.setTextColor(ContextCompat.getColor(requireContext(), colorRes));
        return tv;
    }
}
