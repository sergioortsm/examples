Claro, aquí lo tienes en **Markdown puro y limpio**, listo para guardar como `.md`:

````md
# 🧠 Guía: Montar Ollama local e integrarlo en un proyecto Python

Esta guía explica cómo montar un LLM local con **Ollama** e integrarlo en Python para análisis de logs (por ejemplo ULS de SharePoint).

---

# 1. 📦 Instalación de Ollama

Descarga e instala Ollama desde:

https://ollama.com

---

## Verificar instalación

```bash
ollama --version
````

---

# 2. 🚀 Descargar un modelo LLM

Ejecuta un modelo local:

```bash
ollama run llama3
```

Otros modelos útiles:

```bash
ollama run mistral
ollama run qwen
ollama run llama3.1
```

---

## Prueba rápida

```text
Hola, analiza este error:
Could not load assembly in SharePoint
```

---

# 3. 🧠 API local de Ollama

Ollama expone una API local automáticamente:

```
http://localhost:11434
```

---

## Test con curl

```bash
curl http://localhost:11434/api/generate -d "{
  \"model\": \"llama3\",
  \"prompt\": \"Explica este error: Access denied in SharePoint\",
  \"stream\": false
}"
```

---

# 4. 🐍 Crear proyecto Python

## Crear entorno

```bash
mkdir sharepoint-ai-logs
cd sharepoint-ai-logs

python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

---

## Instalar dependencias

```bash
pip install requests
```

---

# 5. 🤖 Conectar Python con Ollama

## Script básico

```python
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"

def query_llm(prompt, model="llama3"):
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": model,
            "prompt": prompt,
            "stream": False
        }
    )

    return response.json()["response"]


log_example = """
Could not load assembly COLABORAWS.Infrastructure
SPDistributedCachePointerWrapper failed
Access denied for SPFarm account
"""

prompt = f"""
Eres un experto en SharePoint 2022 SE.
Analiza estos logs y encuentra la causa raíz:

{log_example}
"""

result = query_llm(prompt)

print(result)
```

---

# 6. 📊 Arquitectura recomendada

```text
ULS Logs
   ↓
Python Parser
   ↓
JSON estructurado
   ↓
Prompt + contexto
   ↓
Ollama (LLM)
   ↓
Diagnóstico
```

---

# 7. 🧩 Mejora importante: preprocesado de logs

Convierte logs en estructura antes de enviarlos:

```python
log = {
    "timestamp": "...",
    "server": "SPWEB01",
    "level": "Unexpected",
    "correlation_id": "...",
    "message": "Could not load assembly"
}
```

---

## Enviar solo lo relevante al LLM

❌ Incorrecto:

* 50.000 líneas de logs

✔ Correcto:

* 10–50 líneas relevantes filtradas

---

# 8. ⚡ Mejora avanzada (opcional)

Añadir búsqueda semántica:

* OpenSearch
* Elasticsearch
* Qdrant
* pgvector

Flujo:

```text
Logs → Indexación → Búsqueda → LLM → Respuesta
```

---

# 9. 🧠 Qué podrás hacer

* Diagnóstico de errores WSP
* Análisis de Timer Service
* Problemas de Distributed Cache
* Errores Kerberos / NTLM
* Correlación de ULS + IIS + Event Viewer

---

# 10. 🎯 Resultado final

Tendrás un sistema tipo:

**“Copilot de diagnóstico de SharePoint logs”**

* Local
* Privado
* Extensible
* Sin coste por uso

---

```

Si quieres, el siguiente paso útil sería que te monte un **parser real de ULS (con regex + correlación de IDs)** para que esto empiece a ser útil de verdad en SharePoint en cuanto lo ejecutes.
```
