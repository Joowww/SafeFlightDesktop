# Versión Kotlin/Compose (solo referencia, no se compila)

Código de la app Android anterior (Kotlin + Jetpack Compose), movido aquí con `git mv`
durante la migración a Java + XML (rama `feature/android-java-migration`).

- No forma parte de ningún módulo Gradle: `./gradlew` no lo compila ni lo empaqueta.
- Se conserva como referencia hasta aprobar la consolidación de la migración. Después se
  puede eliminar la carpeta entera (`git rm -r android/legacy-kotlin`). Seguirá disponible
  en el historial de Git y en `main`.
- `src/main-java/` contiene la antigua `app/src/main/java` y `src/test-java/` la antigua
  `app/src/test/java`.

La correspondencia entre cada archivo Kotlin y su equivalente Java está en
[`docs/development/android-java.md`](../../docs/development/android-java.md#correspondencia-kotlin--java).
