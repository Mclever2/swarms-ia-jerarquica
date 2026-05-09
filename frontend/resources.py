"""
Singletons cacheados con @st.cache_resource.
Evita recrear agentes y el store de biblioteca en cada rerun de Streamlit.
"""
from __future__ import annotations
import sys
import logging
import os
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ── Silenciar ANTES de cualquier import pesado ───────────────────────────────
# Evita que el file-watcher de Streamlit recorra transformers.__path__
# generando cientos de mensajes de modelos de visión (yolos, vitmatte, etc.)
os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")

import streamlit as st
from dotenv import load_dotenv

# Suprimir loggers ruidosos ANTES de importar swarms/litellm
os.environ.setdefault("LITELLM_LOG", "ERROR")
os.environ.setdefault("SWARMS_VERBOSE", "false")
for _n in ("LiteLLM", "litellm", "swarms", "httpx", "httpcore", "openai", "urllib3"):
    logging.getLogger(_n).setLevel(logging.CRITICAL)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)

load_dotenv()

from backend.agents.director import DirectorOrchestrator
from backend.rag.library_store import get_library_store


@st.cache_resource(show_spinner="Inicializando enjambre de agentes...")
def get_orchestrator() -> DirectorOrchestrator:
    """Crea el orquestador una sola vez por sesión de Streamlit."""
    return DirectorOrchestrator()


@st.cache_resource(show_spinner="Cargando biblioteca metodológica...")
def get_library():
    """Carga el store persistente de la biblioteca de libros."""
    return get_library_store()


def check_api_key() -> bool:
    """Verifica que al menos una clave de Groq esté configurada."""
    keys = ["GROQ_API_KEY", "GROQ_KEY_DIRECTOR", "GROQ_KEY_AUDITOR",
            "GROQ_KEY_METODOLOGICO", "GROQ_KEY_REDACTOR"]
    return any(os.getenv(k) for k in keys)
