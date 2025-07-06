
import json
import tkinter as tk
from tkinter import PhotoImage, ttk, messagebox
import shutil
import os
from PIL import Image, ImageTk
from tool_tip import ToolTip
from utils import obtenerImagen
from constantes import BTN_WIDTH, BTN_HEIGHT, ICON_SIZE, BTN_PADDING
from tkcalendar import DateEntry

class ConfigManager:
    def __init__(self, path):
        self.path = path
        self.data = {}
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo cargar el archivo: {e}")
            self.data = {}

    def save(self):
        try:
            # Copia de seguridad
            backup_path = self.path + ".bak"
            if os.path.exists(self.path):
                shutil.copy2(self.path, backup_path)

            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)

            messagebox.showinfo("Guardado", "Configuración guardada correctamente. Copia de seguridad creada.")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar: {e}")
            json.dump(self.data, f, indent=4, ensure_ascii=False)
            messagebox.showinfo("Guardado", "Configuración guardada correctamente.")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar: {e}")

class GeneralTab:
    def __init__(self, parent, manager):
        self.manager = manager
        self.frame = ttk.Frame(parent, padding=10)

        self.fields = {
            "USUARIO": tk.StringVar(),
            "HORA_EJECUCION": tk.StringVar(),
            "URL_FICHAJE": tk.StringVar(),
            "RUTA_LOG": tk.StringVar(),
            "VARIACION_MIN": tk.IntVar(),
            "VARIACION_MAX": tk.IntVar(),
            "MODO_PRUEBA": tk.BooleanVar(),
            "MODO_INTERACTIVO": tk.BooleanVar()
        }

        self.build()

    def build(self):
        for i, (key, var) in enumerate(self.fields.items()):
            etiqueta = key.replace("_", " ").capitalize() + ":"
            ttk.Label(self.frame, text=etiqueta).grid(row=i, column=0, sticky="w", padx=5, pady=5)
            if isinstance(var, tk.BooleanVar):
                ttk.Checkbutton(self.frame, variable=var).grid(row=i, column=1, sticky="w", padx=5, pady=5)
            else:
                ttk.Entry(self.frame, textvariable=var, width=50).grid(row=i, column=1, sticky="ew", padx=5, pady=5)

        for key in self.fields:
            value = self.manager.data.get(key, "" if isinstance(self.fields[key], tk.StringVar) else False)
            self.fields[key].set(value)
        
        self.frame.columnconfigure(1, weight=1)
        
    def guardar(self):
        for key, var in self.fields.items():
            self.manager.data[key] = var.get()

class FechasTab:
    def __init__(self, parent, manager):
        self.manager = manager
        self.frame = ttk.Frame(parent, padding=10)

        self.fechas_keys = ["VACACIONES", "FESTIVOS", "VIGILIAS_NACIONALES", "AUSENCIAS"]
        self.listas = {}
        self.selected_index = {}
                
        # ← Aquí inicializamos todos los diccionarios
        self.listas         = {}
        self.entrada        = {}
        self.btn_agregar    = {}
        self.btn_eliminar   = {}
        self.btn_actualizar = {}
        self.cancelar_btns  = {}                
        self.vars_fecha = {}
        
        self.build()

    def build(self):
        
        imgAgregar = obtenerImagen(os.path.join("icons", "boton-agregar.png"))
        imgAgregar = imgAgregar.resize(ICON_SIZE, Image.Resampling.LANCZOS)
        self.agregar_img = ImageTk.PhotoImage(imgAgregar)    
        
        imgEliminar = obtenerImagen(os.path.join("icons", "boton-eliminar.png"))
        imgEliminar = imgEliminar.resize(ICON_SIZE, Image.Resampling.LANCZOS)
        self.eliminar_img = ImageTk.PhotoImage(imgEliminar)
        
        imgGuardar = obtenerImagen(os.path.join("icons", "boton-guardar.png"))
        imgGuardar = imgGuardar.resize(ICON_SIZE, Image.Resampling.LANCZOS)
        self.guardar_img = ImageTk.PhotoImage(imgGuardar)
        
        imgCancelar = obtenerImagen(os.path.join("icons", "boton-cancelar.png"))
        imgCancelar = imgCancelar.resize(ICON_SIZE, Image.Resampling.LANCZOS)
        self.cancelar_img = ImageTk.PhotoImage(imgCancelar)

        for i, key in enumerate(self.fechas_keys):
            fila0 = i * 2
            fila1 = fila0 + 1

            self.vars_fecha[key] = tk.StringVar()
            
            # ── Sub‑fila 1: Label + Listbox ─────────────────────
            etiqueta = key.replace("_", " ").capitalize() + ":"
            ttk.Label(self.frame, text=etiqueta).grid(row=fila0, column=0, sticky="w", pady=(0, 5))

            # Listbox en columna 1
            lista = tk.Listbox(self.frame, height=5, selectmode=tk.SINGLE)
            lista.grid(row=fila0, column=1, sticky="nsew", padx=(10, 0), pady=(0, 10))
            
            ToolTip(lista, "Haz doble clic para editar el elemento seleccionado")

            # Scrollbar justo al lado en columna 2
            scrollbar = tk.Scrollbar(self.frame, orient=tk.VERTICAL, command=lista.yview)
            scrollbar.grid(row=fila0, column=2, sticky="ns", padx=(0, 10), pady=(0, 10))

            # Vinculación del scrollbar al listbox
            lista.config(yscrollcommand=scrollbar.set)
            
            # Cargo datos iniciales
            for item in self.manager.data.get(key, []):
                lista.insert(tk.END, item)

            # Sub‑fila 2: Entry + Botones (dentro de un sub-frame horizontal)
            fila_botones = ttk.Frame(self.frame)
            fila_botones.grid(row=fila1, column=1, columnspan=6, sticky="w", padx=(10, 0), pady=(0, 15))

            #entry = tk.Entry(fila_botones, width=12)
            entry = DateEntry(fila_botones, date_pattern='yyyy-mm-dd', locale="es_ES", textvariable=self.vars_fecha[key])
            entry.grid(row=0, column=0, padx=(0, 5))
            entry.delete(0, 'end')
            self.entrada[key] = entry
            
            self.bind_edicion(entry, lista, key)

            #lista.bind("<Double-1>", lambda event, k=key, e=entry: self.editar(k, e))
            self.listas[key] = lista

            # Botón Agregar
            btn = ttk.Button(fila_botones, image=self.agregar_img, command=lambda k=key, e=entry: self.agregar(k, e))
            btn.grid(row=0, column=1, padx=(0, 5))
            ToolTip(btn, "Agregar elemento")
            self.btn_agregar[key] = btn

            # Botón Eliminar
            btn = ttk.Button(fila_botones, image=self.eliminar_img, command=lambda k=key: self.eliminar(k))
            btn.grid(row=0, column=2, padx=(0, 5))
            ToolTip(btn, "Eliminar elemento")
            self.btn_eliminar[key] = btn

            # Botón Actualizar
            btn = ttk.Button(fila_botones, image=self.guardar_img, command=lambda k=key, e=entry: self.actualizar(k, e))
            btn.grid(row=0, column=3, padx=(0, 5))
            btn.state(["disabled"])
            ToolTip(btn, "Actualizar elemento")
            self.btn_actualizar[key] = btn
            
            
            # Botón Cancelar
            btn = ttk.Button(fila_botones, image=self.cancelar_img, command=lambda k=key, e=entry: self.cancelar(k, e))
            btn.grid(row=0, column=4, padx=(0, 5))
            btn.state(["disabled"])
            ToolTip(btn, "Cancelar edición")
            self.cancelar_btns[key] = btn
           

        # Solo la columna de la lista (columna 1) se estira
        self.frame.columnconfigure(1, weight=1)

    def bind_edicion(self_ref, entry_widget, lista_widget, clave):
        
        def on_double_click(event):
            self_ref.editar(clave, entry_widget)
            
        lista_widget.bind("<Double-1>", on_double_click)
            
    def editar(self, key, entrada):
        lista = self.listas[key]
        
        if lista.curselection():         
            index = lista.curselection()[0]
            valor = lista.get(index)                
            self.listas[key].selected_index = index           
            entrada.set_date(valor) 
        
            # Habilita el botón “Cancelar” de esta lista
            btn = self.cancelar_btns[key]
            btn.state(["!disabled"])
            btn = self.btn_actualizar[key]
            btn.state(["!disabled"]) 
   
                
    def actualizar(self, key, entrada):
        val = entrada.get()
        lista = self.listas[key]
        
        if val:
            index = lista.selected_index
            lista.delete(index)
            lista.insert(index, val)
            entrada.delete(0, tk.END)
            
            # Habilita el botón “Cancelar” de esta lista
            btn = self.cancelar_btns[key]
            btn.state(["disabled"]) 
            btn = self.btn_actualizar[key]
            btn.state(["disabled"]) 
            
    def cancelar(self, key, entrada):
        lista = self.listas[key]
        lista.selection_clear(0, tk.END)
        entrada.delete(0, tk.END)
        
        # Habilita el botón “Cancelar” de esta lista
        btn = self.cancelar_btns[key]
        btn.state(["disabled"])
        btn = self.btn_actualizar[key]
        btn.state(["disabled"]) 
            
    def agregar(self, key, entrada):
        val = entrada.get()
        if val:
            self.listas[key].insert(tk.END, val)
            entrada.delete(0, tk.END)

    def eliminar(self, key):
        lista = self.listas[key]
        if lista.curselection():
            lista.delete(lista.curselection()[0])

    def guardar(self):
        for key in self.fechas_keys:
            self.manager.data[key] = list(self.listas[key].get(0, tk.END))

class JornadasIntensivasTab:
    def __init__(self, parent, manager):
        self.manager = manager
        self.frame = ttk.Frame(parent, padding=10)        
        self.selected_index = None
        self.actualizar_btns = {}
        self.cancelar_btns  = {}
        self.key = "JORNADAS_INTENSIVAS"
        self.var_inicio = tk.StringVar()
        self.var_fin = tk.StringVar()                    
        
        ttk.Label(self.frame, text="Jornadas intensivas:").grid(row=0, column=0, sticky="w")
        
        self.lista = tk.Listbox(self.frame, height=5, selectmode=tk.SINGLE, width=25)
        self.lista.grid(row=0, column=1, sticky="ew", padx=(10, 5), pady=10, columnspan=6)
        ToolTip(self.lista, "Haz doble clic para editar el elemento seleccionado")
        self.lista.bind("<Double-1>", self.editar)

        # ✅ Fila 1 se encapsula en un frame propio
        self.fila1 = ttk.Frame(self.frame)
        self.fila1.grid(row=1, column=1, columnspan=6, sticky="w", padx=(10, 0), pady=(5, 0))

        self.entrada_inicio = DateEntry(self.fila1, textvariable=self.var_inicio, date_pattern='yyyy-mm-dd', locale="es_ES")
        self.entrada_inicio.grid(row=0, column=1, sticky="w", padx=(10, 5), pady=5)
        self.entrada_inicio.delete(0, 'end')
                
        self.entrada_fin = DateEntry(self.fila1, textvariable=self.var_fin, date_pattern='yyyy-mm-dd', locale="es_ES")        
        self.entrada_fin.grid(row=0, column=2, sticky="w", padx=(10, 5), pady=5)
        self.entrada_fin.delete(0, 'end')
               
        self.var_inicio.trace_add("write", self.activar_boton_actualizar)
        self.var_fin.trace_add("write", self.activar_boton_actualizar)
        
        imgAgregar = obtenerImagen(os.path.join("icons", "boton-agregar.png"))
        imgAgregar = imgAgregar.resize(ICON_SIZE, Image.Resampling.LANCZOS)
        self.agregar_img = ImageTk.PhotoImage(imgAgregar)
        self.agregar_btn = ttk.Button(self.fila1, w=BTN_WIDTH, command=self.agregar, image=self.agregar_img)
        self.agregar_btn.grid(row=0, column=3, sticky="e")
        ToolTip(self.agregar_btn, "Agregar elemento")
        
        imgEliminar = obtenerImagen(os.path.join("icons", "boton-eliminar.png"))
        imgEliminar = imgEliminar.resize(ICON_SIZE, Image.Resampling.LANCZOS)
        self.eliminar_img = ImageTk.PhotoImage(imgEliminar)
        self.eliminar_btn = ttk.Button(self.fila1, w=BTN_WIDTH, command=self.eliminar, image=self.eliminar_img)
        self.eliminar_btn.grid(row=0, column=4, sticky="w")
        ToolTip(self.eliminar_btn, "Eliminar elemento")
        
        imgGuardar = obtenerImagen(os.path.join("icons", "boton-guardar.png"))
        imgGuardar = imgGuardar.resize(ICON_SIZE, Image.Resampling.LANCZOS)
        self.guardar_img = ImageTk.PhotoImage(imgGuardar)
        self.actualizar_btn = ttk.Button(self.fila1, w=BTN_WIDTH, command=self.actualizar, image=self.guardar_img)
        self.actualizar_btn.grid(row=0, column=5, sticky="w")
        self.actualizar_btn.state(["disabled"])
        ToolTip(self.actualizar_btn, "Actualizar elemento")
        self.actualizar_btns[self.key] = self.actualizar_btn
        
        imgCancelar = obtenerImagen(os.path.join("icons", "boton-cancelar.png"))
        imgCancelar = imgCancelar.resize(ICON_SIZE, Image.Resampling.LANCZOS)
        self.cancelar_img = ImageTk.PhotoImage(imgCancelar)
        self.cancelar_btn = ttk.Button(self.fila1, w=BTN_WIDTH, command=self.cancelar, image=self.cancelar_img)
        self.cancelar_btn.grid(row=0, column=6, sticky="w")
        self.cancelar_btn.state(["disabled"])
        ToolTip(self.cancelar_btn, "Cancelar edición")
        self.cancelar_btns[self.key] = self.cancelar_btn
        
        for rango in self.manager.data.get("JORNADA_INTENSIVA", []):
            self.lista.insert(tk.END, f"{rango['inicio']} → {rango['fin']}")

        self.frame.columnconfigure(1, weight=1)  # columna de la lista
    
    def validar_fecha(texto):
        if len(texto) > 10:
            return False
        allowed = "0123456789-"
        return all(c in allowed for c in texto)
    
    def activar_boton_actualizar(self, *args):
        actual_inicio = self.var_inicio.get()
        actual_fin = self.var_fin.get()
        original_inicio = getattr(self, "original_inicio", "")
        original_fin = getattr(self, "original_fin", "")
        
        if actual_inicio != original_inicio or actual_fin != original_fin:
            self.actualizar_btns[self.key].state(["!disabled"])
        else:
            self.actualizar_btns[self.key].state(["disabled"])
            
    def agregar(self):
        inicio = self.entrada_inicio.get()
        fin = self.entrada_fin.get()
        if inicio and fin:
            self.lista.insert(tk.END, f"{inicio} → {fin}")
            self.entrada_inicio.delete(0, tk.END)
            self.entrada_fin.delete(0, tk.END)

    def eliminar(self):
        if self.lista.curselection():
            self.lista.delete(self.lista.curselection()[0])

    def editar(self, event):
        if self.lista.curselection():
            index = self.lista.curselection()[0]
            valor = self.lista.get(index)
            partes = valor.split("→")
            if len(partes) == 2:
                self.entrada_inicio.delete(0, tk.END)
                self.entrada_inicio.insert(0, partes[0].strip())
                self.entrada_fin.delete(0, tk.END)
                self.entrada_fin.insert(0, partes[1].strip())
                self.lista.selected_index = index       
                # 👉 Guarda los valores originales para detectar cambios
                self.original_inicio = partes[0].strip()
                self.original_fin = partes[1].strip()
                
                # Habilita el botón “Cancelar” y desactiva “Actualizar”
                self.cancelar_btns[self.key].state(["!disabled"])
                self.actualizar_btns[self.key].state(["disabled"])                
                          
    def cancelar(self):        
        self.lista.selection_clear(0, tk.END)
        self.entrada_inicio.delete(0, tk.END)
        self.entrada_fin.delete(0, tk.END)
        self.lista.selected_index = 0
        
        btn = self.cancelar_btns[self.key]
        btn.state(["disabled"])
        btn = self.actualizar_btns[self.key]
        btn.state(["disabled"])
                
    def actualizar(self):
        inicio = self.entrada_inicio.get()
        fin = self.entrada_fin.get()
        if inicio and fin and  self.lista.selected_index is not None:
            nuevo_valor = f"{inicio} → {fin}"
            self.lista.delete(self.lista.selected_index)
            self.lista.insert(self.lista.selected_index, nuevo_valor)
            self.entrada_inicio.delete(0, tk.END)
            self.entrada_fin.delete(0, tk.END)
            self.selected_index = None
                        
    def guardar(self):
        rangos = []
        for i in range(self.lista.size()):
            item = self.lista.get(i)
            partes = item.split("→")
            if len(partes) == 2:
                inicio = partes[0].strip()
                fin = partes[1].strip()
                rangos.append({"inicio": inicio, "fin": fin})
        
        self.manager.data["JORNADA_INTENSIVA"] = rangos

class HorariosTab:
    def __init__(self, parent, manager):
        self.manager = manager
        self.frame = ttk.Frame(parent, padding=10)

        self.horario_keys = ["HORARIO_NORMAL", "HORARIO_REDUCIDO"]
        self.listas = {}
        self.entries_h = {}
        self.entries_t = {}
        self.selected_index = {}
        self.cancelar_btns = {}
        self.actualizar_btns = {}
        opciones = [" ","ClockIn", "ClockOut"]
        
        imgAgregar = obtenerImagen(os.path.join("icons", "boton-agregar.png"))
        imgAgregar = imgAgregar.resize(ICON_SIZE, Image.Resampling.LANCZOS)
        self.agregar_img = ImageTk.PhotoImage(imgAgregar)    
        
        imgEliminar = obtenerImagen(os.path.join("icons", "boton-eliminar.png"))
        imgEliminar = imgEliminar.resize(ICON_SIZE, Image.Resampling.LANCZOS)
        self.eliminar_img = ImageTk.PhotoImage(imgEliminar)
        
        imgGuardar = obtenerImagen(os.path.join("icons", "boton-guardar.png"))
        imgGuardar = imgGuardar.resize(ICON_SIZE, Image.Resampling.LANCZOS)
        self.guardar_img = ImageTk.PhotoImage(imgGuardar)
        
        imgCancelar = obtenerImagen(os.path.join("icons", "boton-cancelar.png"))
        imgCancelar = imgCancelar.resize(ICON_SIZE, Image.Resampling.LANCZOS)
        self.cancelar_img = ImageTk.PhotoImage(imgCancelar)
            
        for i, key in enumerate(self.horario_keys):
            fila0 = i * 2
            fila1 = fila0 + 1
            
            etiqueta = key.replace("_", " ").capitalize() + ":"
            ttk.Label(self.frame, text=etiqueta).grid(row=fila0, column=0, sticky="w")
            
            lista = tk.Listbox(self.frame, height=5, width=40)
            lista.grid(row=i*2, column=1, sticky="nsew", padx=(10, 5), pady=5)
            ToolTip(lista, "Haz doble clic para editar el elemento seleccionado")
            
            # Cargar datos iniciales
            for entrada in self.manager.data.get(key, []):
                lista.insert(tk.END, f"{entrada[0]} | {entrada[1]}")

            # Sub‑fila 2: Entry + Botones (dentro de un sub-frame horizontal)
            fila_botones = ttk.Frame(self.frame)
            fila_botones.grid(row=fila1, column=1, columnspan=6, sticky="w", padx=(10, 0), pady=(0, 15))
            
            # Entradas para hora y tipo
            h = tk.Entry(fila_botones, width=8)
            #t = tk.Entry(fila_botones, width=10)
            t = ttk.Combobox(fila_botones, width=10, values=opciones, state="readonly")  # state="readonly" impide edición manual
            
            h.grid(row=0, column=0, padx=10)
            t.grid(row=0, column=1, padx=10)

            self.entries_h[key] = h
            self.entries_t[key] = t
        
            # Bind doble clic para editar
            lista.bind("<Double-1>", lambda event, k=key: self.editar(k))
            self.listas[key] = lista
            
            # Botones
            btnAgregar = ttk.Button(fila_botones, image=self.agregar_img, command=lambda k=key: self.agregar(k))
            btnAgregar.grid(row=0, column=2, padx=(0,5))
            
            btnEliminar = ttk.Button(fila_botones, image=self.eliminar_img, command=lambda k=key: self.eliminar(k))
            btnEliminar.grid(row=0, column=3, padx=(0,5))
            ToolTip(btnEliminar, "Eliminar elemento")
                        
            actualizar_btn = ttk.Button(fila_botones, image=self.guardar_img, command=lambda k=key: self.actualizar(k))
            actualizar_btn.grid(row=0, column=4, padx=(0,5))
            actualizar_btn.state(["disabled"])
            ToolTip(actualizar_btn, "Actualizar elemento")            
            
            cancelar_btn = ttk.Button(fila_botones, image=self.cancelar_img, command=lambda k=key, e=entrada: self.cancelar(k))
            cancelar_btn.grid(row=0, column=5, padx=(0,5))
            cancelar_btn.state(["disabled"])
            ToolTip(cancelar_btn, "Cancelar edición")
            
            self.cancelar_btns[key] = cancelar_btn
            self.actualizar_btns[key] = actualizar_btn
            
        # Solo la columna de la lista (columna 1) se estira
        self.frame.columnconfigure(1, weight=1)
           
            
    def agregar(self, key):
        h = self.entries_h[key].get()
        t = self.entries_t[key].get()
        if h and t:
            self.listas[key].insert(tk.END, f"{h} | {t}")
            self.entries_h[key].delete(0, tk.END)
            self.entries_t[key].delete(0, tk.END)
            
            # Habilita el botón “Cancelar” de esta lista
            btn = self.cancelar_btns[key]
            btn.state(["!disabled"])
            btn = self.actualizar_btns[key]
            btn.state(["!disabled"])

    def eliminar(self, key):
        lista = self.listas[key]
        if lista.curselection():
            lista.delete(lista.curselection()[0])

    def editar(self, key):
        lista = self.listas[key]
        if lista.curselection():
            index = lista.curselection()[0]
            valor = lista.get(index)
            partes = valor.split("|")
            if len(partes) == 2:
                self.entries_h[key].delete(0, tk.END)
                self.entries_h[key].insert(0, partes[0].strip())
                self.entries_t[key].delete(0, tk.END)
                self.entries_t[key].set(partes[1].strip())
                #self.entries_t[key].insert(0, partes[1].strip())
                self.selected_index[key] = index
                # Habilita el botón “Cancelar” de esta lista
                btn = self.cancelar_btns[key]
                btn.state(["!disabled"])
                btn = self.actualizar_btns[key]
                btn.state(["!disabled"])                
        
            
    def cancelar(self, key):
        h = self.entries_h[key].get()
        t = self.entries_t[key].get()
        
        if h and t:            
            self.entries_h[key].delete(0, tk.END)
            self.entries_t[key].set(" ")
            #self.entries_t[key].delete(0, tk.END)
                    
        lista = self.listas[key]
        lista.selection_clear(0, tk.END)

        # Habilita el botón “Cancelar” de esta lista
        btn = self.cancelar_btns[key]
        btn.state(["disabled"])
        btn = self.actualizar_btns[key]
        btn.state(["disabled"])
                
    def actualizar(self, key):
        h = self.entries_h[key].get()
        t = self.entries_t[key].get()
        if h and t and key in self.selected_index:
            index = self.selected_index[key]
            self.listas[key].delete(index)
            self.listas[key].insert(index, f"{h} | {t}")
            self.entries_h[key].delete(0, tk.END)
            self.entries_t[key].delete(0, tk.END)
            del self.selected_index[key]
            
            # Habilita el botón “Cancelar” de esta lista
            btn = self.cancelar_btns[key]
            btn.state(["disabled"])
            btn = self.actualizar_btns[key]
            btn.state(["disabled"])            

    def guardar(self):
        for key in self.horario_keys:
            raw = self.listas[key].get(0, tk.END)
            self.manager.data[key] = [[r.split("|")[0].strip(), r.split("|")[1].strip()] for r in raw if "|" in r]
