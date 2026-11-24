package org.safeflight.android.diagnostics

import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

enum class LogLevel { DEBUG, INFO, WARN, ERROR }

data class LogEntry(val atMs: Long, val level: LogLevel, val source: String, val message: String)

/** In-memory ring buffer shown in the Connection screen and mirrored to logcat. */
class DiagnosticsLog(private val capacity: Int = 200, private val clock: () -> Long = System::currentTimeMillis) {
    private val _entries = MutableStateFlow<List<LogEntry>>(emptyList())
    val entries: StateFlow<List<LogEntry>> = _entries.asStateFlow()

    @Volatile
    var verbose: Boolean = false

    fun log(level: LogLevel, source: String, message: String) {
        if (level == LogLevel.DEBUG && !verbose) return
        val entry = LogEntry(clock(), level, source, message)
        _entries.update { (listOf(entry) + it).take(capacity) }
        try {
            val tag = "SafeFlight/$source"
            when (level) {
                LogLevel.DEBUG -> Log.d(tag, message)
                LogLevel.INFO -> Log.i(tag, message)
                LogLevel.WARN -> Log.w(tag, message)
                LogLevel.ERROR -> Log.e(tag, message)
            }
        } catch (_: RuntimeException) {
            // android.util.Log is not available in JVM unit tests.
        }
    }

    fun info(source: String, message: String) = log(LogLevel.INFO, source, message)
    fun warn(source: String, message: String) = log(LogLevel.WARN, source, message)
    fun error(source: String, message: String) = log(LogLevel.ERROR, source, message)
    fun debug(source: String, message: String) = log(LogLevel.DEBUG, source, message)
}
