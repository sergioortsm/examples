# install-ollama.ps1 — Guía de uso

Script PowerShell para instalar Ollama y descargar un modelo LLM local en servidores Windows. Diseñado para preparar el entorno que utiliza la vista **Buscador IA** de Trolli.

---

## Requisitos

- Windows 10 / Windows Server 2016 o superior
- PowerShell 5.1 o PowerShell 7+
- Conexión a Internet durante la instalación
- **Recomendado:** ejecutar como Administrador (para añadir Ollama al PATH del sistema)

---

## Uso

```powershell
# Instalación básica — descarga Ollama + modelo llama3
.\scripts\install-ollama.ps1

# Usar otro modelo
.\scripts\install-ollama.ps1 -Model mistral
.\scripts\install-ollama.ps1 -Model llama3.1
.\scripts\install-ollama.ps1 -Model qwen

# Solo instalar Ollama sin descargar ningún modelo ahora
.\scripts\install-ollama.ps1 -SkipModelPull
```

---

## Parámetros

| Parámetro | Tipo | Defecto | Descripción |
|---|---|---|---|
| `-Model` | `string` | `llama3` | Modelo a descargar tras la instalación |
| `-SkipModelPull` | `switch` | `$false` | Si se indica, omite la descarga del modelo |

---

## Qué hace el script paso a paso

1. **Comprueba** si Ollama ya está instalado en `%LOCALAPPDATA%\Programs\Ollama`.
2. Si no está, **descarga** el instalador oficial desde `https://ollama.com/download/OllamaSetup.exe`.
3. **Instala** Ollama en modo silencioso (`/SILENT`).
4. **Añade** el directorio de Ollama al PATH del sistema (requiere Administrador) y al PATH de la sesión actual.
5. **Arranca** el servidor `ollama serve` en segundo plano y espera hasta 18 segundos a que responda en `http://localhost:11434`.
6. **Descarga** el modelo indicado con `ollama pull <modelo>` (salvo `-SkipModelPull`).
7. Muestra un **resumen** de los modelos disponibles.

---

## Modelos recomendados por RAM

| RAM disponible | Modelo recomendado | Tamaño aprox. |
|---|---|---|
| 8 GB | `llama3` o `mistral` | ~4–5 GB |
| 16 GB | `llama3.1` o `qwen` | ~8 GB |
| 32 GB+ | `llama3.1:70b` | ~40 GB |

---

## Verificación manual

Tras ejecutar el script, confirma que todo funciona:

```powershell
# Listar modelos instalados
ollama list

# Probar el servidor directamente
curl http://localhost:11434/api/tags

# Probar el modelo en modo chat
ollama run llama3
```

---

## Resolución de problemas

**`ollama` no se reconoce como comando**
El PATH no se actualizó en la sesión actual. Añádelo manualmente:
```powershell
$env:PATH += ";$env:LOCALAPPDATA\Programs\Ollama"
```
O cierra y abre una nueva terminal.

**El servidor no responde tras la instalación**
Arráncalo manualmente en una terminal separada:
```powershell
ollama serve
```

**La descarga del modelo es muy lenta o se interrumpe**
`ollama pull` es reanudable. Vuelve a ejecutar el mismo comando y continuará desde donde lo dejó.

**Chip rojo "Ollama no disponible" en Trolli**
Verifica que el servidor está corriendo:
```powershell
curl http://localhost:11434/api/tags
```
Si no responde, ejecuta `ollama serve`.
