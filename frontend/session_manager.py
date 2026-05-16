"""
Gestión centralizada de st.session_state.
Provee helpers para inicializar, leer y actualizar el estado de sesión.
"""
from __future__ import annotations
import streamlit as st

# ── Claves de sesión ──────────────────────────────────────────────────────────
_DEFAULTS: dict = {
    "pantalla":            "upload",   # upload | seleccion | procesando | revision | resultado
    "pdf_bytes":           None,
    "pdf_nombre":          "",
    "tesis_store":         None,       # ChromaDB ephemeral de la tesis
    "sections":            {},         # Dict[seccion_key, texto]
    "seccion_activa":      None,       # seccion_key seleccionada
    "seccion_preview":     None,       # seccion_key seleccionada provisionalmente (antes de confirmar)
    "resultado":           None,       # Dict retornado por DirectorOrchestrator.run()
    "texto_editado":       "",         # texto que el mentor puede modificar en HITL
    "iteracion_hitl":      0,          # cuántas veces el mentor rechazó
    "historial_sesion":    [],         # lista de resultados anteriores
    "rubrica_dinamica":    None,       # dict de rubric_parser (None = usa UPAO)
    "rubrica_hash":        None,       # hash del PDF de rúbrica (detectar re-subida)
    "rubrica_nombre":      None,       # nombre del archivo de rúbrica
    "ctx_rag_actual":      "",         # contexto RAG de la última evaluación (para métricas)
}


def init():
    """Inicializa todas las claves de sesión con sus valores por defecto."""
    for key, val in _DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = val


def get(key: str):
    return st.session_state.get(key, _DEFAULTS.get(key))


def set(key: str, value) -> None:
    st.session_state[key] = value


def ir_a(pantalla: str) -> None:
    """Navega a una pantalla y fuerza el rerun de Streamlit."""
    st.session_state["pantalla"] = pantalla
    st.rerun()


def reiniciar() -> None:
    """Resetea toda la sesión (mantiene la biblioteca)."""
    for key, val in _DEFAULTS.items():
        st.session_state[key] = val
    st.rerun()
