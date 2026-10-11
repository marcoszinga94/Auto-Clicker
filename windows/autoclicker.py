#!/usr/bin/env python3
"""Auto Clicker Simple para Windows.

- Inyecta clics reales en la posicion actual del cursor mediante SendInput.
- Atajo global para Activar/Desactivar (depende del paquete `keyboard`).
- Interfaz grafica con Tkinter.

Uso normal:  python autoclicker.py
Compilar:    pyinstaller --onefile --windowed --name AutoClicker autoclicker.py
"""

import argparse
import ctypes
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

# --------------------------------------------------------------------------- #
# SendInput (Windows)
# --------------------------------------------------------------------------- #
INPUT_MOUSE = 0

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040

BD_FLAGS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}

LONG = ctypes.c_long
ULONG_PTR = ctypes.POINTER(ctypes.c_ulong)


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", LONG),
        ("dy", LONG),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    )


class _INPUTUNION(ctypes.Union):
    _fields_ = (("mi", MOUSEINPUT),)


class INPUT(ctypes.Structure):
    _anonymous_ = ("i",)
    _fields_ = (("type", ctypes.c_ulong), ("i", _INPUTUNION))


def _send(flags):
    """Envia un evento de raton en la posicion actual del cursor."""
    inp = INPUT(type=INPUT_MOUSE)
    inp.i.mi.dwFlags = flags
    sent = ctypes.windll.user32.SendInput(
        1, ctypes.byref(inp), ctypes.sizeof(INPUT)
    )
    return sent == 1


def click(button):
    """Un clic (presionar + soltar) del boton indicado."""
    down, up = BD_FLAGS[button]
    _send(down)
    time.sleep(0.012)
    _send(up)


def click_double(button):
    click(button)
    time.sleep(0.012)
    click(button)


def self_test():
    try:
        ctypes.windll.user32.SendInput
    except AttributeError:
        return 1
    print("SendInput disponible. Auto Clicker Simple (Windows) listo.")
    return 0


# --------------------------------------------------------------------------- #
# Interfaz
# --------------------------------------------------------------------------- #
class ClickerApp:
    TITLE = "Auto Clicker Simple"

    def __init__(self, interval_ms=100, button="left", hotkey="f8"):
        self.interval_ms = max(10, int(interval_ms))
        self.button = button
        self.hotkey = hotkey.lower()
        self.click_count = 0
        self.active = False
        self._stop = threading.Event()

        self.root = tk.Tk()
        self.root.title(self.TITLE)
        self.root.resizable(False, False)

        try:
            import keyboard  # noqa: WPS433
        except ImportError:
            messagebox.showerror(
                self.TITLE,
                "Falta el paquete 'keyboard'.\nEjecuta: pip install keyboard",
            )
            self.root.destroy()
            return
        self.hotkey_lib = keyboard
        self.hotkey_lib.add_hotkey(self.hotkey, self._toggle)

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------ UI ------------------------------ #
    def _build_ui(self):
        pad = {"padx": 12, "pady": 6}
        frame = ttk.Frame(self.root, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frame, text="Auto Clicker Simple", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 10)
        )

        self.toggle_btn = ttk.Button(frame, text="Activar", command=self._toggle)
        self.toggle_btn.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        ttk.Label(frame, text="Intervalo (ms):").grid(row=2, column=0, sticky="w", **pad)
        self.interval_var = tk.StringVar(value=str(self.interval_ms))
        ttk.Spinbox(
            frame,
            from_=10,
            to=600000,
            increment=10,
            textvariable=self.interval_var,
            width=10,
        ).grid(row=2, column=1, sticky="e", **pad)

        ttk.Label(frame, text="Boton:").grid(row=3, column=0, sticky="w", **pad)
        self.button_var = tk.StringVar(value=self.button)
        ttk.Combobox(
            frame,
            textvariable=self.button_var,
            values=["left", "right", "middle"],
            state="readonly",
            width=8,
        ).grid(row=3, column=1, sticky="e", **pad)

        ttk.Label(frame, text="Tipo de clic:").grid(row=4, column=0, sticky="w", **pad)
        self.click_type_var = tk.StringVar(value="simple")
        ttk.Combobox(
            frame,
            textvariable=self.click_type_var,
            values=["simple", "doble"],
            state="readonly",
            width=8,
        ).grid(row=4, column=1, sticky="e", **pad)

        ttk.Label(frame, text="Atajo global:").grid(row=5, column=0, sticky="w", **pad)
        hotkey_row = ttk.Frame(frame)
        hotkey_row.grid(row=5, column=1, sticky="e", **pad)
        self.hotkey_var = tk.StringVar(value=self.hotkey)
        ttk.Entry(hotkey_row, textvariable=self.hotkey_var, width=8).pack(
            side="left", padx=(0, 4)
        )
        ttk.Button(
            hotkey_row, text="Capturar", command=self._capture_hotkey
        ).pack(side="left")

        self.count_label = ttk.Label(frame, text="Clics realizados: 0")
        self.count_label.grid(row=6, column=0, columnspan=2, pady=(8, 0))

        self.status_label = ttk.Label(
            frame,
            text=f"Listo. Atajo: {self.hotkey} (funciona sin foco).",
            wraplength=340,
        )
        self.status_label.grid(row=7, column=0, columnspan=2, pady=(4, 0))

    # --------------------------- control --------------------------- #
    def _on_hotkey_changed(self):
        hotkey = self.hotkey_var.get().strip().lower()
        if not hotkey:
            return
        try:
            self.hotkey_lib.remove_all_hotkeys()
        except Exception:
            pass
        self.hotkey_lib.add_hotkey(hotkey, self._toggle)
        self.hotkey = hotkey
        self.status_label.config(text=f"Atajo cambiado a: {hotkey}.")

    def _capture_hotkey(self):
        self.status_label.config(text="Pulsa la tecla que quieras como atajo...")
        threading.Thread(target=self._capture_hotkey_worker, daemon=True).start()

    def _capture_hotkey_worker(self):
        try:
            hotkey = self.hotkey_lib.read_hotkey(suppress=False)
        except Exception as error:
            self.root.after(0, lambda: self.status_label.config(text=str(error)))
            return
        self.root.after(0, lambda: (self.hotkey_var.set(hotkey), self._on_hotkey_changed()))

    def _toggle(self):
        if self.active:
            self._stop.set()
        else:
            self.active = True
            self._stop.clear()
            threading.Thread(target=self._click_worker, daemon=True).start()
        self._refresh_ui()

    def _click_worker(self):
        while self.active and not self._stop.is_set():
            try:
                if self.click_type_var.get() == "doble":
                    click_double(self.button_var.get())
                    self.click_count += 2
                else:
                    click(self.button_var.get())
                    self.click_count += 1
            except Exception as error:
                self._stop.set()
                self.active = False
                self.root.after(0, lambda: self.status_label.config(text=f"Error: {error}"))
                self.root.after(0, self._refresh_ui)
                break
            self._refresh_count()
            try:
                interval = max(10, int(self.interval_var.get()))
            except ValueError:
                interval = 100
            time.sleep(interval / 1000.0)
        self.active = False
        self.root.after(0, self._refresh_ui)

    def _refresh_count(self):
        self.root.after(
            0, lambda: self.count_label.config(text=f"Clics realizados: {self.click_count}")
        )

    def _refresh_ui(self):
        if self.active:
            self.toggle_btn.config(text="Desactivar")
            self.status_label.config(text="Activo: haciendo clics.")
        else:
            self.toggle_btn.config(text="Activar")
            self.status_label.config(
                text=f"Detenido. Atajo: {self.hotkey} (funciona sin foco)."
            )

    def _on_close(self):
        self.active = False
        self._stop.set()
        if self.hotkey_lib:
            try:
                self.hotkey_lib.remove_all_hotkeys()
            except Exception:
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    parser = argparse.ArgumentParser(description="Auto Clicker Simple (Windows)")
    parser.add_argument("--interval", type=int, default=100)
    parser.add_argument("--button", choices=["left", "right", "middle"], default="left")
    parser.add_argument("--hotkey", default="f8")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    app = ClickerApp(
        interval_ms=args.interval,
        button=args.button,
        hotkey=args.hotkey,
    )
    if not app.root.winfo_exists():
        return 1
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())