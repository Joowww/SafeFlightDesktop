# SafeFlight Android en Java: guía para entender, modificar y compilar la app

Rama `feature/android-java-migration`. Proyecto Gradle en `android/`; módulo de la app en
`android/app/`. Todo el código de la aplicación está en Java y todas las pantallas en XML.
Los archivos `*.gradle.kts` son solo configuración de compilación.

| Pieza | Tecnología |
|---|---|
| Lenguaje | Java 17 (sin Kotlin) |
| Interfaz | Android Views + XML + ViewBinding, Material Components 3 (`com.google.android.material`) |
| Estado de pantalla | `ViewModel` + `LiveData` (AndroidX Lifecycle) |
| Vídeo | Media3 ExoPlayer + `RtspMediaSource` (API Java) |
| Telemetría | Parser MAVLink propio, `java.net.DatagramSocket` en un hilo |
| Persistencia | `SharedPreferences` + JSON (`org.json`) |
| Compilación | Gradle 8 / AGP 8.13, `minSdk 26`, `targetSdk 35`, `compileSdk 36` |

## 1. Paquetes Java (`android/app/src/main/java/org/safeflight/android/`)

| Paquete | Qué hace | Clases principales |
|---|---|---|
| (raíz) | Arranque y unión de piezas | `SafeFlightApplication` (crea el contenedor), `AppContainer` (objetos de larga vida), `MainActivity` (única actividad), `SharedPreferencesStore` |
| `mavlink` | Recibir y decodificar MAVLink | `MavlinkClient` (UDP + hilos), `MavlinkParser` (tramas v1/v2 y CRC), `MavlinkDecoder` (bytes → mensaje), `MavlinkMessage` (Heartbeat, SysStatus, GpsRawInt...), `GcsHeartbeatEncoder` (único codificador), `MavlinkIds`, `MavlinkCrc`, `ArduCopterModes` |
| `state` | Estado del vehículo y del enlace | `TelemetryState`, `TelemetryReducer` (aplica mensajes), `LinkState`/`LinkStatus`, `LinkSupervisor` (CONECTADO/OBSOLETO/PERDIDO) |
| `control` | Bloqueo de comandos | `CommandGate`, `FlightCommand`, `CommandDecision` |
| `config` | Perfiles de conexión | `ConnectionProfile` (+ `MavlinkSettings`, `VideoSettings`, `TimeoutSettings`, `DiagnosticsSettings`), `ProfileRepository`, `ProfileJson`, `ProfileValidator`, `DefaultProfiles`, `KeyValueStore` |
| `video` | Vídeo RTSP | `VideoController` (ExoPlayer), `VideoSupervisor` (reglas puras), `VideoState`/`VideoStatus` |
| `diagnostics` | Registro en pantalla y logcat | `DiagnosticsLog`, `LogEntry`, `LogLevel` |
| `mission` | Misiones (solo datos DEMO) | `MissionRepository`, `DemoMissionRepository`, `Mission` |
| `ui` | Pantallas | `MainViewModel`, `FlightFragment`, `ConnectionFragment`, `MissionsFragment`, `UiFormat`, `VideoHost`, `ThrottledLiveData` |
| `ui.widget` | Vistas propias reutilizables | `StatusChipView` («● CONECTADO»), `TelemetryRowView` (fila «etiqueta … valor») |

Las clases de `mavlink`, `state`, `control`, `config`, `video.VideoSupervisor` y `mission` no
dependen de pantallas, así que se prueban con JUnit en el PC (`android/app/src/test/java`).

## 2. Pantallas: XML ↔ Java

| Pantalla | Layout (`app/src/main/res/layout/`) | Clase Java | Clase de ViewBinding generada |
|---|---|---|---|
| Ventana principal y menú lateral | `activity_main.xml` + `res/menu/nav_rail.xml` | `MainActivity` | `ActivityMainBinding` |
| Vuelo | `fragment_flight.xml` | `ui/FlightFragment` | `FragmentFlightBinding` |
| Conexión | `fragment_connection.xml` (+ `item_profile_chip.xml`) | `ui/ConnectionFragment` | `FragmentConnectionBinding` |
| Misiones | `fragment_missions.xml` (+ `item_mission.xml`) | `ui/MissionsFragment` | `FragmentMissionsBinding`, `ItemMissionBinding` |
| Indicador de estado | `view_status_chip.xml` | `ui/widget/StatusChipView` | `ViewStatusChipBinding` |
| Fila de telemetría | `view_telemetry_row.xml` | `ui/widget/TelemetryRowView` | `ViewTelemetryRowBinding` |

**ViewBinding:** por cada layout, Gradle genera una clase con un campo por cada `android:id`.
Por ejemplo, `android:id="@+id/row_rel_alt"` en `fragment_flight.xml` se usa en Java como
`binding.rowRelAlt`. No hace falta `findViewById`.

Los textos fijos están en `res/values/strings.xml`, los colores en `res/values/colors.xml`
(`sf_ok`, `sf_warn`, `sf_danger`…) y los estilos en `res/values/themes.xml`.

## 3. Dónde se recibe y procesa MAVLink

```
MavlinkClient.receiveLoop()               hilo "mavlink-receive"
  └─ DatagramSocket.receive(packet)
  └─ MavlinkParser.feed(bytes)            busca tramas, valida CRC + CRC_EXTRA
       └─ MavlinkDecoder.decode(...)      bytes → MavlinkMessage.Heartbeat / SysStatus / ...
  └─ TelemetryReducer.reduce(state, msg)  nuevo TelemetryState (nunca modifica el anterior)
  └─ Listener.onTelemetry(state)
MavlinkClient.supervise()                 cada 250 ms: LinkSupervisor.evaluate(...)
  └─ Listener.onLink(linkState)           CONECTADO / OBSOLETO / PERDIDO / ERROR
MainViewModel                             recibe los Listener → LiveData (telemetría ≤ 5 Hz)
FlightFragment.render()                   observa el LiveData y pinta chips y filas
```

- **Conectar:** el botón «Conectar» (`ConnectionFragment`) llama a `MainViewModel.connectTelemetry()`, que valida el perfil y llama a `MavlinkClient.connect(settings, telemetryStaleS)`.
- **Modos de UDP:** `udp_listen` abre un puerto local. `udp_connect` envía el heartbeat de GCS al remoto para que este conozca la dirección de la estación.
- **Pérdida y reconexión:** si se pierde el enlace, `LinkSupervisor` lo marca a partir de la edad del último heartbeat del vehículo. Si falla el socket, se reintenta cada `reconnectDelayMs`.
- **Mensajes añadidos:** para decodificar uno nuevo hay que darlo de alta en `MavlinkIds`, crear su subclase en `MavlinkMessage`, añadir su `case` en `MavlinkDecoder` y su efecto en `TelemetryReducer`. Después se añade un vector a `shared/protocols/mavlink-test-vectors.json` para que lo comprueben Desktop y Android.

## 4. Dónde se reproduce el vídeo RTSP

- **`video/VideoController`:**
  - `start(...)` aplica el perfil.
  - `openPlayer(...)` crea el `ExoPlayer` con `RtspMediaSource` (TCP o UDP) y búferes pequeños para baja latencia.
  - Un `Runnable ticker` cada 250 ms vigila la edad del último fotograma; si se congela o no llega, reabre la sesión.
  - `stop()` libera el decodificador.
- **`MainActivity`:** posee el `VideoController`. Lo arranca en `onStart()` y lo detiene en `onStop()` (pantalla apagada o app en segundo plano).
- **Pantallas:** las que muestran vídeo tienen un `androidx.media3.ui.PlayerView` en su XML. En `onViewCreated` observan `video.getPlayer()` y llaman a `playerView.setPlayer(player)`; en `onDestroyView` lo sueltan.
- **Detección de congelación:** `video.onSurfaceAttached()`/`onSurfaceDetached()` indican si hay alguna superficie visible. Sin superficie no se juzga la congelación.

## 5. Cómo se guarda la configuración

- `config/ProfileRepository` guarda un `ProfilesDocument` (lista de perfiles más el perfil activo).
- Cada cambio (`save`, `select`, `duplicate`, `restore`, `delete`) crea un documento nuevo y lo escribe con `persist()`.
- El JSON lo genera `ProfileJson.toJson(...)` con las claves `snake_case` del esquema compartido con Desktop (`shared/schemas/connection-profiles.schema.json`).
- Se almacena con `SharedPreferencesStore` en el archivo privado `shared_prefs/safeflight.xml`, clave `connection_profiles_json`.
- Si el JSON está dañado, se restauran los valores de fábrica (`DefaultProfiles`) y el texto original se guarda en `connection_profiles_json_corrupt`.
- Antes de guardar se valida con `ProfileValidator.validate(profile)`; si devuelve errores, no se guarda nada.

## 6. Dónde se bloquean los comandos peligrosos

1. **`control/CommandGate`:**
   - La constante `PHYSICAL_COMMANDS_ENABLED = false` hace que `evaluate(...)` nunca devuelva «permitido».
   - Todos los botones de `FlightCommand` (ARM, DISARM, TAKEOFF, LAND, MODO, INICIAR/DETENER MISIÓN) pasan por `MainViewModel.requestCommand(...)`, que solo registra y muestra el motivo del bloqueo.
2. **Sin codificadores de comandos:** la capa MAVLink no tiene ninguno. El único marco que la app puede enviar es el HEARTBEAT de GCS (`GcsHeartbeatEncoder`), y es opcional según el perfil.
3. **Tests que lo comprueban:**
   - `CommandGateTest`: todo comando queda bloqueado, sea cual sea el estado del vehículo.
   - `SafetyStructureTest`: no hay `.kt` en la app; el único `.send(` está en `MavlinkClient` y envía `encoder.encode()`; no existen ids de COMMAND_LONG, SET_MODE, MISSION_* ni RC override.

Cambiar `PHYSICAL_COMMANDS_ENABLED` no basta para mandar nada: haría falta escribir un codificador de comandos, y eso debe ser una fase propia con su análisis de seguridad.

## 7. Cómo añadir un botón o una pantalla

**Un botón en la pantalla de Vuelo:**
1. En `res/layout/fragment_flight.xml`, dentro del panel:
   ```xml
   <com.google.android.material.button.MaterialButton
       android:id="@+id/button_center_map"
       android:layout_width="wrap_content"
       android:layout_height="wrap_content"
       android:text="@string/button_center_map" />
   ```
2. En `res/values/strings.xml`: `<string name="button_center_map">Centrar</string>`.
3. En `FlightFragment.onViewCreated(...)`:
   ```java
   binding.buttonCenterMap.setOnClickListener(v -> viewModel.algunaAccion());
   ```
   La lógica va en `MainViewModel` o en una clase de dominio, no en el fragmento.

**Una pantalla nueva** (por ejemplo, «Registro»):
1. Crea `res/layout/fragment_log.xml`.
2. Crea `ui/LogFragment.java`, copiando la estructura de `MissionsFragment`: `onCreateView` infla `FragmentLogBinding` y `onViewCreated` obtiene `MainViewModel` con `new ViewModelProvider(requireActivity()).get(MainViewModel.class)`.
3. Añade el elemento en `res/menu/nav_rail.xml` (`android:id="@+id/nav_log"`, icono y título).
4. Añade la rama en `MainActivity.showScreen(...)`: `else if (itemId == R.id.nav_log) screen = new LogFragment();`.

## 8. Abrir, compilar y ejecutar en Android Studio

1. *File → Open* y selecciona la carpeta **`android/`** del repositorio (no la raíz).
2. *Settings → Build Tools → Gradle → Gradle JDK*: el JBR de Android Studio (17 o superior). Espera al *Gradle Sync*.
3. Si falta el SDK, Android Studio crea `android/local.properties` (no se versiona).
4. Configuración de ejecución **app** → elige un emulador (por ejemplo `SafeFlight_API28`, Android 9 como el MK32) → *Run*.
5. Tests: clic derecho sobre `app/src/test/java` → *Run Tests*, o en terminal:
   ```powershell
   cd android
   .\gradlew.bat testDebugUnitTest lintDebug assembleDebug
   ```
6. Logcat: filtra por `SafeFlight/` (etiquetas `SafeFlight/MAVLink`, `SafeFlight/Vídeo`, `SafeFlight/Control`…).

## 9. Generar el APK para el SIYI MK32

```powershell
python build.py --target android      # tests + lint + APK debug + informe
```

- **APK:** `dist/artifacts/SafeFlight-Android-<VERSION>-debug.apk`. Está firmado con la clave de depuración, id `org.safeflight.android.debug`.
- **Instalación,** cuando se autorice la prueba en el mando: activar la depuración USB en el MK32 y ejecutar `adb install -r <apk>`.
- **Firma de publicación:** no está configurada en el repositorio, a propósito.
- **Compatibilidad:** el MK32 usa Android 9 (API 28), compatible con `minSdk 26`. Está verificado en el emulador API 28, **no en el mando real**. El procedimiento está en `docs/deployment/mk32.md`.

## Correspondencia Kotlin → Java

La versión Kotlin está en `android/legacy-kotlin/` como referencia (no se compila).

| Kotlin/Compose | Java/XML |
|---|---|
| `MainActivity.kt` + `ui/SafeFlightRoot.kt` (NavigationRail Compose) | `MainActivity.java` + `activity_main.xml` + `menu/nav_rail.xml` (Fragments) |
| `ui/FlightScreen.kt` | `ui/FlightFragment.java` + `fragment_flight.xml` |
| `ui/ConnectionScreen.kt` (incl. `ProfileForm`) | `ui/ConnectionFragment.java` (`bindForm`/`readForm`) + `fragment_connection.xml` |
| `ui/MissionsScreen.kt` | `ui/MissionsFragment.java` + `fragment_missions.xml` + `item_mission.xml` |
| `ui/Components.kt` (`StatusChip`, `TelemetryRow`, `fmt`, colores) | `ui/widget/StatusChipView`, `ui/widget/TelemetryRowView`, `ui/UiFormat` |
| `ui/theme/Theme.kt` (`SfColors`) | `res/values/colors.xml` + `themes.xml` (Material 3 Dark) |
| `ui/MainViewModel.kt` (`StateFlow`) | `ui/MainViewModel.java` (`LiveData`, `ThrottledLiveData`) |
| `mavlink/MavlinkClient.kt` (corrutinas) | `mavlink/MavlinkClient.java` (hilo + `ScheduledExecutorService` + `Listener`) |
| `mavlink/MavlinkMessages.kt` (`sealed interface`) | `MavlinkMessage.java` (subclases), `MavlinkHeader`, `MavlinkIds`, `MavConstants`, `MavlinkDecoder` |
| `mavlink/MavlinkParser.kt`, `MavlinkCrc.kt`, `GcsHeartbeatEncoder.kt`, `ArduCopterModes.kt` | mismos nombres `.java` |
| `state/TelemetryState.kt` (`data class` + `TelemetryReducer`) | `TelemetryState.java`, `TelemetryReducer.java`, `StatusMessage.java`, `CommandAckInfo.java` |
| `state/LinkSupervisor.kt` | `LinkStatus.java`, `LinkState.java`, `LinkSupervisor.java` |
| `control/CommandGate.kt` | `CommandGate.java`, `FlightCommand.java`, `CommandDecision.java` |
| `config/ConnectionProfile.kt` (kotlinx.serialization) | `ConnectionProfile.java` + 4 clases de ajustes, `ProfilesDocument`, `ProfileJson` (org.json), `ProfileValidator`, `DefaultProfiles` |
| `config/ProfileRepository.kt` | `ProfileRepository.java`, `KeyValueStore.java` |
| `SafeFlightApplication.kt` (`AppContainer`, `SharedPreferencesStore`) | `SafeFlightApplication.java`, `AppContainer.java`, `SharedPreferencesStore.java` |
| `video/VideoController.kt`, `VideoState.kt` | `VideoController.java`, `VideoState.java`, `VideoStatus.java`, `VideoSupervisor.java` |
| `diagnostics/DiagnosticsLog.kt` | `DiagnosticsLog.java`, `LogEntry.java`, `LogLevel.java` |
| `mission/Missions.kt` | `Mission`, `MissionStatus`, `ExecutionMode`, `MissionSourceKind`, `MissionRepository`, `DemoMissionRepository` |
| Tests `*.kt` (6 clases, 26 tests) | Tests `*.java` (7 clases, 38 tests; se añade `SafetyStructureTest`) |

## Diferencias respecto a la versión Kotlin

**Funcionalidad**
- **Misma funcionalidad y mismos textos:** los scripts del emulador siguen funcionando.
- **Concurrencia:** las corrutinas y `StateFlow` se sustituyen por un hilo, un `ScheduledExecutorService`, interfaces `Listener` y `LiveData`.
- **Ritmo de refresco:** la telemetría se publica a la interfaz como máximo 5 veces por segundo, y los contadores y la edad del fotograma una vez por segundo. Las vistas no se redibujan si el valor no cambia. Reduce CPU con un autopiloto real y permite a `uiautomator` leer la pantalla.
- **Reintentos de vídeo:** si no llega ningún fotograma, la espera entre intentos se duplica a partir del intervalo del perfil, hasta 10 s (`VideoSupervisor.retryDelayMs`). Con el primer fotograma vuelve al intervalo normal. Así una cámara inaccesible no consume CPU sin parar.
- **Selección de perfil:** los chips de perfil saltan de línea, para que los cuatro perfiles se vean en pantallas estrechas.
- **Campos de dirección y URL:** sin sugerencias del teclado.

**Validación de perfiles en JSON**
- **Tipos:** `org.json` admite números escritos como texto ("14550"). Los tipos claramente erróneos se tratan como datos dañados, igual que antes.
- **Valores `null`:** un `null` explícito se interpreta como valor por defecto.

**Sin cambios**
- `applicationId`, `minSdk`, permisos (INTERNET, ACCESS_NETWORK_STATE), orientación `sensorLandscape`, versión desde `VERSION` y firma debug.
