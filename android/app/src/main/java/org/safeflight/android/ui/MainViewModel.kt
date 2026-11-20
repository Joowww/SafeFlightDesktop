package org.safeflight.android.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewmodel.CreationExtras
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.safeflight.android.AppContainer
import org.safeflight.android.SafeFlightApplication
import org.safeflight.android.config.ConnectionProfile
import org.safeflight.android.config.ProfileValidator
import org.safeflight.android.control.CommandDecision
import org.safeflight.android.control.CommandGate
import org.safeflight.android.control.FlightCommand

/**
 * Presentation state holder. Telemetry and profiles live in the application
 * container so that they survive activity recreation; the video player is
 * owned by the activity because it is bound to the surface lifecycle.
 */
class MainViewModel(private val container: AppContainer) : ViewModel() {
    val telemetry = container.mavlink.telemetry
    val link = container.mavlink.link
    val counters = container.mavlink.counters
    val profiles = container.profiles.document
    val logEntries = container.log.entries
    val missions = container.missions.missions
    val missionSource = container.missions.source

    private val _message = MutableStateFlow<String?>(null)
    val message: StateFlow<String?> = _message.asStateFlow()

    val activeProfile: ConnectionProfile get() = container.profiles.active

    fun connectTelemetry() {
        val profile = container.profiles.active
        val errors = ProfileValidator.validate(profile).filterNot { it.startsWith("RTP/UDP") }
        if (errors.isNotEmpty()) {
            _message.value = "Perfil no válido para telemetría: ${errors.joinToString("; ")}"
            return
        }
        container.log.verbose = profile.diagnostics.verboseLogging
        container.mavlink.connect(profile.mavlink, profile.timeouts.telemetryStaleS)
    }

    fun disconnectTelemetry() = container.mavlink.disconnect()

    fun selectProfile(id: String) {
        val wasRunning = container.mavlink.isRunning
        container.profiles.select(id)
        container.log.info("Perfiles", "Perfil seleccionado: ${container.profiles.active.name}")
        if (wasRunning) connectTelemetry()
    }

    fun saveProfile(profile: ConnectionProfile): List<String> {
        val errors = container.profiles.save(profile)
        if (errors.isEmpty()) {
            container.profiles.select(profile.id)
            container.log.info("Perfiles", "Perfil guardado: ${profile.name}")
            if (container.mavlink.isRunning) connectTelemetry()
        }
        return errors
    }

    fun duplicateProfile(id: String) = container.profiles.duplicate(id).also { container.profiles.select(it.id) }
    fun restoreProfile(id: String) = container.profiles.restore(id)
    fun deleteProfile(id: String) = try {
        container.profiles.delete(id); null
    } catch (e: IllegalArgumentException) {
        e.message
    }
    fun newProfile(): ConnectionProfile {
        val base = container.profiles.active
        val profile = base.copy(id = container.profiles.newProfileId(), name = "Nuevo perfil", kind = "custom", builtin = false, notes = "")
        return profile
    }

    fun evaluate(command: FlightCommand): CommandDecision =
        CommandGate.evaluate(command, telemetry.value, link.value)

    fun requestCommand(command: FlightCommand) {
        val decision = evaluate(command)
        if (decision is CommandDecision.Blocked) {
            container.log.warn("Control", "${command.label} rechazado: ${decision.reasons.first()}")
            _message.value = "${command.label} no disponible: ${decision.reasons.first()}"
        }
    }

    fun consumeMessage() {
        _message.value = null
    }

    fun logVideo(message: String) = container.log.info("Vídeo", message)

    override fun onCleared() {
        // Telemetry is application-scoped; it is released when the process ends
        // or when the operator disconnects explicitly.
        super.onCleared()
    }

    companion object {
        val Factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>, extras: CreationExtras): T {
                val app = checkNotNull(extras[ViewModelProvider.AndroidViewModelFactory.APPLICATION_KEY]) as SafeFlightApplication
                return MainViewModel(app.container) as T
            }
        }
    }
}
