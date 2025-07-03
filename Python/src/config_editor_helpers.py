
import json
import tkinter as tk
from tkinter import ttk, messagebox
import shutil
import os

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
            "modo_prueba": tk.BooleanVar(),
            "modo_interactivo": tk.BooleanVar()
        }

        self.build()

    def build(self):
        for i, (key, var) in enumerate(self.fields.items()):
            ttk.Label(self.frame, text=key + ":").grid(row=i, column=0, sticky="w")
            if isinstance(var, tk.BooleanVar):
                ttk.Checkbutton(self.frame, variable=var).grid(row=i, column=1, sticky="w")
            else:
                ttk.Entry(self.frame, textvariable=var, width=50).grid(row=i, column=1, sticky="ew")

        for key in self.fields:
            value = self.manager.data.get(key, "" if isinstance(self.fields[key], tk.StringVar) else False)
            self.fields[key].set(value)

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

        self.build()

    def build(self):
        
        for i, key in enumerate(self.fechas_keys):
            ttk.Label(self.frame, text=key).grid(row=i, column=0, sticky="w")

            # Listbox sin rowspan
            lista = tk.Listbox(self.frame, height=5, selectmode=tk.SINGLE, width=25)
            lista.grid(row=i, column=1, padx=(10, 0), pady=10, sticky="nsew")

            # Scrollbar vertical en columna adyacente
            scrollbar = tk.Scrollbar(self.frame, orient=tk.VERTICAL, command=lista.yview)
            scrollbar.grid(row=i, column=2, sticky="ns", pady=10)

            # Conecta scrollbar y listbox
            lista.config(yscrollcommand=scrollbar.set)

            self.listas[key] = lista

            for fecha in self.manager.data.get(key, []):
                lista.insert(tk.END, fecha)

            entrada = tk.Entry(self.frame, width=12)
            entrada.grid(row=i, column=3)

            actualizar_btn = ttk.Button(self.frame, w=3, text="✏️", command=lambda k=key, e=entrada: self.actualizar(k, e))
            actualizar_btn.grid(row=i, column=6)

            lista.bind("<Double-1>", lambda event, k=key, e=entrada: self.editar(k, e))

            ttk.Button(self.frame, text="+", w=3, command=lambda k=key, e=entrada: self.agregar(k, e)).grid(row=i, column=4)
            ttk.Button(self.frame, text="-", w=3, command=lambda k=key: self.eliminar(k)).grid(row=i, column=5)

    def editar(self, key, entrada):
        lista = self.listas[key]
        if lista.curselection():
            index = lista.curselection()[0]
            entrada.delete(0, tk.END)
            entrada.insert(0, lista.get(index))
            self.selected_index[key] = index

    def actualizar(self, key, entrada):
        val = entrada.get()
        if val and key in self.selected_index:
            index = self.selected_index[key]
            self.listas[key].delete(index)
            self.listas[key].insert(index, val)
            entrada.delete(0, tk.END)


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
        
        self.lista = tk.Listbox(self.frame, height=10, selectmode=tk.SINGLE, width=30)
        self.lista.grid(row=0, column=0, rowspan=3, padx=(10, 5), pady=10)
        self.lista.bind("<Double-1>", self.editar)

        self.entrada_inicio = tk.Entry(self.frame, width=12)
        self.entrada_inicio.grid(row=0, column=1, padx=(5, 5))

        self.entrada_fin = tk.Entry(self.frame, width=12)
        self.entrada_fin.grid(row=0, column=2, padx=(5, 5))

        self.agregar_btn = ttk.Button(self.frame, text="+", w=3, command=self.agregar)
        self.agregar_btn.grid(row=0, column=3)

        self.eliminar_btn = ttk.Button(self.frame, text="-",  w=3, command=self.eliminar)
        self.eliminar_btn.grid(row=0, column=4)

        self.actualizar_btn = ttk.Button(self.frame, text="✏️",  w=3, command=self.actualizar)
        self.actualizar_btn.grid(row=0, column=5)

        for rango in self.manager.data.get("JORNADA_INTENSIVA", []):
            self.lista.insert(tk.END, f"{rango['inicio']} → {rango['fin']}")


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
                self.selected_index = index

    def actualizar(self):
        inicio = self.entrada_inicio.get()
        fin = self.entrada_fin.get()
        if inicio and fin and self.selected_index is not None:
            nuevo_valor = f"{inicio} → {fin}"
            self.lista.delete(self.selected_index)
            self.lista.insert(self.selected_index, nuevo_valor)
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

        for i, key in enumerate(self.horario_keys):
            ttk.Label(self.frame, text=key).grid(row=i*2, column=0, sticky="w")
            
            lista = tk.Listbox(self.frame, height=5, width=40)
            lista.grid(row=i*2, column=1, columnspan=3, sticky="w")
            self.listas[key] = lista

            # Cargar datos iniciales
            for entrada in self.manager.data.get(key, []):
                lista.insert(tk.END, f"{entrada[0]} | {entrada[1]}")

            # Entradas para hora y tipo
            h = tk.Entry(self.frame, width=8)
            t = tk.Entry(self.frame, width=10)
            h.grid(row=i*2+1, column=1, padx=2, pady=5)
            t.grid(row=i*2+1, column=2, padx=2, pady=5, sticky="w")

            self.entries_h[key] = h
            self.entries_t[key] = t

            # Botones
            ttk.Button(self.frame, w=3, text="+", command=lambda k=key: self.agregar(k)).grid(row=i*2+1, column=3, padx=2)
            ttk.Button(self.frame, w=3, text="-", command=lambda k=key: self.eliminar(k)).grid(row=i*2+1, column=4, padx=2)
            ttk.Button(self.frame, w=3, text="✏️", command=lambda k=key: self.actualizar(k)).grid(row=i*2+1, column=5, padx=2)

            # Bind doble clic para editar
            lista.bind("<Double-1>", lambda event, k=key: self.editar(k))

    def agregar(self, key):
        h = self.entries_h[key].get()
        t = self.entries_t[key].get()
        if h and t:
            self.listas[key].insert(tk.END, f"{h} | {t}")
            self.entries_h[key].delete(0, tk.END)
            self.entries_t[key].delete(0, tk.END)

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
                self.entries_t[key].insert(0, partes[1].strip())
                self.selected_index[key] = index

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

    def guardar(self):
        for key in self.horario_keys:
            raw = self.listas[key].get(0, tk.END)
            self.manager.data[key] = [[r.split("|")[0].strip(), r.split("|")[1].strip()] for r in raw if "|" in r]
