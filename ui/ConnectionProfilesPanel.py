"""Modal panel to create, edit, duplicate, restore and delete profiles.

The panel only edits :class:`models.ConnectionProfiles.ProfileStore`; the
application decides how a saved profile is applied (video changes are
applied immediately, MAVLink changes on the next connection).
"""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from models.ConnectionProfiles import (
    ConnectionProfile,
    Diagnostics,
    MavlinkEndpoint,
    ProfileStore,
    ProfileValidationError,
    Timeouts,
    VideoSource,
)

_FIELD_BG = "#1b1b1b"

_KIND_LABELS = {
    "siyi_local": "SIYI LOCAL",
    "cellular_vpn": "5G / VPN",
    "sitl": "SITL / SIMULACIÓN",
    "custom": "Personalizado",
}
_TRANSPORT_LABELS = {
    "udp_listen": "UDP escucha (udpin)",
    "udp_connect": "UDP hacia remoto (udpout)",
    "tcp_client": "TCP cliente",
    "serial": "Puerto serie",
    "custom": "Cadena personalizada",
}
_VIDEO_LABELS = {
    "rtp_udp": "RTP/UDP (H.264, SDP local)",
    "rtsp": "RTSP (servidor remoto)",
    "none": "Sin vídeo",
}


def _text_field(label: str, value="", width: Optional[int] = None, hint: str = "") -> ft.TextField:
    return ft.TextField(
        label=label,
        value=str(value),
        hint_text=hint or None,
        dense=True,
        width=width,
        border_radius=8,
        bgcolor=_FIELD_BG,
        color="white",
    )


def _dropdown(label: str, labels: dict, value: str, on_select=None, width: Optional[int] = None) -> ft.Dropdown:
    return ft.Dropdown(
        label=label,
        value=value,
        dense=True,
        width=width,
        options=[ft.DropdownOption(key=k, text=v) for k, v in labels.items()],
        on_select=on_select,
    )


class ConnectionProfilesPanel:
    """Full-window overlay editor bound to a :class:`ProfileStore`."""

    def __init__(
        self,
        store: ProfileStore,
        on_saved: Callable[[ConnectionProfile], None],
        on_message: Callable[[str, bool], None],
        on_update: Callable[[], None],
    ):
        self.store = store
        self._on_saved = on_saved
        self._on_message = on_message
        self._on_update = on_update
        self._editing_id: Optional[str] = None
        self._build()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        self.profile_selector = _dropdown("Perfil", {}, "", on_select=self._on_selector_change, width=300)
        self.name_field = _text_field("Nombre", width=300)
        self.kind_dropdown = _dropdown("Tipo", _KIND_LABELS, "custom", width=220)
        self.notes_text = ft.Text("", size=11, color="#f0b429", selectable=True)

        self.transport_dropdown = _dropdown(
            "Transporte MAVLink", _TRANSPORT_LABELS, "udp_listen",
            on_select=lambda e: self._refresh_visibility(), width=300,
        )
        self.local_host_field = _text_field("Dirección local de escucha", "0.0.0.0", 220)
        self.local_port_field = _text_field("Puerto local", "14560", 120)
        self.remote_host_field = _text_field("Dirección remota", "", 220, hint="192.168.x.x")
        self.remote_port_field = _text_field("Puerto remoto", "14550", 120)
        self.serial_device_field = _text_field("Dispositivo serie", "", 220, hint="COM5 / /dev/ttyACM0")
        self.baud_field = _text_field("Baudios", "57600", 120)
        self.custom_conn_field = _text_field("Cadena de conexión", "", 360, hint="udpin:0.0.0.0:14560")
        self.conn_preview = ft.Text("", size=12, color="#3b8ed0", selectable=True)

        self.video_mode_dropdown = _dropdown(
            "Fuente de vídeo", _VIDEO_LABELS, "rtp_udp",
            on_select=lambda e: self._refresh_visibility(), width=300,
        )
        self.rtp_port_field = _text_field("Puerto RTP local (UDP)", "5004", 180)
        self.rtsp_url_field = _text_field("URL RTSP", "", 420, hint="rtsp://IP:8554/ruta")
        self.rtsp_transport_dropdown = _dropdown("Transporte RTSP", {"tcp": "TCP", "udp": "UDP"}, "tcp", width=140)

        self.connect_timeout_field = _text_field("Timeout conexión (s)", "90", 150)
        self.heartbeat_timeout_field = _text_field("Espera 1er heartbeat (s)", "30", 170)
        self.telemetry_stale_field = _text_field("Telemetría obsoleta (s)", "3", 160)
        self.video_stale_field = _text_field("Vídeo obsoleto (s)", "2", 140)
        self.video_reconnect_field = _text_field("Reintento vídeo (s)", "1", 140)
        self.verbose_switch = ft.Switch(label="Registro detallado", value=False)

        self.error_text = ft.Text("", color="#fb7185", size=12, selectable=True)

        self.btn_new = ft.TextButton("Nuevo", on_click=self._new_profile)
        self.btn_duplicate = ft.TextButton("Duplicar", on_click=self._duplicate_profile)
        self.btn_restore = ft.TextButton("Restaurar valores de fábrica", on_click=self._restore_profile)
        self.btn_delete = ft.TextButton("Eliminar", on_click=self._delete_profile)
        self.btn_cancel = ft.TextButton("Cerrar", on_click=lambda e: self.close())
        self.btn_save = ft.Button("Guardar y seleccionar", bgcolor="#28a745", color="white", on_click=self._save)

        def section(title: str) -> ft.Text:
            return ft.Text(title, size=12, weight=ft.FontWeight.BOLD, color="gray")

        self.local_row = ft.Row([self.local_host_field, self.local_port_field], wrap=True)
        self.remote_row = ft.Row([self.remote_host_field, self.remote_port_field], wrap=True)
        self.serial_row = ft.Row([self.serial_device_field, self.baud_field], wrap=True)
        self.custom_row = ft.Row([self.custom_conn_field], wrap=True)
        self.rtp_row = ft.Row([self.rtp_port_field], wrap=True)
        self.rtsp_row = ft.Row([self.rtsp_url_field, self.rtsp_transport_dropdown], wrap=True)

        body = ft.Column(
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            spacing=10,
            controls=[
                ft.Text("Perfiles de conexión", size=20, weight=ft.FontWeight.BOLD, color="white"),
                ft.Row([self.profile_selector, self.btn_new, self.btn_duplicate], wrap=True),
                ft.Row([self.name_field, self.kind_dropdown], wrap=True),
                self.notes_text,
                ft.Divider(color="#333333"),
                section("TELEMETRÍA (MAVLink)"),
                self.transport_dropdown,
                self.local_row,
                self.remote_row,
                self.serial_row,
                self.custom_row,
                self.conn_preview,
                ft.Divider(color="#333333"),
                section("VÍDEO"),
                self.video_mode_dropdown,
                self.rtp_row,
                self.rtsp_row,
                ft.Divider(color="#333333"),
                section("SUPERVISIÓN Y DIAGNÓSTICO"),
                ft.Row(
                    [
                        self.connect_timeout_field,
                        self.heartbeat_timeout_field,
                        self.telemetry_stale_field,
                        self.video_stale_field,
                        self.video_reconnect_field,
                    ],
                    wrap=True,
                ),
                self.verbose_switch,
                ft.Text(
                    "La pérdida de enlace que activa el aterrizaje de emergencia de la "
                    "aplicación sigue fijada en 15 s y no se modifica desde los perfiles.",
                    size=11,
                    color="#aaaaaa",
                ),
            ],
        )
        # Validation errors and actions stay visible below the scrolling form,
        # also in the default 1366x768 window.
        footer = ft.Column(
            spacing=6,
            controls=[
                self.error_text,
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    wrap=True,
                    controls=[self.btn_restore, self.btn_delete, self.btn_cancel, self.btn_save],
                ),
            ],
        )

        self.container = ft.Container(
            visible=False,
            expand=True,
            bgcolor="#000000b0",
            alignment=ft.Alignment(0, 0),
            content=ft.Container(
                width=760,
                padding=20,
                border_radius=12,
                bgcolor="#202020",
                border=ft.Border.all(1, "#444444"),
                content=ft.Column(spacing=8, controls=[body, ft.Divider(color="#333333"), footer]),
            ),
        )

    # ------------------------------------------------------------------
    def open(self, profile_id: Optional[str] = None) -> None:
        self._load_into_form(self.store.get(profile_id or self.store.active_profile_id) or self.store.active)
        self.container.visible = True
        self._on_update()

    def close(self) -> None:
        # Discard unsaved new/duplicated profiles by reloading the file.
        self.store.load()
        self.container.visible = False
        self._on_update()

    @property
    def is_open(self) -> bool:
        return bool(self.container.visible)

    # ------------------------------------------------------------------
    def _refresh_selector(self) -> None:
        self.profile_selector.options = [
            ft.DropdownOption(key=p.id, text=p.name) for p in self.store.profiles
        ]
        self.profile_selector.value = self._editing_id

    def _load_into_form(self, profile: ConnectionProfile) -> None:
        self._editing_id = profile.id
        self._refresh_selector()
        m, v, t = profile.mavlink, profile.video, profile.timeouts
        self.name_field.value = profile.name
        self.kind_dropdown.value = profile.kind
        self.notes_text.value = profile.notes
        self.transport_dropdown.value = m.transport
        self.local_host_field.value = m.local_host
        self.local_port_field.value = str(m.local_port)
        self.remote_host_field.value = m.remote_host
        self.remote_port_field.value = str(m.remote_port)
        self.serial_device_field.value = m.serial_device
        self.baud_field.value = str(m.baud_rate)
        self.custom_conn_field.value = m.connection_string
        self.video_mode_dropdown.value = v.mode
        self.rtp_port_field.value = str(v.rtp_udp_port)
        self.rtsp_url_field.value = v.rtsp_url
        self.rtsp_transport_dropdown.value = v.rtsp_transport
        self.connect_timeout_field.value = f"{t.connect_timeout_s:g}"
        self.heartbeat_timeout_field.value = f"{t.heartbeat_timeout_s:g}"
        self.telemetry_stale_field.value = f"{t.telemetry_stale_s:g}"
        self.video_stale_field.value = f"{t.video_stale_s:g}"
        self.video_reconnect_field.value = f"{t.video_reconnect_interval_s:g}"
        self.verbose_switch.value = profile.diagnostics.verbose_logging
        self.btn_delete.disabled = profile.builtin
        self.btn_restore.disabled = not profile.builtin
        self.error_text.value = ""
        self._refresh_visibility()

    def _refresh_visibility(self) -> None:
        transport = self.transport_dropdown.value
        self.local_row.visible = transport == "udp_listen"
        self.remote_row.visible = transport in ("udp_connect", "tcp_client")
        self.serial_row.visible = transport == "serial"
        self.custom_row.visible = transport == "custom"
        mode = self.video_mode_dropdown.value
        self.rtp_row.visible = mode == "rtp_udp"
        self.rtsp_row.visible = mode == "rtsp"
        try:
            self.conn_preview.value = "MAVLink: " + self._form_to_profile().mavlink_connection_string()
        except Exception:
            self.conn_preview.value = "MAVLink: (valores incompletos)"
        self._on_update()

    def _form_to_profile(self) -> ConnectionProfile:
        existing = self.store.get(self._editing_id or "")
        profile = ConnectionProfile(
            id=self._editing_id or self.store.new_profile_id(),
            name=str(self.name_field.value or ""),
            kind=str(self.kind_dropdown.value or "custom"),
            builtin=bool(existing.builtin) if existing else False,
            notes=existing.notes if existing else "",
            mavlink=MavlinkEndpoint(
                transport=str(self.transport_dropdown.value or ""),
                local_host=self.local_host_field.value,
                local_port=self.local_port_field.value,
                remote_host=self.remote_host_field.value,
                remote_port=self.remote_port_field.value,
                serial_device=self.serial_device_field.value,
                baud_rate=self.baud_field.value,
                connection_string=self.custom_conn_field.value,
            ),
            video=VideoSource(
                mode=str(self.video_mode_dropdown.value or ""),
                rtp_udp_port=self.rtp_port_field.value,
                rtsp_url=self.rtsp_url_field.value,
                rtsp_transport=str(self.rtsp_transport_dropdown.value or "tcp"),
            ),
            timeouts=Timeouts(
                connect_timeout_s=self.connect_timeout_field.value,
                heartbeat_timeout_s=self.heartbeat_timeout_field.value,
                telemetry_stale_s=self.telemetry_stale_field.value,
                video_stale_s=self.video_stale_field.value,
                video_reconnect_interval_s=self.video_reconnect_field.value,
            ),
            diagnostics=Diagnostics(verbose_logging=bool(self.verbose_switch.value)),
        )
        profile.normalise()
        return profile

    # ------------------------------------------------------------------
    def _on_selector_change(self, e) -> None:
        profile = self.store.get(str(self.profile_selector.value or ""))
        if profile is not None:
            self._load_into_form(profile)

    def _save(self, e=None) -> None:
        try:
            profile = self.store.upsert(self._form_to_profile())
            self.store.select(profile.id)
            self.store.save()
        except ProfileValidationError as exc:
            self.error_text.value = "Revisa los campos:\n• " + "\n• ".join(exc.errors)
            self._on_update()
            return
        except OSError as exc:
            self.error_text.value = f"No se pudo guardar: {exc}"
            self._on_update()
            return
        self.container.visible = False
        self._on_saved(profile)

    def _new_profile(self, e=None) -> None:
        profile = ConnectionProfile(id=self.store.new_profile_id(), name="Nuevo perfil", kind="custom")
        self.store.profiles.append(profile)
        self._load_into_form(profile)
        self._on_message("Perfil creado. Ajusta los valores y pulsa Guardar.", False)

    def _duplicate_profile(self, e=None) -> None:
        if not self._editing_id:
            return
        clone = self.store.duplicate(self._editing_id)
        self._load_into_form(clone)
        self._on_message(f"Duplicado como '{clone.name}'. Pulsa Guardar para conservarlo.", False)

    def _restore_profile(self, e=None) -> None:
        if not self._editing_id:
            return
        try:
            profile = self.store.restore_builtin(self._editing_id)
            self.store.save()
        except (ValueError, OSError) as exc:
            self._on_message(str(exc), True)
            return
        self._load_into_form(profile)
        self._on_message(f"'{profile.name}' restaurado a valores de fábrica.", False)
        if self.store.active_profile_id == profile.id:
            self._on_saved(profile)

    def _delete_profile(self, e=None) -> None:
        if not self._editing_id:
            return
        try:
            self.store.delete(self._editing_id)
            self.store.save()
        except (KeyError, ValueError, OSError) as exc:
            self._on_message(str(exc), True)
            return
        self._load_into_form(self.store.active)
        self._on_saved(self.store.active)
