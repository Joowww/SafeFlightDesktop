# ADR-0010: SafeFlight Android en Java con Android Views y XML

**Estado:** propuesto (rama `feature/android-java-migration`). Sustituye a
[ADR-0002](ADR-0002-android-kotlin-compose.md) cuando se apruebe la consolidación.

## Contexto

La primera versión de SafeFlight Android se escribió en Kotlin con Jetpack Compose. El autor
del TFG trabaja en Java y necesita entender, mantener y ampliar la app personalmente durante
el proyecto. Un código que el responsable no domina es un riesgo de mantenimiento y de
seguridad: es más difícil revisar que no se habilitan comandos por error.

## Decisión

- **Lenguaje:** toda la aplicación y sus tests en **Java 17**.
- **Interfaz:** pantallas en **XML** (Android Views) con **ViewBinding** y Material Components 3, organizadas en una `Activity` y tres `Fragment`.
- **Estado de pantalla:** `ViewModel` + `LiveData`.
- **Concurrencia:** un hilo de recepción UDP y un `ScheduledExecutorService` para supervisar el enlace, sustituyendo las corrutinas.
- **JSON de perfiles:** `org.json`, incluido en Android, sustituyendo `kotlinx.serialization`. Se conserva el esquema compartido con Desktop.
- **Se mantienen:** Media3 ExoPlayer (API Java), el parser MAVLink propio, `CommandGate` con comandos deshabilitados en compilación, `applicationId`, `minSdk 26`, permisos, orientación horizontal y la generación del APK con `python build.py --target android`.
- **Gradle:** los scripts siguen en Kotlin DSL (`*.gradle.kts`). Son configuración de compilación, no código de la aplicación.
- **Versión anterior:** el código Kotlin se conserva en `android/legacy-kotlin/` (no compilado) hasta aprobar la consolidación.

## Consecuencias

- **Código:** más largo que en Kotlin (sin `data class` ni `copy`), pero explícito y comprensible para el autor.
- **Ritmo de refresco:** la interfaz se actualiza a un ritmo limitado (telemetría ≤ 5 Hz; contadores y edad de vídeo 1 Hz). Reduce CPU en el MK32 y deja leer la pantalla a `uiautomator` en las pruebas de emulador.
- **Comprobación de seguridad:** `SafetyStructureTest` verifica que no hay código Kotlin en la app, que el único envío de red es el heartbeat de GCS y que no existen mensajes de comando.
- **Guía de trabajo:** [`docs/development/android-java.md`](../development/android-java.md).
