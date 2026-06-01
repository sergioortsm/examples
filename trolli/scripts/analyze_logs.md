# analyze_logs.py — Guía de uso

Herramienta de análisis y aprendizaje para mejorar `src/smart_rules.json` a partir de ficheros ULS reales de SharePoint.

---

## Flujo básico

```powershell
# 1. Analizar logs y ver cobertura
.\.venv\Scripts\python.exe scripts\analyze_logs.py "C:\Temp\LOGS\*.log"

# 2. Con más detalle (top 50 patrones no cubiertos)
.\.venv\Scripts\python.exe scripts\analyze_logs.py "C:\Temp\LOGS\*.log" --top 50
```

El reporte muestra:
- **Cobertura global**: filas cubiertas por al menos una regla activa
- **Cobertura por regla**: matches de cada regla ordenados de mayor a menor
- **Reglas con 0 matches**: posibles patrones erróneos o irrelevantes para estos logs
- **Top frases no cubiertas**: mensajes normalizados más frecuentes sin regla asignada
- **Top grupos Category+Area**: para entender de qué subsistema vienen los huecos

---

## Opciones

| Opción | Defecto | Descripción |
|---|---|---|
| `--top N` | 30 | Líneas en cada sección del reporte |
| `--levels L,...` | `CRITICAL,HIGH,MONITORABLE,UNEXPECTED` | Niveles ULS a analizar |
| `--all-levels` | — | Analizar todos los niveles (ignora `--levels`) |
| `--min-count N` | 3 | Mínimo de ocurrencias para incluir un candidato |
| `--out FILE` | — | Exportar candidatos de nuevas reglas a un JSON |
| `--learn` | — | Modo aprendizaje interactivo (ver más abajo) |
| `--merge FILE` | — | Importar candidatos desde un JSON ya revisado |

---

## Modo aprendizaje interactivo (`--learn`)

Analiza los logs y, tras el reporte, presenta los candidatos uno a uno para decidir qué hacer con cada uno. Los aceptados se escriben en `src/smart_rules.json` **de forma inmediata**.

```powershell
.\.venv\Scripts\python.exe scripts\analyze_logs.py "C:\Temp\LOGS\*.log" --learn
```

### Teclas disponibles en el diálogo

| Tecla | Acción |
|---|---|
| `Enter` / `a` | Añadir la regla con los valores mostrados |
| `e` | Editar el patrón |
| `r` | Toggle `is_regex` true/false |
| `d` | Cambiar dominio (menú numerado con los 6 dominios) |
| `n` | Editar el nombre de la regla |
| `s` | Saltar este candidato (no se añade) |
| `q` | Guardar lo aceptado hasta aquí y salir |

### Dominios disponibles

| # | Dominio | Color |
|---|---|---|
| 1 | SPFx | `#FF6F00` |
| 2 | Timer Jobs | `#1565C0` |
| 3 | wsps / Paquetes | `#2E7D32` |
| 4 | PowerShell / Deploy | `#B71C1C` |
| 5 | Distributed Cache | `#BF360C` |
| 6 | Config / Object Cache | `#4527A0` |

El dominio y el color se asignan automáticamente por heurística (a partir de la categoría y área de los mensajes no cubiertos). Se puede afinar durante el diálogo con `d`.

---

## Flujo exportar → revisar → importar (`--out` + `--merge`)

Para revisar los candidatos con más calma antes de añadirlos:

```powershell
# Paso 1: exportar candidatos a un JSON
.\.venv\Scripts\python.exe scripts\analyze_logs.py "C:\Temp\LOGS\*.log" --out candidatos.json

# Paso 2: editar candidatos.json en VS Code
#   - Ajustar "domain" donde convenga
#   - Ajustar "pattern" / "is_regex" si es necesario
#   - Poner "enabled": true en los que se quieran activar

# Paso 3: importar (no necesita logs)
.\.venv\Scripts\python.exe scripts\analyze_logs.py --merge candidatos.json
```

Los candidatos con `"enabled": false` se ignoran. Los que ya existen en `smart_rules.json` (mismo `id`) se omiten silenciosamente.

---

## Ciclo de mejora continua recomendado

```
Nuevos logs llegan
      │
      ▼
analyze_logs.py "*.log"          ← ver cobertura actual
      │
      ▼
¿Hay huecos significativos?
  Sí → analyze_logs.py "*.log" --learn   ← aceptar/editar candidatos
      │
      ▼
analyze_logs.py "*.log"          ← verificar que la cobertura mejoró
```

---

## Notas

- Las reglas con **0 matches no son necesariamente erróneas**: las reglas de SPFx, WSP y PowerShell son válidas para otros entornos donde sí ocurran esos errores. No eliminarlas.
- El normalizador reemplaza GUIDs, rutas, números largos y strings entrecomillados por `<GUID>`, `<PATH>`, `<N>` y `<STR>` para agrupar variantes del mismo error.
- Los IDs de regla son MD5 del patrón (16 hex). Si se edita el patrón durante `--learn`, el ID se recalcula automáticamente.
