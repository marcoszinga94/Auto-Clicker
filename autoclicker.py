#!/usr/bin/env python3
"""Auto Clicker Simple para Linux (KDE/Wayland y tambien X11).

- Inyecta clics reales creando un raton virtual via /dev/uinput.
  No necesita root si tu usuario tiene permiso de escritura en /dev/uinput.
- Detecta un atajo global leyendo /dev/input/event* (necesita el grupo `input`).
- Ventana GTK4 con boton Activar/Desactivar y selector de atajo.

Uso normal:      python3 autoclicker.py
Comprobar raton: python3 autoclicker.py --self-test
"""

import argparse
import atexit
import fcntl
import glob
import os
import select
import struct
import sys
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402


# --------------------------------------------------------------------------- #
# Constantes de Linux (linux/input-event-codes.h y linux/uinput.h)
# --------------------------------------------------------------------------- #
EV_SYN, EV_KEY, EV_REL = 0x00, 0x01, 0x02
SYN_REPORT = 0x00
REL_X, REL_Y = 0x00, 0x01
BTN_LEFT, BTN_RIGHT, BTN_MIDDLE = 0x110, 0x111, 0x112
BUS_USB = 0x03

BTN_BY_NAME = {"left": BTN_LEFT, "right": BTN_RIGHT, "middle": BTN_MIDDLE}


def _IOC(direction, typ, nr, size):
    return (direction << 30) | (size << 16) | (ord(typ) << 8) | nr


UI_DEV_CREATE = _IOC(0, "U", 1, 0)      # 0x5501
UI_DEV_DESTROY = _IOC(0, "U", 2, 0)     # 0x5502
UI_DEV_SETUP = _IOC(1, "U", 3, 92)      # 0x405c5503
UI_SET_EVBIT = _IOC(1, "U", 100, 4)     # 0x40045564
UI_SET_KEYBIT = _IOC(1, "U", 101, 4)    # 0x40045565
UI_SET_RELBIT = _IOC(1, "U", 102, 4)    # 0x40045566


def EVIOCGNAME(length):
    return _IOC(2, "E", 0x06, length)


def EVIOCGBIT(event_type, length):
    return _IOC(2, "E", 0x20 + event_type, length)


INPUT_EVENT = struct.Struct("llHHi")     # timeval + type + code + value (24 bytes)
UINPUT_SETUP = struct.Struct("HHHH80sI")  # input_id + name[80] + ff_effects_max


# Nombres legibles para las teclas mas comunes.
KEY_NAMES = {
    1: "Esc", 2: "1", 3: "2", 4: "3", 5: "4", 6: "5", 7: "6", 8: "7",
    9: "8", 10: "9", 11: "0", 12: "-", 13: "=", 14: "Retroceso", 15: "Tab",
    16: "Q", 17: "W", 18: "E", 19: "R", 20: "T", 21: "Y", 22: "U", 23: "I",
    24: "O", 25: "P", 26: "[", 27: "]", 28: "Enter", 29: "Ctrl izq",
    30: "A", 31: "S", 32: "D", 33: "F", 34: "G", 35: "H", 36: "J", 37: "K",
    38: "L", 39: ";", 40: "'", 41: "`", 42: "Shift izq", 43: "\\",
    44: "Z", 45: "X", 46: "C", 47: "V", 48: "B", 49: "N", 50: "M",
    51: ",", 52: ".", 53: "/", 54: "Shift der", 55: "KP *", 56: "Alt izq",
    57: "Espacio", 58: "Bloq Mayus", 59: "F1", 60: "F2", 61: "F3", 62: "F4",
    63: "F5", 64: "F6", 65: "F7", 66: "F8", 67: "F9", 68: "F10",
    69: "Bloq Num", 70: "Bloq Despl", 87: "F11", 88: "F12",
    96: "KP Enter", 97: "Ctrl der", 98: "KP /", 99: "Impr Pant",
    100: "Alt der", 102: "Inicio", 103: "Arriba", 104: "Av Pag",
    105: "Izquierda", 106: "Derecha", 107: "Fin", 108: "Abajo",
    109: "Re Pag", 110: "Insert", 111: "Supr", 119: "Pausa",
    125: "Meta izq", 126: "Meta der", 127: "Menu",
}
NAME_TO_CODE = {name.lower(): code for code, name in KEY_NAMES.items()}
NAME_TO_CODE.update({"space": 57, "enter": 28, "escape": 1, "scrolllock": 70})


def key_name(code):
    return KEY_NAMES.get(code, f"Tecla {code}")


# --------------------------------------------------------------------------- #
# Raton virtual via /dev/uinput
# --------------------------------------------------------------------------- #
class UInputError(RuntimeError):
    pass


class VirtualMouse:
    """Crea un raton virtual y emite pulsaciones en la posicion actual."""

    def __init__(self, name="Auto-Clicker Virtual Mouse"):
        self.fd = None
        try:
            self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        except OSError as error:
            raise UInputError(
                "No se puede abrir /dev/uinput. Comprueba que tu usuario tiene "
                f"permiso (ACL, grupo o regla udev). Detalle: {error}"
            ) from error
        try:
            self._setup(name)
        except Exception:
            os.close(self.fd)
            self.fd = None
            raise

    def _setup(self, name):
        ioctl = lambda req, arg=0: fcntl.ioctl(self.fd, req, arg)  # noqa: E731
        ioctl(UI_SET_EVBIT, EV_KEY)
        ioctl(UI_SET_EVBIT, EV_REL)
        ioctl(UI_SET_EVBIT, EV_SYN)
        for button in (BTN_LEFT, BTN_RIGHT, BTN_MIDDLE):
            ioctl(UI_SET_KEYBIT, button)
        for rel in (REL_X, REL_Y):
            ioctl(UI_SET_RELBIT, rel)
        setup = UINPUT_SETUP.pack(BUS_USB, 0x1234, 0x5678, 1, name.encode()[:79], 0)
        ioctl(UI_DEV_SETUP, setup)
        ioctl(UI_DEV_CREATE)
        time.sleep(0.2)  # deja que el kernel cree el nodo /dev/input/event*

    def _emit(self, event_type, code, value):
        os.write(self.fd, INPUT_EVENT.pack(0, 0, event_type, code, value))

    def click(self, button_code):
        self._emit(EV_KEY, button_code, 1)
        self._emit(EV_SYN, SYN_REPORT, 0)
        time.sleep(0.012)
        self._emit(EV_KEY, button_code, 0)
        self._emit(EV_SYN, SYN_REPORT, 0)

    def close(self):
        if self.fd is None:
            return
        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        except OSError:
            pass
        try:
            os.close(self.fd)
        except OSError:
            pass
        self.fd = None


# --------------------------------------------------------------------------- #
# Atajo global: lee los teclados desde /dev/input
# --------------------------------------------------------------------------- #
class HotkeyListener(threading.Thread):
    def __init__(self, get_hotkey, is_capturing, callback):
        super().__init__(daemon=True, name="hotkey-listener")
        self._get_hotkey = get_hotkey
        self._is_capturing = is_capturing
        self._callback = callback
        self._stop = threading.Event()
        self._fds = {}     # fd -> path
        self._paths = {}   # path -> fd
        self._down = set()

    def stop(self):
        self._stop.set()

    @staticmethod
    def _is_keyboard(fd):
        buf = fcntl.ioctl(fd, EVIOCGBIT(EV_KEY, 96), bytes(96))
        has = lambda code: buf[code // 8] & (1 << (code % 8))  # noqa: E731
        return bool(has(1) or has(28) or has(30) or has(57))  # Esc/Enter/A/Espacio

    def _rescan(self):
        current = set(glob.glob("/dev/input/event*"))
        for fd, path in list(self._fds.items()):
            if path not in current:
                try:
                    os.close(fd)
                except OSError:
                    pass
                del self._fds[fd]
                self._paths.pop(path, None)
        for path in sorted(current):
            if path in self._paths:
                continue
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                continue
            try:
                if self._is_keyboard(fd):
                    self._fds[fd] = path
                    self._paths[path] = fd
                else:
                    os.close(fd)
            except OSError:
                os.close(fd)

    def _on_event(self, code, value):
        if value == 1:
            if code in self._down:
                return
            self._down.add(code)
            if self._is_capturing() or code == self._get_hotkey():
                self._callback(code)
        elif value == 0:
            self._down.discard(code)

    def run(self):
        last_scan = 0.0
        while not self._stop.is_set():
            now = time.monotonic()
            if now - last_scan > 3.0:
                self._rescan()
                last_scan = now
            fds = list(self._fds.keys())
            if not fds:
                self._stop.wait(0.5)
                continue
            try:
                ready, _, _ = select.select(fds, [], [], 1.0)
            except OSError:
                self._rescan()
                continue
            for fd in ready:
                try:
                    data = os.read(fd, INPUT_EVENT.size * 64)
                except OSError:
                    path = self._fds.pop(fd, None)
                    if path:
                        self._paths.pop(path, None)
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                    continue
                for offset in range(0, len(data) - INPUT_EVENT.size + 1, INPUT_EVENT.size):
                    _, _, event_type, code, value = INPUT_EVENT.unpack_from(data, offset)
                    if event_type == EV_KEY:
                        self._on_event(code, value)


# --------------------------------------------------------------------------- #
# Aplicacion GTK4
# --------------------------------------------------------------------------- #
class ClickerApp(Gtk.Application):
    def __init__(self, interval_ms=100, button="left", hotkey="F8", smoke=False):
        super().__init__(
            application_id="io.github.zinike.autoclickersimple",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.mouse = None
        self.window = None
        self.listener = None
        self.worker = None

        self._active = threading.Event()
        self._shutdown = threading.Event()

        self.interval_ms = max(10, int(interval_ms))
        self.button_name = button
        self.hotkey_code = NAME_TO_CODE.get(hotkey.lower(), 66)
        self.click_type = "simple"

        self._capturing = False
        self.click_count = 0
        self._last_ui = 0.0
        self._smoke = smoke
        self._closed = False

        self._build_engine()

    # --------------------------- motor de clics --------------------------- #
    def _build_engine(self):
        try:
            self.mouse = VirtualMouse()
        except UInputError as error:
            self.mouse_error = str(error)
            return
        self.mouse_error = None
        self.worker = threading.Thread(target=self._click_worker, daemon=True, name="clicker")
        self.worker.start()
        self.listener = HotkeyListener(
            get_hotkey=lambda: self.hotkey_code,
            is_capturing=lambda: self._capturing,
            callback=lambda code: GLib.idle_add(self._on_key, code),
        )
        self.listener.start()
        atexit.register(self._shutdown_engine)

    def _click_worker(self):
        while not self._shutdown.is_set():
            self._active.wait()
            if self._shutdown.is_set():
                break
            while self._active.is_set() and not self._shutdown.is_set():
                try:
                    button = BTN_BY_NAME[self.button_name]
                    self.mouse.click(button)
                    if self.click_type == "doble":
                        self.mouse.click(button)
                    self.click_count += 2 if self.click_type == "doble" else 1
                except Exception as error:  # p. ej. /dev/uinput cerrado
                    GLib.idle_add(self._on_worker_error, str(error))
                    self._active.clear()
                    break
                self._maybe_update_count()
                deadline = time.monotonic() + self.interval_ms / 1000.0
                while (
                    self._active.is_set()
                    and not self._shutdown.is_set()
                    and time.monotonic() < deadline
                ):
                    time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
            GLib.idle_add(self._refresh_count, True)

    def _maybe_update_count(self):
        now = time.monotonic()
        if now - self._last_ui >= 0.1:
            self._last_ui = now
            GLib.idle_add(self._refresh_count, False)

    def _refresh_count(self, force):
        if self.window and self.count_label is not None:
            self.count_label.set_text(f"Clics realizados: {self.click_count}")
        return False

    def _on_worker_error(self, message):
        self._active.clear()
        if not self.window:
            return False
        self._refresh_toggle()
        self.status_label.set_text(f"Error: {message}")
        return False

    # ------------------------------ atajo ------------------------------ #
    def _on_key(self, code):
        if not self.window:
            return False
        if self._capturing:
            self._capturing = False
            self.hotkey_code = code
            self.capture_button.set_label("Cambiar")
            self.hotkey_label.set_text(f"Atajo: {key_name(code)}")
            self.status_label.set_text(f"Atajo global cambiado a {key_name(code)}.")
            return False
        if code == self.hotkey_code:
            self._request_toggle()
        return False

    def _start_capture(self, _button):
        if not self.mouse:
            return
        self._capturing = True
        self.capture_button.set_label("Pulsa una tecla...")
        self.status_label.set_text("Pulsa la tecla que quieras usar como atajo.")

    # ----------------------------- control ----------------------------- #
    def _request_toggle(self):
        if not self.mouse:
            return
        if self._active.is_set():
            self._active.clear()
        else:
            self._active.set()
        GLib.idle_add(self._refresh_toggle)

    def _refresh_toggle(self):
        if not self.window:
            return False
        active = self._active.is_set()
        if active:
            self.toggle_button.set_label("Desactivar")
            if "suggested-action" in self.toggle_button.get_css_classes():
                self.toggle_button.remove_css_class("suggested-action")
            self.toggle_button.add_css_class("destructive-action")
            self.status_label.set_text("Activo: haciendo clics.")
        else:
            self.toggle_button.set_label("Activar")
            self.toggle_button.remove_css_class("destructive-action")
            self.toggle_button.add_css_class("suggested-action")
            self.status_label.set_text("Detenido.")
        return False

    # ------------------------------- UI ------------------------------- #
    def do_activate(self):
        if self.window is not None:
            self.window.present()
            return
        self._build_ui()
        self.window.present()
        if self._smoke:
            GLib.timeout_add(1500, self._quit)

    def _build_ui(self):
        self.window = Gtk.ApplicationWindow(application=self, title="Auto Clicker Simple")
        self.window.set_default_size(380, -1)
        self.window.connect("close-request", self._on_close)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(16)
        self.window.set_child(box)

        title = Gtk.Label(label="Auto Clicker Simple")
        title.add_css_class("title-2")
        box.append(title)

        self.toggle_button = Gtk.Button(label="Activar")
        self.toggle_button.add_css_class("suggested-action")
        self.toggle_button.add_css_class("pill")
        self.toggle_button.connect("clicked", lambda *_: self._request_toggle())
        box.append(self.toggle_button)

        grid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.append(grid)

        grid.append(self._row("Intervalo (ms)", self._interval_spin()))
        grid.append(self._row("Boton", self._button_dropdown()))
        grid.append(self._row("Tipo", self._click_dropdown()))

        hotkey_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.hotkey_label = Gtk.Label(label=f"Atajo: {key_name(self.hotkey_code)}")
        self.hotkey_label.set_xalign(0)
        self.hotkey_label.set_hexpand(True)
        hotkey_row.append(self.hotkey_label)
        self.capture_button = Gtk.Button(label="Cambiar")
        self.capture_button.connect("clicked", self._start_capture)
        hotkey_row.append(self.capture_button)
        grid.append(hotkey_row)

        self.status_label = Gtk.Label(label="Listo.")
        self.status_label.set_xalign(0)
        self.status_label.set_wrap(True)
        box.append(self.status_label)

        self.count_label = Gtk.Label(label="Clics realizados: 0")
        self.count_label.set_xalign(0)
        box.append(self.count_label)

        if not self.mouse:
            self.toggle_button.set_sensitive(False)
            self.status_label.set_text(f"Error: {self.mouse_error}")
        else:
            self.status_label.set_text(
                f"Listo. Atajo global: {key_name(self.hotkey_code)} (funciona sin foco)."
            )

    @staticmethod
    def _row(text, widget):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        label = Gtk.Label(label=text)
        label.set_xalign(0)
        label.set_hexpand(True)
        row.append(label)
        row.append(widget)
        return row

    def _interval_spin(self):
        spin = Gtk.SpinButton.new_with_range(10, 600_000, 10)
        spin.set_value(self.interval_ms)
        spin.connect("value-changed", self._on_interval)
        return spin

    def _button_dropdown(self):
        names = ["Izquierdo", "Derecho", "Medio"]
        values = ["left", "right", "middle"]
        self._button_values = values
        dropdown = Gtk.DropDown.new_from_strings(names)
        dropdown.set_selected(values.index(self.button_name))
        dropdown.connect("notify::selected", self._on_button)
        return dropdown

    def _click_dropdown(self):
        self._click_values = ["simple", "doble"]
        dropdown = Gtk.DropDown.new_from_strings(["Simple", "Doble"])
        dropdown.set_selected(0)
        dropdown.connect("notify::selected", self._on_click_type)
        return dropdown

    def _on_interval(self, spin):
        self.interval_ms = int(spin.get_value())
        return False

    def _on_button(self, dropdown, _param):
        self.button_name = self._button_values[dropdown.get_selected()]
        return False

    def _on_click_type(self, dropdown, _param):
        self.click_type = self._click_values[dropdown.get_selected()]
        return False

    # ----------------------------- cierre ----------------------------- #
    def _quit(self):
        self.quit()
        return False

    def _on_close(self, *_):
        self._shutdown_engine()
        self.window = None
        return False

    def _shutdown_engine(self):
        if self._closed:
            return
        self._closed = True
        self._shutdown.set()
        self._active.clear()
        if self.listener:
            self.listener.stop()
        if self.worker:
            self.worker.join(timeout=1.0)
        if self.mouse:
            self.mouse.close()
            self.mouse = None


# --------------------------------------------------------------------------- #
# Prueba del raton virtual
# --------------------------------------------------------------------------- #
def run_self_test():
    before = set(glob.glob("/dev/input/event*"))
    try:
        mouse = VirtualMouse()
    except UInputError as error:
        print(f"FALLO: {error}")
        return 1
    time.sleep(0.4)
    after = set(glob.glob("/dev/input/event*"))
    new = sorted(after - before)
    print("Raton virtual creado correctamente.")
    print(f"Nuevos nodos de entrada: {new if new else '(ninguno detectado)'}")
    mouse.close()
    time.sleep(0.2)
    print("Raton virtual destruido. Todo listo.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Auto Clicker Simple (Linux)")
    parser.add_argument("--interval", type=int, default=100, help="intervalo en ms (defecto 100)")
    parser.add_argument("--button", choices=["left", "right", "middle"], default="left")
    parser.add_argument("--hotkey", default="F8", help="tecla de atajo, p. ej. F8, Pausa, Bloq Despl")
    parser.add_argument("--self-test", action="store_true", help="crea y destruye el raton virtual")
    parser.add_argument("--smoke-test", action="store_true", help="abre la ventana y sale en 1,5 s")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    app = ClickerApp(
        interval_ms=args.interval,
        button=args.button,
        hotkey=args.hotkey,
        smoke=args.smoke_test,
    )
    return app.run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
