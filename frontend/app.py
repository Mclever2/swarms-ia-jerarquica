"""
Router principal de Streamlit.
Gestiona la navegación entre pantallas y delega el render a los componentes.
"""
from __future__ import annotations
import sys
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Cargar .env ANTES de cualquier import de backend para que los módulos
# capturen las variables correctas al ejecutar su código a nivel de módulo.
# override=True garantiza que .env sobreescribe variables del sistema.
_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env", override=True)

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ── Silenciar ANTES de que Streamlit inicie su file-watcher ──────────────────
# El watcher escanea transformers.__path__ y genera cientos de mensajes
# de modelos de visión (yolos, vitmatte, zoedepth...) si no se deshabilita.
os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"   # no setdefault — forzar
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")

import streamlit as st

# ── Suprimir loggers antes de cualquier import de backend ────────────────────
os.environ.setdefault("LITELLM_LOG", "ERROR")
os.environ.setdefault("SWARMS_VERBOSE", "false")
for _n in ("LiteLLM", "litellm", "swarms", "httpx", "httpcore", "openai", "urllib3"):
    logging.getLogger(_n).setLevel(logging.CRITICAL)

# ── Configuración de página ───────────────────────────────────────────────────
st.set_page_config(
    page_title="Mentoría Académica UPAO",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

from frontend import session_manager as sm
from frontend.resources import check_api_key
from frontend.components import sidebar
from frontend.components import (
    pantalla_upload,
    pantalla_seleccion,
    pantalla_revision,
    pantalla_resultado,
)

# ── Inicializar sesión ────────────────────────────────────────────────────────
sm.init()

# ── Sidebar (siempre visible) ─────────────────────────────────────────────────
sidebar.render()

# ── Guardia de API key ────────────────────────────────────────────────────────
if not check_api_key():
    st.error(
        "⚠️ **No se encontró la clave de API de OpenAI.**\n\n"
        "Configura `OPENAI_API_KEY` en el archivo `.env` y reinicia la aplicación."
    )
    st.stop()

# ── Router principal ──────────────────────────────────────────────────────────
pantalla = sm.get("pantalla")

_ROUTES = {
    "upload":     pantalla_upload.render,
    "seleccion":  pantalla_seleccion.render,
    "procesando": pantalla_revision.render,
    "revision":   pantalla_revision.render,
    "resultado":  pantalla_resultado.render,
}

render_fn = _ROUTES.get(pantalla)
if render_fn:
    render_fn()
else:
    st.error(f"Pantalla desconocida: '{pantalla}'")
    sm.ir_a("upload")
