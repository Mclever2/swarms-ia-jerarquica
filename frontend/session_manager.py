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
    "pdf_hash":            None,       # md5 del PDF — evita re-vectorizar si no cambia
    "pdf_nombre":          "",
    "tesis_store":         None,       # ChromaDB ephemeral de la tesis
    "estructura_toc":      None,       # dict {nombre_seccion: n_pagina} del índice detectado
    "stats_secciones":     None,       # lista de stats por sección (de obtener_stats_secciones)
    "sections":            {},         # Dict[seccion_key, texto] — para pantalla_seleccion fallback
    "seccion_activa":      None,       # clave config de la sección (ej. "planteamiento_problema")
    "seccion_nombre_toc":  None,       # nombre original del TOC del PDF (para mostrar en UI)
    "seccion_preview":     None,       # clave provisional antes de confirmar
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


def get(key: str, default=None):
    print(f"DEBUG: session_manager.get called for key={key}", flush=True)
    if key in st.session_state:
        return st.session_state[key]
    return _DEFAULTS.get(key, default)


def set(key: str, value) -> None:
    st.session_state[key] = value


def ir_a(pantalla: str) -> None:
    """Navega a una pantalla y fuerza el rerun de Streamlit."""
    st.session_state["pantalla"] = pantalla
    st.rerun()


def reiniciar() -> None:
    """Resetea toda la sesión (mantiene la biblioteca persistente)."""
    for key, val in _DEFAULTS.items():
        st.session_state[key] = val
    st.rerun()


def reiniciar_solo_grafo() -> None:
    """Limpia resultado y estado de evaluación, conserva el PDF ya vectorizado."""
    set("resultado",           None)
    set("iteracion_hitl",      0)
    set("seccion_activa",      None)
    set("seccion_nombre_toc",  None)
    set("seccion_preview",     None)
    set("pantalla",            "seleccion")
    st.rerun()
