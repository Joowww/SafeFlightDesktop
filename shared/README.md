# Contratos compartidos

SafeFlight Desktop (Python) y SafeFlight Android (Java) no comparten código:
comparten **contratos** verificables por pruebas en ambos lenguajes.

| Ruta | Contenido | Consumidores |
|---|---|---|
| `schemas/connection-profiles.schema.json` | Esquema JSON de los perfiles de conexión | `models/ConnectionProfiles.py`, `config/ConnectionProfile.kt` |
| `examples/connection-profiles.example.json` | Perfiles de fábrica generados por Desktop | `ProfilesTest.sharedExampleIsReadable` (Android) |
| `protocols/mavlink-telemetry-contract.md` | Interpretación del subconjunto MAVLink | ambos clientes |
| `protocols/mavlink-test-vectors.json` | Tramas reales (pymavlink) y valores esperados | `test_mavlink_vectors.py`, `SharedVectorsTest.kt` |

Regenerar los vectores tras modificar el contrato:

```bash
python scripts/generate_mavlink_vectors.py
```

Un cambio en `shared/` dispara en CI tanto el *workflow* de Desktop como el de Android.
