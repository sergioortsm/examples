import tkinter as tk
from tkinter import ttk
from config_editor_helpers import ConfigManager, GeneralTab, FechasTab, JornadasIntensivasTab, HorariosTab
from config import JORNADA_INTENSIVA, MODO_PRUEBA, MODO_INTERACTIVO, AUSENCIAS, VACACIONES, FESTIVOS, HORARIO_NORMAL, HORARIO_REDUCIDO, URL_FICHAJE, USUARIO, VIGILIAS_NACIONALES, VARIACION_MIN, VARIACION_MAX, HORA_EJECUCION, obtener_ruta_config

class ConfigEditorApp:

    def __init__(self, root):
        self.root = root
        self.root.title("Editor de configuración de fichajes")

        # Tamaño mínimo y centrado
        self.root.minsize(600, 600)
        self.centrar_ventana(600, 600)

        # Configurar layout con grid
        self.root.rowconfigure(0, weight=1)  # Expande el notebook
        self.root.columnconfigure(0, weight=1)

        RUTA_CONFIG = obtener_ruta_config()
        self.manager = ConfigManager(RUTA_CONFIG)

        # Crear el notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky="nsew")  # Se expande

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
        btn_frame.grid(row=1, column=0, pady=10)  # Abajo, fuera del notebook

        ttk.Button(btn_frame, text="Guardar", command=self.guardar).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Salir", command=self.root.quit).pack(side="left", padx=5)
        
        self.centrar_ventana(600, 600)  # Puedes ajustar el tamaño deseado
        
         
    def guardar(self):
        self.general_tab.guardar()
        self.fechas_tab.guardar()
        self.jornadas_tab.guardar()
        self.horarios_tab.guardar()
        self.manager.save()


    def centrar_ventana(self, ancho, alto):
        pantalla_ancho = self.root.winfo_screenwidth()
        pantalla_alto = self.root.winfo_screenheight()
        x = (pantalla_ancho // 2) - (ancho // 2)
        y = (pantalla_alto // 2) - (alto // 2)
        self.root.geometry(f"{ancho}x{alto}+{x}+{y}")
        
        
if __name__ == "__main__":
    root = tk.Tk()
    app = ConfigEditorApp(root)
    root.mainloop()
