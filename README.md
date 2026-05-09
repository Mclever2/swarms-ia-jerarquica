# SwarmsIA — Sistema de Mentoría Académica Jerárquico Multi-Agente

Sistema de evaluación automática de proyectos de tesis universitarios basado en una
arquitectura **jerárquica multi-agente pura**, RAG con embeddings locales y la rúbrica
oficial UPAO (33 ítems). El Director LLM orquesta dinámicamente a los agentes
especializados mediante **tool calling** — sin flujos hardcodeados en Python.

---

## Índice

1. [Descripción general](#1-descripción-general)
2. [Arquitectura jerárquica](#2-arquitectura-jerárquica)
3. [Stack tecnológico](#3-stack-tecnológico)
4. [Estructura del proyecto](#4-estructura-del-proyecto)
5. [Instalación](#5-instalación)
6. [Configuración](#6-configuración)
7. [Arrancar la aplicación](#7-arrancar-la-aplicación)
8. [Flujo de uso](#8-flujo-de-uso)
9. [Sistema RAG](#9-sistema-rag)
10. [Rúbrica UPAO](#10-rúbrica-upao)
11. [Variables de entorno](#11-variables-de-entorno)

---

## 1. Descripción general

SwarmsIA es una plataforma de mentoría académica que evalúa proyectos de tesis
siguiendo la rúbrica oficial de la Universidad Privada Antenor Orrego (UPAO - Facultad
de Ingeniería). El mentor sube el PDF del proyecto y selecciona la sección a analizar;
el sistema despliega un enjambre de agentes especializados que evalúan, analizan,
debaten y proponen texto mejorado.

**Capacidades principales:**

- Evaluación automática de las 7 secciones del proyecto de tesis contra los 33 ítems
  de la rúbrica UPAO con escala 0-3 por ítem y conversión a nota vigesimal.
- Análisis de **dependencias cruzadas** entre secciones (ej. si el problema está bien
  planteado, valida coherencia con título, hipótesis y metodología).
- Base de conocimiento RAG con libros de metodología de investigación para
  fundamentar las observaciones de los agentes.
- Interfaz HITL (Human-in-the-Loop) donde el mentor puede editar el texto propuesto
  antes de aprobarlo.

---

## 2. Arquitectura jerárquica

El sistema implementa jerarquía multi-agente **pura**: cada herramienta del Director
involucra exactamente un agente subordinado. El Director LLM toma todas las decisiones
de routing; Python no hardcodea el flujo.

```
Director LLM  (groq/llama-3.3-70b-versatile)
│
│  tool_call: convocar_auditor()
├──────────────────────────> Auditor UPAO
│                            Evalúa ítems 0-3 de la rúbrica
│  <────────────── reporte con puntajes + observaciones por ítem
│
│  tool_call: convocar_metodologico()
├──────────────────────────> Metodólogo
│                            Analiza coherencia científica y dependencias cruzadas
│  <────────────── observaciones narrativas numeradas
│
│  [Director sintetiza ambos reportes y formula instrucciones]
│
│  tool_call: convocar_redactor(instrucciones)
├──────────────────────────> Redactor Académico
│                            Produce texto mejorado según instrucciones del Director
│  <────────────── texto mejorado + argumento
│
│  [Opcional — si quedan ítems observados]
│
│  tool_call: revisar_texto_auditor(texto, items)
├──────────────────────────> Auditor UPAO
│                            Valida si el texto propuesto levantó las observaciones
│  <────────────── veredicto por ítem
│
│  tool_call: revisar_texto_metodologico(texto, observaciones)
├──────────────────────────> Metodólogo
│                            Verifica coherencia del texto propuesto
│  <────────────── análisis de revisión
│
│  [Director sintetiza revisiones y decide: aprobar o re-instruir al Redactor]
│
└──> VEREDICTO FINAL: nota vigesimal + estado + recomendaciones
```

**Reglas de jerarquía:**
- Ningún agente se comunica con otro directamente. Todo pasa por el Director.
- Cada tool es atómica: 1 tool = 1 agente = 1 resultado.
- El Director decide el orden, la cantidad de iteraciones y cuándo terminar.

---

## 3. Stack tecnológico

| Componente | Tecnología |
|---|---|
| Orquestación multi-agente | [Swarms](https://github.com/kyegomez/swarms) >= 7.0 |
| LLM (Director + Workers) | Groq API — `llama-3.3-70b-versatile` |
| Embeddings locales | HuggingFace `sentence-transformers/all-MiniLM-L6-v2` |
| Vector store (biblioteca) | ChromaDB persistente en disco |
| Vector store (tesis) | ChromaDB efímero en memoria (por sesión) |
| Chunking y RAG | LangChain (text-splitters + langchain-chroma) |
| Extracción de PDF | pdfplumber |
| Frontend | Streamlit >= 1.35 |
| Validación de datos | Pydantic v2 |

---

## 4. Estructura del proyecto

```
mentoria_swarms/
│
├── backend/                        # Lógica del sistema multi-agente
│   │
│   ├── agents/                     # Agentes del enjambre
│   │   ├── director.py             # Nodo raíz — orquesta con tool calling
│   │   ├── herramientas.py         # Las 5 tools que el Director puede invocar
│   │   ├── auditor.py              # Evalúa ítems de la rúbrica UPAO (0-3)
│   │   ├── metodologico.py         # Analiza coherencia científica entre secciones
│   │   ├── redactor.py             # Produce y refina texto académico
│   │   └── debate.py               # (Legacy) módulo de debate — conservado como referencia
│   │
│   ├── prompts/                    # System prompts de cada agente (archivos .md)
│   │   ├── director_jerarquico_prompt.md   # Prompt del Director con árbol jerárquico
│   │   ├── auditor_prompt.md               # Formato JSON obligatorio de evaluación
│   │   ├── metodologico_prompt.md          # Análisis narrativo de coherencia
│   │   └── redactor_prompt.md              # Formato TEXTO MEJORADO / ARGUMENTO
│   │
│   ├── rag/                        # Sistema de recuperación aumentada (RAG)
│   │   ├── embeddings.py           # Carga del modelo HuggingFace (MiniLM-L6-v2)
│   │   ├── extractor.py            # Extracción de texto PDF + segmentación en secciones
│   │   ├── tesis_store.py          # ChromaDB efímero — índice del proyecto del estudiante
│   │   └── library_store.py        # ChromaDB persistente — biblioteca de metodología
│   │
│   ├── config.py                   # Configuración global, rúbrica UPAO, dependencias cruzadas
│   └── utils.py                    # run_agent_silently, extract_json, call_with_backoff, use_groq_key
│
├── frontend/                       # Interfaz Streamlit
│   ├── app.py                      # Router principal (4 pantallas)
│   ├── resources.py                # Singletons cacheados con @st.cache_resource
│   ├── session_manager.py          # Gestión de st.session_state
│   └── components/
│       ├── sidebar.py              # Gestión de biblioteca + estado del sistema
│       ├── pantalla_upload.py      # Pantalla 1: carga del PDF de tesis
│       ├── pantalla_seleccion.py   # Pantalla 2: selección de sección a evaluar
│       ├── pantalla_revision.py    # Pantalla 3: ejecución del pipeline + HITL
│       └── pantalla_resultado.py   # Pantalla 4: resultado aprobado + descarga
│
├── books/                          # PDFs de metodología de investigación (pre-cargados)
│   ├── Hernández - Metodología de la investigación.pdf
│   └── ...
│
├── chroma_db/                      # Base vectorial persistente (generada automáticamente)
│
├── .env                            # Claves de API y parámetros del pipeline
└── requirements.txt                # Dependencias Python
```

### Archivos clave explicados

**`backend/config.py`**
Fuente única de verdad del sistema. Contiene:
- `RUBRICA_ITEMS_UPAO` — los 33 ítems de evaluación con descripción completa
- `SECCIONES` — mapeo sección → ítems de rúbrica asignados
- `CROSS_DEPS` — grafo de dependencias cruzadas entre secciones
- `CROSS_QUERIES` — queries semánticas específicas para cada par de secciones relacionadas
- `SECTION_QUERIES` — queries RAG semánticas por sección
- `SCORE_TABLE` — tabla de conversión puntaje bruto → nota vigesimal (0-20)

**`backend/agents/herramientas.py`**
Fábrica de las 5 herramientas atómicas del Director. El contexto RAG viaja en
closures — el Director no gestiona fragmentos de PDF, solo recibe resúmenes estructurados.

**`backend/rag/tesis_store.py`**
Gestiona dos operaciones principales:
- `build_tesis_store(sections)` — indexa el proyecto del estudiante en ChromaDB efímero
- `query_context` / `query_cross_context` — recuperación semántica principal y cruzada

**`backend/utils.py`**
Utilidades transversales:
- `run_agent_silently` — ejecuta `agent.run()` suprimiendo stdout/stderr
- `extract_json` — extrae JSON válido de respuestas LLM (maneja markdown, texto plano)
- `call_with_backoff` — reintentos con backoff exponencial para absorber rate limits
- `use_groq_key` — context manager que inyecta la clave API correcta por agente

---

## 5. Instalación

### Requisitos previos

- Python 3.10 o superior
- Cuenta en [Groq](https://console.groq.com) (gratuita) para obtener API keys
- ~500 MB de espacio (modelo de embeddings MiniLM-L6-v2 se descarga automáticamente)

### Pasos

```bash
# 1. Clonar o descomprimir el proyecto
cd mentoria_swarms

# 2. Crear entorno virtual
python -m venv .venv

# 3. Activar entorno virtual
# Windows:
.venv\Scripts\activate
# Linux / macOS:
source .venv/bin/activate

# 4. Instalar dependencias
pip install -r requirements.txt
```

> **Nota:** La primera ejecución descarga el modelo de embeddings (~80 MB desde
> HuggingFace). Las ejecuciones siguientes lo leen desde caché local.

---

## 6. Configuración

Crea o edita el archivo `.env` en la raíz del proyecto:

```env
# ── Claves Groq ────────────────────────────────────────────────────────────────
# Opción A: una clave única para todos los agentes
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx

# Opción B: clave diferente por agente (recomendado para evitar rate limits)
GROQ_KEY_DIRECTOR=gsk_xxxxxxxxxxxxxxxxxxxx
GROQ_KEY_AUDITOR=gsk_xxxxxxxxxxxxxxxxxxxx
GROQ_KEY_METODOLOGICO=gsk_xxxxxxxxxxxxxxxxxxxx
GROQ_KEY_REDACTOR=gsk_xxxxxxxxxxxxxxxxxxxx

# ── Parámetros del pipeline ────────────────────────────────────────────────────
MAX_ITERACIONES=3          # Máximo de ciclos de mejora por sección
MAX_RONDAS_DEBATE=2        # (Legacy) rondas de debate

# ── Logging ────────────────────────────────────────────────────────────────────
LITELLM_LOG=ERROR          # Silencia logs de litellm
SWARMS_VERBOSE=false       # Silencia logs de swarms
```

> **Rate limits de Groq (tier gratuito):** El sistema incluye pausas de 20 segundos
> entre llamadas a agentes (`SLEEP_BETWEEN_AGENTS`). Un análisis completo tarda
> aproximadamente 3-6 minutos por sección dependiendo del número de iteraciones
> que el Director LLM decida ejecutar.

---

## 7. Arrancar la aplicación

```bash
# Desde la carpeta mentoria_swarms/ con el entorno virtual activo:
streamlit run frontend/app.py
```

La aplicación queda disponible en `http://localhost:8501`.

### Comandos adicionales

```bash
# Verificar que todos los módulos importan correctamente (sin iniciar la UI)
python -c "from backend.agents.director import DirectorOrchestrator; print('OK')"

# Verificar configuración de claves API
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
keys = ['GROQ_API_KEY','GROQ_KEY_DIRECTOR','GROQ_KEY_AUDITOR']
for k in keys:
    v = os.getenv(k, '')
    print(f'{k}: {\"configurada\" if v else \"FALTA\"}')"

# Pre-indexar libros de la carpeta /books sin abrir la UI
python -c "
import sys; sys.path.insert(0, '.')
from backend.rag.library_store import get_library_store, precargar_libros_desde_carpeta, listar_libros
store = get_library_store()
nuevos = precargar_libros_desde_carpeta(store, [l['nombre'] for l in listar_libros(store)])
print(f'Libros indexados: {nuevos}')"
```

---

## 8. Flujo de uso

```
1. CARGAR BIBLIOTECA (una sola vez)
   Sidebar → "Indexar N libro(s) de /books"
   Los libros de metodología se vectorizan y persisten en chroma_db/

2. SUBIR PROYECTO DE TESIS
   Pantalla 1 → Subir PDF del proyecto
   El sistema extrae texto y lo segmenta en las 7 secciones automáticamente

3. SELECCIONAR SECCIÓN A EVALUAR
   Pantalla 2 → Elegir sección (Título, Planteamiento, Marco Teórico, etc.)
   Solo aparecen activas las secciones detectadas en el PDF

4. ANÁLISIS AUTOMÁTICO (3-6 min)
   Pantalla 3 → El Director orquesta la jerarquía:
   Director → Auditor → Metodólogo → Redactor → [Revisión de panel] → Veredicto

5. REVISIÓN HITL
   Pantalla 3 → El mentor revisa el texto propuesto, puede editarlo y:
   - Aprobar: texto pasa a la pantalla de resultado final
   - Re-analizar: el Director inicia una nueva iteración (hasta 3 veces)

6. RESULTADO FINAL
   Pantalla 4 → Descarga del texto aprobado en .txt o reporte completo en .json
```

---

## 9. Sistema RAG

El sistema usa **dos bases vectoriales independientes**:

### Biblioteca metodológica (persistente)

- **Ubicación:** `chroma_db/` (en disco, sobrevive reinicios)
- **Contenido:** Libros de metodología de investigación de la carpeta `books/`
- **Chunking:** 800 caracteres, 100 de overlap
- **Uso:** Fundamenta las observaciones del Auditor y el Metodólogo con teoría

### Índice de tesis (efímero)

- **Ubicación:** RAM (ChromaDB EphemeralClient, se destruye al cerrar el navegador)
- **Contenido:** El proyecto de tesis del estudiante, segmentado por secciones
- **Chunking:** 600 caracteres, 80 de overlap
- **Uso:** Recupera el contexto exacto de cada sección para los agentes

### Embeddings

Modelo local `sentence-transformers/all-MiniLM-L6-v2` (HuggingFace):
- Se ejecuta en CPU, sin costo de API
- Primera descarga: ~80 MB (se cachea automáticamente)
- Normalización L2 habilitada para mejor similitud coseno

### Dependencias cruzadas RAG

Cuando el Director analiza una sección, el sistema recupera también fragmentos de
las secciones relacionadas según el grafo de dependencias:

| Sección analizada | Secciones consultadas como contexto cruzado |
|---|---|
| Título | Planteamiento, Marco Teórico, Hipótesis, Metodología |
| Planteamiento del Problema | Título, Hipótesis y Variables |
| Marco Teórico | Título, Hipótesis y Variables |
| Hipótesis y Variables | Título, Planteamiento, Metodología |
| Marco Metodológico | Planteamiento, Hipótesis |
| Aspectos Administrativos | Planteamiento del Problema |
| Referencias Bibliográficas | Marco Teórico |

---

## 10. Rúbrica UPAO

La rúbrica oficial de 33 ítems está codificada en `backend/config.py`:

| Sección | Ítems | Criterios principales |
|---|---|---|
| Título | 1-3 | Claridad, articulación de variables/espacio/tiempo, línea de investigación |
| Planteamiento del Problema | 4-10 | Realidad problemática, antecedentes, objetivos, justificación, formulación |
| Marco Teórico | 11-17 | Antecedentes, bases teóricas, definición de términos, citas APA |
| Hipótesis y Variables | 18-21 | Relación con el problema, definición operacional, matriz de consistencia |
| Marco Metodológico | 22-27 | Tipo/método/diseño, población, muestra, instrumentos, procedimiento |
| Aspectos Administrativos | 28-31 | Cronograma, recursos, presupuesto, financiamiento |
| Referencias Bibliográficas | 32-33 | Todos los autores citados, normas APA/VANCOUVER/HARVARD |

**Escala de calificación:**

| Puntaje | Nivel | Criterio |
|---|---|---|
| 3 | Excelente | Cumple completamente el criterio |
| 2 | Bueno | Cumple mayormente, observaciones menores |
| 1 | Regular | Cumple parcialmente, requiere corrección |
| 0 | Insuficiente | No cumple, requiere reformulación |

Una sección está **aprobada** cuando todos sus ítems tienen puntaje ≥ 2.

**Conversión a nota vigesimal** (puntaje máximo = 99):

| Puntaje bruto | Nota |
|---|---|
| 96-99 | 20 |
| 91-95 | 19 |
| 86-90 | 18 |
| 81-85 | 17 |
| ... | ... |
| 0-20 | 0 |

---

## 11. Variables de entorno

| Variable | Requerida | Descripción |
|---|---|---|
| `GROQ_API_KEY` | Sí (fallback) | Clave Groq usada si no hay claves individuales |
| `GROQ_KEY_DIRECTOR` | No | Clave exclusiva para el agente Director |
| `GROQ_KEY_AUDITOR` | No | Clave exclusiva para el agente Auditor |
| `GROQ_KEY_METODOLOGICO` | No | Clave exclusiva para el agente Metodólogo |
| `GROQ_KEY_REDACTOR` | No | Clave exclusiva para el agente Redactor |
| `MAX_ITERACIONES` | No | Máximo de ciclos de mejora (default: 3) |
| `SLEEP_BETWEEN_AGENTS` | No | Pausa entre llamadas en segundos (default: 20) |
| `LITELLM_LOG` | No | Nivel de log de litellm (default: ERROR) |
| `SWARMS_VERBOSE` | No | Verbosidad de swarms (default: false) |

> **Tip para rate limits:** Si usas el tier gratuito de Groq, registra 4 cuentas
> y asigna una clave diferente a cada variable `GROQ_KEY_*`. Esto distribuye las
> llamadas entre 4 límites independientes y reduce los errores 429.

---

## Modelos utilizados

| Agente | Modelo | Justificación |
|---|---|---|
| Director | `groq/llama-3.3-70b-versatile` | Necesita capacidad de razonamiento para tool calling y orquestación |
| Auditor | `groq/llama-3.3-70b-versatile` | Evaluación objetiva requiere comprensión profunda del texto |
| Metodólogo | `groq/llama-3.3-70b-versatile` | Análisis de coherencia científica entre secciones |
| Redactor | `groq/llama-3.3-70b-versatile` | Producción de texto académico de calidad |
