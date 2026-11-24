package org.safeflight.android.ui;

import android.os.Bundle;
import android.text.SpannableStringBuilder;
import android.text.Spanned;
import android.text.TextUtils;
import android.text.style.ForegroundColorSpan;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.EditText;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.core.content.ContextCompat;
import androidx.fragment.app.Fragment;
import androidx.lifecycle.ViewModelProvider;

import com.google.android.material.chip.Chip;
import com.google.android.material.dialog.MaterialAlertDialogBuilder;

import org.safeflight.android.R;
import org.safeflight.android.config.ConnectionProfile;
import org.safeflight.android.config.ProfilesDocument;
import org.safeflight.android.databinding.FragmentConnectionBinding;
import org.safeflight.android.diagnostics.LogEntry;
import org.safeflight.android.diagnostics.LogLevel;
import org.safeflight.android.mavlink.MavlinkCounters;
import org.safeflight.android.state.LinkState;
import org.safeflight.android.state.LinkStatus;
import org.safeflight.android.video.VideoController;
import org.safeflight.android.video.VideoState;
import org.safeflight.android.video.VideoStatus;

import java.text.SimpleDateFormat;
import java.util.Collections;
import java.util.Date;
import java.util.List;
import java.util.Locale;

import static org.safeflight.android.ui.UiFormat.UNKNOWN;
import static org.safeflight.android.ui.UiFormat.fmt;

/**
 * Connection screen (layout: res/layout/fragment_connection.xml).
 *
 * <p>Left: editor of the active profile. The form is filled from the stored
 * profile ({@link #bindForm}) and converted back with {@link #readForm} when
 * "Guardar" is pressed; nothing is stored until then. Right: telemetry and
 * video diagnostics and the log.
 */
public final class ConnectionFragment extends Fragment {
    private static final int LOG_LINES = 40;

    private FragmentConnectionBinding binding;
    private MainViewModel viewModel;
    private VideoHost host;
    private VideoController video;

    /** Profile currently shown in the form (reference comparison detects changes). */
    private ConnectionProfile boundProfile;
    /** Document whose profiles are shown as chips. */
    private ProfilesDocument chipsDocument;
    /** True while the form is filled from code, so listeners do not react. */
    private boolean bindingForm = false;
    private final SimpleDateFormat timeFormat = new SimpleDateFormat("HH:mm:ss", Locale.US);

    @Nullable
    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, @Nullable ViewGroup container,
                             @Nullable Bundle savedInstanceState) {
        binding = FragmentConnectionBinding.inflate(inflater, container, false);
        return binding.getRoot();
    }

    @Override
    public void onViewCreated(@NonNull View view, @Nullable Bundle savedInstanceState) {
        viewModel = new ViewModelProvider(requireActivity()).get(MainViewModel.class);
        host = (VideoHost) requireActivity();
        video = host.getVideo();

        setUpListeners();

        video.onSurfaceAttached();
        video.getPlayer().observe(getViewLifecycleOwner(), p -> binding.previewPlayerView.setPlayer(p));
        viewModel.getProfiles().observe(getViewLifecycleOwner(), this::renderProfiles);
        viewModel.getLink().observe(getViewLifecycleOwner(), l -> renderTelemetry());
        viewModel.getCounters().observe(getViewLifecycleOwner(), c -> renderTelemetry());
        video.getState().observe(getViewLifecycleOwner(), this::renderVideo);
        viewModel.getLogEntries().observe(getViewLifecycleOwner(), this::renderLog);
    }

    @Override
    public void onDestroyView() {
        binding.previewPlayerView.setPlayer(null);
        video.onSurfaceDetached();
        binding = null;
        boundProfile = null;
        chipsDocument = null;
        super.onDestroyView();
    }

    // ------------------------------------------------------------ listeners
    private void setUpListeners() {
        binding.transportChips.setOnCheckedStateChangeListener((group, checkedIds) -> {
            boolean remote = checkedIds.contains(R.id.chip_udp_connect);
            showTransportFields(remote);
            if (remote && !bindingForm) {
                // A remote endpoint only learns this station's address from its heartbeats.
                binding.switchGcsHeartbeat.setChecked(true);
            }
        });

        binding.buttonSave.setOnClickListener(v -> save());
        binding.buttonDuplicate.setOnClickListener(v -> {
            if (boundProfile != null) {
                viewModel.duplicateProfile(boundProfile.id);
            }
        });
        binding.buttonReset.setOnClickListener(v -> confirmReset());
        binding.buttonDelete.setOnClickListener(v -> {
            if (boundProfile != null) {
                String error = viewModel.deleteProfile(boundProfile.id);
                showErrors(error == null ? Collections.<String>emptyList() : Collections.singletonList(error));
            }
        });

        binding.buttonConnect.setOnClickListener(v -> viewModel.connectTelemetry());
        binding.buttonDisconnect.setOnClickListener(v -> viewModel.disconnectTelemetry());
        binding.buttonRestartVideo.setOnClickListener(v -> host.restartVideo());
        binding.buttonStopVideo.setOnClickListener(v -> host.stopVideo());
    }

    private void showTransportFields(boolean remote) {
        binding.listenFields.setVisibility(remote ? View.GONE : View.VISIBLE);
        binding.connectFields.setVisibility(remote ? View.VISIBLE : View.GONE);
    }

    private void save() {
        ConnectionProfile profile = readForm();
        if (profile == null) {
            showErrors(Collections.singletonList(getString(R.string.numeric_fields_error)));
            return;
        }
        List<String> errors = viewModel.saveProfile(profile);
        showErrors(errors);
        if (errors.isEmpty()) {
            host.restartVideo();
        }
    }

    private void confirmReset() {
        if (boundProfile == null) {
            return;
        }
        final String id = boundProfile.id;
        new MaterialAlertDialogBuilder(requireContext())
                .setTitle(R.string.reset_title)
                .setMessage(R.string.reset_message)
                .setPositiveButton(R.string.reset_confirm, (dialog, which) -> {
                    viewModel.restoreProfile(id);
                    host.restartVideo();
                })
                .setNegativeButton(R.string.cancel, null)
                .show();
    }

    private void showErrors(List<String> errors) {
        if (errors.isEmpty()) {
            binding.formErrors.setVisibility(View.GONE);
            return;
        }
        StringBuilder sb = new StringBuilder();
        for (String e : errors) {
            if (sb.length() > 0) {
                sb.append('\n');
            }
            sb.append("• ").append(e);
        }
        binding.formErrors.setText(sb.toString());
        binding.formErrors.setVisibility(View.VISIBLE);
    }

    // -------------------------------------------------------------- profiles
    private void renderProfiles(ProfilesDocument doc) {
        if (binding == null || doc == null || doc.profiles.isEmpty()) {
            return;
        }
        if (doc != chipsDocument) {
            chipsDocument = doc;
            binding.profileChips.removeAllViews();
            LayoutInflater inflater = LayoutInflater.from(requireContext());
            for (ConnectionProfile p : doc.profiles) {
                Chip chip = (Chip) inflater.inflate(R.layout.item_profile_chip, binding.profileChips, false);
                chip.setText(p.name);
                chip.setCheckable(true);
                chip.setChecked(p.id.equals(doc.activeProfileId));
                final String id = p.id;
                chip.setOnClickListener(v -> selectProfile(id));
                binding.profileChips.addView(chip);
            }
        }
        ConnectionProfile active = doc.active();
        if (active != boundProfile) {
            bindForm(active);
        }
    }

    private void selectProfile(String id) {
        if (boundProfile != null && boundProfile.id.equals(id)) {
            renderProfiles(chipsDocument); // keep the chip checked
            return;
        }
        viewModel.selectProfile(id);
        if (video.currentState().status != VideoStatus.IDLE) {
            host.restartVideo();
        }
    }

    /** Copies the stored profile into the form fields. */
    private void bindForm(ConnectionProfile p) {
        bindingForm = true;
        boundProfile = p;
        showErrors(Collections.<String>emptyList());
        binding.profileNotes.setText(p.notes);
        binding.profileNotes.setVisibility(TextUtils.isEmpty(p.notes) ? View.GONE : View.VISIBLE);
        binding.editName.setText(p.name);
        boolean remote = "udp_connect".equals(p.mavlink.transport);
        binding.transportChips.check(remote ? R.id.chip_udp_connect : R.id.chip_udp_listen);
        showTransportFields(remote);
        binding.editLocalHost.setText(p.mavlink.localHost);
        binding.editLocalPort.setText(String.valueOf(p.mavlink.localPort));
        binding.editRemoteHost.setText(p.mavlink.remoteHost);
        binding.editRemotePort.setText(String.valueOf(p.mavlink.remotePort));
        binding.switchGcsHeartbeat.setChecked(p.mavlink.sendGcsHeartbeat);
        binding.videoModeChips.check("none".equals(p.video.mode) ? R.id.chip_no_video : R.id.chip_rtsp);
        binding.rtspTransportChips.check("udp".equals(p.video.rtspTransport) ? R.id.chip_udp : R.id.chip_tcp);
        binding.editRtspUrl.setText(p.video.rtspUrl);
        binding.editStale.setText(String.valueOf(p.timeouts.telemetryStaleS));
        binding.editVideoStale.setText(String.valueOf(p.timeouts.videoStaleS));
        binding.editVideoRetry.setText(String.valueOf(p.timeouts.videoReconnectIntervalS));
        binding.switchVerbose.setChecked(p.diagnostics.verboseLogging);
        binding.buttonDelete.setVisibility(p.builtin ? View.GONE : View.VISIBLE);
        bindingForm = false;
    }

    /** Builds a profile from the form, or {@code null} when a numeric field is not a number. */
    private ConnectionProfile readForm() {
        if (boundProfile == null) {
            return null;
        }
        try {
            ConnectionProfile p = boundProfile.copy();
            p.name = text(binding.editName);
            p.mavlink.transport = binding.transportChips.getCheckedChipId() == R.id.chip_udp_connect
                    ? "udp_connect" : "udp_listen";
            p.mavlink.localHost = text(binding.editLocalHost);
            p.mavlink.localPort = Integer.parseInt(text(binding.editLocalPort));
            p.mavlink.remoteHost = text(binding.editRemoteHost);
            p.mavlink.remotePort = Integer.parseInt(text(binding.editRemotePort));
            p.mavlink.sendGcsHeartbeat = binding.switchGcsHeartbeat.isChecked();
            p.video.mode = binding.videoModeChips.getCheckedChipId() == R.id.chip_no_video ? "none" : "rtsp";
            p.video.rtspTransport = binding.rtspTransportChips.getCheckedChipId() == R.id.chip_udp ? "udp" : "tcp";
            p.video.rtspUrl = text(binding.editRtspUrl);
            p.timeouts.telemetryStaleS = Double.parseDouble(text(binding.editStale));
            p.timeouts.videoStaleS = Double.parseDouble(text(binding.editVideoStale));
            p.timeouts.videoReconnectIntervalS = Double.parseDouble(text(binding.editVideoRetry));
            p.diagnostics.verboseLogging = binding.switchVerbose.isChecked();
            return p;
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private static String text(EditText field) {
        return field.getText() == null ? "" : field.getText().toString().trim();
    }

    // ----------------------------------------------------------- diagnostics
    private void renderTelemetry() {
        if (binding == null) {
            return;
        }
        LinkState link = viewModel.getLink().getValue();
        MavlinkCounters c = viewModel.getCounters().getValue();
        if (link == null || c == null) {
            return;
        }
        binding.chipLink.bind(UiFormat.linkLabel(link.status), UiFormat.linkColor(link.status), null);
        binding.rowEndpoint.setValue(TextUtils.isEmpty(link.endpoint) ? UNKNOWN : link.endpoint);
        binding.rowLastHeartbeat.setValue(link.heartbeatAgeMs != null
                ? fmt(link.heartbeatAgeMs / 1000.0, 1, " s") : UNKNOWN);
        binding.rowDatagrams.setValue(String.valueOf(c.datagrams));
        binding.rowFrames.setValue(c.framesAccepted + " / " + c.framesRejected);
        binding.rowGcsSent.setValue(String.valueOf(c.gcsHeartbeatsSent));
        binding.rowSocketRetries.setValue(String.valueOf(link.reconnectAttempts));
        binding.linkError.setVisibility(link.lastError != null ? View.VISIBLE : View.GONE);
        binding.linkError.setText(link.lastError);
        binding.buttonDisconnect.setEnabled(link.status != LinkStatus.DISCONNECTED);
    }

    private void renderVideo(VideoState v) {
        if (binding == null || v == null) {
            return;
        }
        binding.chipVideoState.bind(UiFormat.videoLabel(v.status), UiFormat.videoColor(v.status), null);
        binding.rowUrl.setValue(TextUtils.isEmpty(v.url) ? UNKNOWN : v.url);
        binding.rowResolution.setValue(v.width != null ? v.width + "x" + v.height : UNKNOWN);
        binding.rowFrameAge.setValue(v.lastFrameAgeMs != null ? v.lastFrameAgeMs + " ms" : UNKNOWN);
        binding.rowFramesRendered.setValue(String.valueOf(v.framesRendered));
        binding.rowVideoRetries.setValue(String.valueOf(v.retries));
        binding.videoError.setVisibility(v.lastError != null ? View.VISIBLE : View.GONE);
        binding.videoError.setText(v.lastError);
    }

    private void renderLog(List<LogEntry> entries) {
        if (binding == null || entries == null) {
            return;
        }
        SpannableStringBuilder sb = new SpannableStringBuilder();
        for (int i = 0; i < Math.min(LOG_LINES, entries.size()); i++) {
            LogEntry e = entries.get(i);
            int start = sb.length();
            if (start > 0) {
                sb.append('\n');
                start++;
            }
            sb.append(timeFormat.format(new Date(e.atMs))).append(' ')
                    .append(e.source).append(": ").append(e.message);
            int color = e.level == LogLevel.ERROR ? R.color.sf_danger
                    : e.level == LogLevel.WARN ? R.color.sf_warn : R.color.sf_muted;
            sb.setSpan(new ForegroundColorSpan(ContextCompat.getColor(requireContext(), color)),
                    start, sb.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        }
        binding.logText.setText(sb);
    }
}
