# analyze_logs.py — Guía de uso

Herramienta de línea de comandos para analizar ficheros ULS reales de SharePoint y mejorar `src/smart_rules.json`.  
Evalúa las reglas activas contra los logs, mide su cobertura e identifica patrones nuevos que aún no están cubiertos.

---

## Casos de uso

### UC-1 · Ver qué reglas detectan algo en un log real

El caso más habitual: cargar un log de producción y comprobar cuáles de las 54+ reglas activas tienen matches y cuáles están en 0.

```powershell
python scripts/analyze_logs.py "C:\Temp\LOGS\LAB01\UMEDVSHP001-20260526-0926.log"
```

Salida resumida:

```
Reglas cargadas: 64 total, 54 activas
Total filas cargadas : 110,387  (1 fichero(s))
Filas en niveles [CRITICAL, HIGH, MONITORABLE, UNEXPECTED]: 38,714

COBERTURA GLOBAL
  Cubiertas (≥1 regla): 2,916  (7.5%)
  No cubiertas        : 35,798 (92.5%)

COBERTURA POR REGLA
  2,831  Sync: Error
     85  PS: Security token expired
     12  PS: Claim in token is null
      0  WSP: Error al crear listas        ← sin match en este log
      ...
```

> **Nota:** 0 matches en un log concreto no significa que la regla esté mal;  
> puede que ese log sea de timer jobs y las reglas WSP/SPFx apliquen a otros entornos.

---

### UC-2 · Analizar varios logs a la vez (glob)

```powershell
python scripts/analyze_logs.py "C:\Temp\LOGS\LAB01\*.log"
```

Útil para comparar cobertura en un rango horario o entre servidores.

---

### UC-3 · Ver todos los niveles ULS (no solo errores)

Por defecto solo analiza `CRITICAL`, `HIGH`, `MONITORABLE` y `UNEXPECTED`.  
Para analizar también `MEDIUM`, `VERBOSE`, etc.:

```powershell
python scripts/analyze_logs.py "C:\Temp\LOGS\*.log" --all-levels
```

O elegir niveles concretos:

```powershell
python scripts/analyze_logs.py "C:\Temp\LOGS\*.log" --levels "CRITICAL,HIGH"
```

---

### UC-4 · Descubrir nuevos patrones (modo interactivo)

Tras el reporte, presenta los mensajes más frecuentes sin regla y permite añadirlos a `smart_rules.json` uno a uno:

```powershell
python scripts/analyze_logs.py "C:\Temp\LOGS\*.log" --learn
```

---

### UC-5 · Exportar candidatos para revisarlos con calma

```powershell
# Exportar
python scripts/analyze_logs.py "C:\Temp\LOGS\*.log" --out candidatos.json

# Editar candidatos.json en VS Code:
#   - Ajustar "domain", "pattern", "is_regex"
#   - Poner "enabled": true en los que se quieran activar

# Importar sin necesitar los logs
python scripts/analyze_logs.py --merge candidatos.json
```

---

### UC-6 · Testear las reglas WSP con texto de prueba (sin log real)

Para verificar que una regex WSP funciona antes de aplicarla a un log grande,
usar el script inline:

```python
# Desde la raíz del proyecto
import sys; sys.path.insert(0, "src")
from smart_rules import RulesEngine, DOMAIN_WSP

engine = RulesEngine()
for r in engine.get_rules_for_domain(DOMAIN_WSP):
    r.enabled = True  # activa también las deshabilitadas por defecto

rows = [
    {"_search_key": "Error al crear listas en el sitio raíz"},
    {"_search_key": "COLABORAWS.Infraestructure activated"},
    {"_search_key": "COLABORAWS.Infraestructure.Master feature"},
    {"_search_key": "Current User: COLABORAWS\\admin"},
    {"_search_key": "Solution deployment failed for ColaboraWS.wsp"},
    {"Message": "solution cannot be deployed to this farm"},  # campo Message
]
for idx, rules in engine.apply(rows, DOMAIN_WSP).items():
    print(f"Fila {idx}: {rows[idx]}")
    for r in rules:
        print(f"  ✓ [{r.name}]  pattern={r.pattern!r}")
```

---

## Entendiendo el reporte

| Sección | Qué muestra |
|---|---|
| **COBERTURA GLOBAL** | % de filas de error capturadas por al menos una regla activa |
| **COBERTURA POR REGLA** | Matches de cada regla, de mayor a menor. Las de 0 se listan aparte con su patrón |
| **TOP FRASES NO CUBIERTAS** | Mensajes normalizados más frecuentes sin regla; base para nuevas reglas |
| **TOP GRUPOS Category+Area** | Qué subsistemas SharePoint generan más ruido sin capturar |

El normalizador reemplaza valores variables por marcadores:  
`<GUID>`, `<PATH>`, `<N>`, `<HEX>`, `<STR>` — así agrupa variantes del mismo error.

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
