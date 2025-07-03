import tkinter as tk
from tkinter import ttk
from config_editor_helpers import ConfigManager, GeneralTab, FechasTab, JornadasIntensivasTab, HorariosTab
from config import JORNADA_INTENSIVA, modo_prueba, modo_interactivo, AUSENCIAS, VACACIONES, FESTIVOS, HORARIO_NORMAL, HORARIO_REDUCIDO, URL_FICHAJE, USUARIO, VIGILIAS_NACIONALES, VARIACION_MIN, VARIACION_MAX, HORA_EJECUCION, obtener_ruta_config

class ConfigEditorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Editor de configuración de fichajes")
        RUTA_CONFIG = obtener_ruta_config()
        self.manager = ConfigManager(RUTA_CONFIG)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True)

        # Pestañas
        self.general_tab = GeneralTab(self.notebook, self.manager)
        self.fechas_tab = FechasTab(self.notebook, self.manager)
        self.jornadas_tab = JornadasIntensivasTab(self.notebook, self.manager)
        self.horarios_tab = HorariosTab(self.notebook, self.manager)

        self.notebook.add(self.general_tab.frame, text="General")
        self.notebook.add(self.fechas_tab.frame, text="Fechas")
        self.notebook.add(self.jornadas_tab.frame, text="Jornada Intensiva")
        self.notebook.add(self.horarios_tab.frame, text="Horarios")

        # Botones de guardar y salir
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=10)

        ttk.Button(btn_frame, text="Guardar", command=self.guardar).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Salir", command=self.root.quit).pack(side="left", padx=5)

    def guardar(self):
        self.general_tab.guardar()
        self.fechas_tab.guardar()
        self.jornadas_tab.guardar()
        self.horarios_tab.guardar()
        self.manager.save()

if __name__ == "__main__":
    root = tk.Tk()
    app = ConfigEditorApp(root)
    root.mainloop()
