import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

from config import obtener_ruta_config


class EditorConfigApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Editor configuracion Personio")
        self.root.geometry("620x430")

        self.ruta_config = Path(obtener_ruta_config())
        self.data = self._cargar()

        self.vars = {
            "employee_id": tk.StringVar(value=str(self.data.get("employee_id", ""))),
            "timezone": tk.StringVar(value=self.data.get("timezone", "Europe/Madrid")),
            "base_url": tk.StringVar(value=self.data.get("base_url", "https://unikaltech.app.personio.com")),
            "morning_start": tk.StringVar(value=self.data.get("morning_start", "08:30")),
            "morning_end": tk.StringVar(value=self.data.get("morning_end", "14:30")),
            "afternoon_start": tk.StringVar(value=self.data.get("afternoon_start", "15:30")),
            "afternoon_end": tk.StringVar(value=self.data.get("afternoon_end", "18:00")),
            "friday_start": tk.StringVar(value=self.data.get("friday_start", "09:00")),
            "friday_end": tk.StringVar(value=self.data.get("friday_end", "15:00")),
            "headless": tk.BooleanVar(value=bool(self.data.get("headless", False))),
            "modo_prueba": tk.BooleanVar(value=bool(self.data.get("modo_prueba", False))),
            "modo_interactivo": tk.BooleanVar(value=bool(self.data.get("modo_interactivo", True))),
        }

        self._build_ui()

    def _cargar(self) -> dict:
        if not self.ruta_config.exists():
            return {}
        try:
            with self.ruta_config.open("r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            messagebox.showwarning(
                "Configuracion invalida",
                "El JSON de configuracion esta dañado o no es valido. "
                "Se cargara el formulario con valores por defecto.",
            )
            return {}

    def _crear_payload(self) -> dict:
        employee_id_raw = self.vars["employee_id"].get().strip()
        if not employee_id_raw:
            raise ValueError("employee_id es obligatorio.")

        try:
            employee_id = int(employee_id_raw)
        except ValueError as exc:
            raise ValueError("employee_id debe ser un numero entero.") from exc

        if employee_id <= 0:
            raise ValueError("employee_id debe ser mayor que 0.")

        payload = {
            "employee_id": employee_id,
            "timezone": self.vars["timezone"].get().strip(),
            "base_url": self.vars["base_url"].get().strip(),
            "morning_start": self.vars["morning_start"].get().strip(),
            "morning_end": self.vars["morning_end"].get().strip(),
            "afternoon_start": self.vars["afternoon_start"].get().strip(),
            "afternoon_end": self.vars["afternoon_end"].get().strip(),
            "friday_start": self.vars["friday_start"].get().strip(),
            "friday_end": self.vars["friday_end"].get().strip(),
            "headless": bool(self.vars["headless"].get()),
            "modo_prueba": bool(self.vars["modo_prueba"].get()),
            "modo_interactivo": bool(self.vars["modo_interactivo"].get()),
        }

        required_text_fields = [
            "timezone",
            "base_url",
            "morning_start",
            "morning_end",
            "afternoon_start",
            "afternoon_end",
            "friday_start",
            "friday_end",
        ]
        for field_name in required_text_fields:
            if not payload[field_name]:
                raise ValueError(f"{field_name} no puede estar vacio.")

        return payload

    def _build_ui(self):
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill="both", expand=True)

        campos = [
            "employee_id",
            "timezone",
            "base_url",
            "morning_start",
            "morning_end",
            "afternoon_start",
            "afternoon_end",
            "friday_start",
            "friday_end",
        ]

        for idx, key in enumerate(campos):
            ttk.Label(frame, text=key).grid(row=idx, column=0, sticky="w", pady=5)
            ttk.Entry(frame, textvariable=self.vars[key], width=48).grid(
                row=idx, column=1, sticky="ew", pady=5
            )

        row_base = len(campos)
        ttk.Checkbutton(frame, text="headless", variable=self.vars["headless"]).grid(
            row=row_base, column=0, sticky="w", pady=8
        )
        ttk.Checkbutton(frame, text="modo_prueba", variable=self.vars["modo_prueba"]).grid(
            row=row_base + 1, column=0, sticky="w", pady=8
        )
        ttk.Checkbutton(frame, text="modo_interactivo", variable=self.vars["modo_interactivo"]).grid(
            row=row_base + 2, column=0, sticky="w", pady=8
        )

        botones = ttk.Frame(frame)
        botones.grid(row=row_base + 3, column=0, columnspan=2, pady=16, sticky="w")

        ttk.Button(botones, text="Guardar", command=self.guardar).pack(side="left", padx=5)
        ttk.Button(botones, text="Salir", command=self.root.destroy).pack(side="left", padx=5)

        frame.columnconfigure(1, weight=1)

    def guardar(self):
        try:
            payload = self._crear_payload()

            self.ruta_config.parent.mkdir(parents=True, exist_ok=True)
            with self.ruta_config.open("w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)

            messagebox.showinfo("Guardado", f"Configuracion guardada en {self.ruta_config}")
        except ValueError as exc:
            messagebox.showerror("Validacion", str(exc))
        except Exception as exc:
            messagebox.showerror("Error de escritura", f"No se pudo guardar: {exc}")


def main():
    root = tk.Tk()
    app = EditorConfigApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
