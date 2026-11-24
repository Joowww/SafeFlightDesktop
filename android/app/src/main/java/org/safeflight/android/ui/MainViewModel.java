package org.safeflight.android.ui;

import androidx.annotation.NonNull;
import androidx.lifecycle.LiveData;
import androidx.lifecycle.MutableLiveData;
import androidx.lifecycle.ViewModel;
import androidx.lifecycle.ViewModelProvider;

import org.safeflight.android.AppContainer;
import org.safeflight.android.config.ConnectionProfile;
import org.safeflight.android.config.ProfileRepository;
import org.safeflight.android.config.ProfileValidator;
import org.safeflight.android.config.ProfilesDocument;
import org.safeflight.android.control.CommandDecision;
import org.safeflight.android.control.CommandGate;
import org.safeflight.android.control.FlightCommand;
import org.safeflight.android.diagnostics.DiagnosticsLog;
import org.safeflight.android.diagnostics.LogEntry;
import org.safeflight.android.mavlink.MavlinkClient;
import org.safeflight.android.mavlink.MavlinkCounters;
import org.safeflight.android.mission.Mission;
import org.safeflight.android.mission.MissionSourceKind;
import org.safeflight.android.state.LinkState;
import org.safeflight.android.state.TelemetryState;

import java.util.ArrayList;
import java.util.List;

/**
 * State holder shared by the three screens.
 *
 * <p>Telemetry, profiles and the log live in the {@link AppContainer} (they
 * survive activity recreation). This class listens to them and republishes
 * their state as {@link LiveData}, which the screens observe. Background
 * threads use {@code postValue}; the main thread uses {@code setValue}.
 * The video player is owned by the activity (see {@link VideoHost}).
 */
public final class MainViewModel extends ViewModel {
    private final AppContainer container;

    /** Telemetry at most 5 times per second, counters once per second (calm UI, low CPU). */
    private final ThrottledLiveData<TelemetryState> telemetry;
    private final MutableLiveData<LinkState> link;
    private final ThrottledLiveData<MavlinkCounters> counters;
    private final MutableLiveData<ProfilesDocument> profiles;
    private final MutableLiveData<List<LogEntry>> logEntries;
    private final MutableLiveData<String> message = new MutableLiveData<>(null);
    private final Object linkLock = new Object();
    private LinkState lastPostedLink;
    private long lastLinkPostMs = 0;

    private final MavlinkClient.Listener mavlinkListener = new MavlinkClient.Listener() {
        @Override
        public void onTelemetry(TelemetryState value) {
            telemetry.offer(value);
        }

        @Override
        public void onLink(LinkState value) {
            // State changes (CONECTADO/OBSOLETO/PERDIDO, errors) are shown at once; when only
            // the heartbeat age changed (every 250 ms) the screen is refreshed once per second.
            long now = android.os.SystemClock.uptimeMillis();
            synchronized (linkLock) {
                boolean significant = lastPostedLink == null
                        || value.status != lastPostedLink.status
                        || value.reconnectAttempts != lastPostedLink.reconnectAttempts
                        || !java.util.Objects.equals(value.lastError, lastPostedLink.lastError)
                        || !java.util.Objects.equals(value.endpoint, lastPostedLink.endpoint);
                if (!significant && now - lastLinkPostMs < 1000) {
                    return;
                }
                lastPostedLink = value;
                lastLinkPostMs = now;
            }
            link.postValue(value);
        }

        @Override
        public void onCounters(MavlinkCounters value) {
            counters.offer(value);
        }
    };
    private final ProfileRepository.Listener profilesListener;
    private final DiagnosticsLog.Listener logListener;

    public MainViewModel(AppContainer container) {
        this.container = container;
        telemetry = new ThrottledLiveData<>(container.mavlink.getTelemetry(), 200);
        link = new MutableLiveData<>(container.mavlink.getLink());
        counters = new ThrottledLiveData<>(container.mavlink.getCounters(), 1000);
        profiles = new MutableLiveData<>(container.profiles.getDocument());
        logEntries = new MutableLiveData<>(container.log.getEntries());

        profilesListener = profiles::postValue;
        logListener = logEntries::postValue;
        container.mavlink.addListener(mavlinkListener);
        container.profiles.addListener(profilesListener);
        container.log.addListener(logListener);
    }

    // ---------------------------------------------------------------- state
    public LiveData<TelemetryState> getTelemetry() {
        return telemetry.asLiveData();
    }

    public LiveData<LinkState> getLink() {
        return link;
    }

    public LiveData<MavlinkCounters> getCounters() {
        return counters.asLiveData();
    }

    public LiveData<ProfilesDocument> getProfiles() {
        return profiles;
    }

    public LiveData<List<LogEntry>> getLogEntries() {
        return logEntries;
    }

    /** One-shot message for a Snackbar; call {@link #consumeMessage()} once shown. */
    public LiveData<String> getMessage() {
        return message;
    }

    public List<Mission> getMissions() {
        return container.missions.getMissions();
    }

    public MissionSourceKind getMissionSource() {
        return container.missions.getSource();
    }

    public ConnectionProfile getActiveProfile() {
        return container.profiles.getActive();
    }

    // ------------------------------------------------------------- telemetry
    public void connectTelemetry() {
        ConnectionProfile profile = container.profiles.getActive();
        List<String> errors = new ArrayList<>();
        for (String error : ProfileValidator.validate(profile)) {
            if (!error.startsWith("RTP/UDP")) { // video problems do not prevent telemetry
                errors.add(error);
            }
        }
        if (!errors.isEmpty()) {
            message.setValue("Perfil no válido para telemetría: " + String.join("; ", errors));
            return;
        }
        container.log.setVerbose(profile.diagnostics.verboseLogging);
        container.mavlink.connect(profile.mavlink, profile.timeouts.telemetryStaleS);
    }

    public void disconnectTelemetry() {
        container.mavlink.disconnect();
    }

    // -------------------------------------------------------------- profiles
    public void selectProfile(String id) {
        boolean wasRunning = container.mavlink.isRunning();
        container.profiles.select(id);
        container.log.info("Perfiles", "Perfil seleccionado: " + container.profiles.getActive().name);
        if (wasRunning) {
            connectTelemetry();
        }
    }

    /** Saves and activates {@code profile}; returns validation errors (empty when saved). */
    public List<String> saveProfile(ConnectionProfile profile) {
        List<String> errors = container.profiles.save(profile);
        if (errors.isEmpty()) {
            container.profiles.select(profile.id);
            container.log.info("Perfiles", "Perfil guardado: " + profile.name);
            if (container.mavlink.isRunning()) {
                connectTelemetry();
            }
        }
        return errors;
    }

    public void duplicateProfile(String id) {
        ConnectionProfile clone = container.profiles.duplicate(id);
        container.profiles.select(clone.id);
    }

    public void restoreProfile(String id) {
        container.profiles.restore(id);
    }

    /** Returns an error message, or {@code null} when the profile was deleted. */
    public String deleteProfile(String id) {
        try {
            container.profiles.delete(id);
            return null;
        } catch (IllegalArgumentException e) {
            return e.getMessage();
        }
    }

    // --------------------------------------------------------------- control
    public CommandDecision evaluate(FlightCommand command) {
        return CommandGate.evaluate(command, container.mavlink.getTelemetry(), container.mavlink.getLink());
    }

    /** Every command is refused by {@link CommandGate}; the reason is logged and shown. */
    public void requestCommand(FlightCommand command) {
        CommandDecision decision = evaluate(command);
        if (decision.isBlocked()) {
            String reason = decision.getReasons().get(0);
            container.log.warn("Control", command.label + " rechazado: " + reason);
            message.setValue(command.label + " no disponible: " + reason);
        }
    }

    public void consumeMessage() {
        message.setValue(null);
    }

    @Override
    protected void onCleared() {
        // Telemetry keeps running at application scope; only the listeners are removed.
        container.mavlink.removeListener(mavlinkListener);
        container.profiles.removeListener(profilesListener);
        container.log.removeListener(logListener);
        super.onCleared();
    }

    /** Creates the view model with the application container. */
    public static ViewModelProvider.Factory factory(AppContainer container) {
        return new ViewModelProvider.Factory() {
            @NonNull
            @Override
            @SuppressWarnings("unchecked")
            public <T extends ViewModel> T create(@NonNull Class<T> modelClass) {
                return (T) new MainViewModel(container);
            }
        };
    }
}
