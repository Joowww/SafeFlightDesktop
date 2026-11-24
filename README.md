# SafeFlight

Estaciones de control para la supervisión de vehículos autónomos (ArduPilot) del
TFG sobre planificación y ejecución de misiones con IA agéntica.

| Aplicación | Plataformas | Tecnología | Ubicación |
|---|---|---|---|
| **SafeFlight Desktop** | Windows · macOS · Linux | Python, Flet, DroneKit, PyAV | raíz (`App_flet.py`, `models/`, `ui/`) |
| **SafeFlight Android** | Android 8+ · objetivo SIYI MK32 | Java, Android Views (XML), Media3 | [`android/`](android/) |

Ambas aplicaciones son independientes y comparten contratos verificados por pruebas
en [`shared/`](shared/): perfiles de conexión, interpretación de MAVLink y vectores de prueba.

## Inicio rápido

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt -r requirements-build.txt

python App_flet.py                 # ejecutar Desktop desde el código
python build.py                    # pruebas + paquete Desktop del SO actual
python build.py --target android   # pruebas + lint + APK de depuración
python build.py --help
```

Los artefactos y sus informes (pruebas, *smoke test*, SHA-256) quedan en `dist/artifacts/`.

## Configuración sin recompilar

Las direcciones IP, puertos y fuentes de vídeo se gestionan con **perfiles de
conexión** editables desde la aplicación: *SIYI LOCAL*, *5G / VPN*, *SITL / SIMULACIÓN*
y perfiles propios. Ver [ADR-0005](docs/adr/ADR-0005-connection-profiles.md).

## Seguridad

* SafeFlight Android **no envía comandos de vuelo**: los controles están bloqueados por
  diseño hasta completar validación SITL, análisis de seguridad y autorización
  ([ADR-0008](docs/adr/ADR-0008-flight-commands-disabled.md)).
* El radiocontrol del mando es independiente de SafeFlight.
* Las funciones de despegue/aterrizaje heredadas de Desktop no están validadas en vuelo físico.

## Documentación

| Tema | Documento |
|---|---|
| Arquitectura global y estado de cada componente | [docs/architecture/overview.md](docs/architecture/overview.md) |
| Desktop · Android · Comunicaciones | [desktop](docs/architecture/desktop.md) · [android](docs/architecture/android.md) · [communications](docs/architecture/communications.md) |
| Compilación, CI y despliegue | [docs/architecture/build-and-deployment.md](docs/architecture/build-and-deployment.md) |
| Integración con el sistema multiagente (propuesta) | [docs/architecture/integration-points.md](docs/architecture/integration-points.md) |
| Decisiones arquitectónicas | [docs/adr/](docs/adr/) |
| Desarrollo Desktop · macOS · Android | [desktop](docs/development/desktop.md) · [macos](docs/development/macos.md) · [android](docs/development/android.md) |
| Despliegue en SIYI MK32 | [docs/deployment/mk32.md](docs/deployment/mk32.md) |
| Validación y evidencias | [matriz](docs/evaluation/validation-matrix.md) · [registro](docs/evaluation/test-log.md) |

## Estado (v0.3.0)

Desktop compilado y verificado en Windows; macOS y Linux se compilan en GitHub
Actions y están pendientes de validación en equipos reales. Android verificado en
emulador con telemetría y vídeo de prueba; validación en el SIYI MK32 pendiente de
hardware. Detalle en la [matriz de validación](docs/evaluation/validation-matrix.md).
