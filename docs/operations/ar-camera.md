# Realidad aumentada (AR): modelo de cámara y calibración

SafeFlight Desktop dibuja HOME y los puntos de misión sobre el vídeo con un modelo de cámara
estenopeica (`models/ArProjection.py`):

- desplazamientos este/norte/arriba desde el dron (longitud corregida con cos(latitud));
- orientación de la cámara = rumbo del vehículo + inclinación del soporte/gimbal;
- distancias focales a partir del **FOV efectivo del vídeo recibido**;
- solo se dibuja con un fix GPS 3D cuyos propios mensajes (GLOBAL_POSITION_INT y GPS_RAW_INT)
  tengan menos de 3 s; si no, el vídeo muestra «AR: SIN POSICION GPS VALIDA».

## Cuándo es aproximada

Sin `ar_camera.json`, o con `"calibrated": false`, la posición es **aproximada**: el vídeo muestra
«AR APROXIMADA: CAMARA SIN CALIBRAR», las distancias llevan «~» y el panel lateral lo indica.
Valores nominales usados: FOV 66×41° (IMX708, óptica estándar, modo de sensor completo 16:9) e
inclinación 0° (cámara horizontal). No incluyen el cabeceo/alabeo del vehículo ni el retardo del
vídeo.

El FOV efectivo cambia con el modo del sensor y el recorte: un modo recortado o la óptica gran
angular (≈102×67°) desplazan los marcadores si no se configuran.

## Configuración

`ar_camera.json` en el directorio de configuración del usuario
(Windows: `%APPDATA%\SafeFlightDesktop\`):

```json
{
  "name": "IMX708 estándar, 1280x720 desde 2304x1296",
  "hfov_deg": 66,
  "vfov_deg": 41,
  "mount_pitch_deg": -15,
  "calibrated": false
}
```

`mount_pitch_deg` negativo = cámara mirando hacia abajo. `"stabilized": true` solo si un gimbal
compensa cabeceo y alabeo; con cámara fija (por defecto) se suma el cabeceo del dron y la AR se
marca como aproximada si falta la actitud o el alabeo supera 5°.

Altitudes: dron, HOME y waypoints usan la altitud relativa a HOME (HOME = 0 m).

Marcar `"calibrated": true` solo después
de comprobar en tierra que un punto conocido (p. ej. HOME a 20–30 m) cae sobre su marcador con el
FOV y la inclinación indicados. Un fichero no válido se ignora y se usan los valores nominales.
