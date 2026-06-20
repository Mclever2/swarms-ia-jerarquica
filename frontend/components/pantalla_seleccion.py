"""
Pantalla 2: Selección de sección a evaluar.

Estilo langgraph:
- Dropdown con las secciones reales del índice del PDF (si se detectó TOC)
- Fallback a las secciones SECCIONES_TESIS del config si no hay TOC
- Mapeo automático de nombre TOC → clave config para los agentes
- Configuración avanzada de iteraciones
"""
from __future__ import annotations
import re

import streamlit as st

from backend.config import SECCIONES, SECCIONES_TESIS, SECCION_ITEMS_MAP, RUBRICA_ITEMS_UPAO, _mapear_a_clave_config
from frontend import session_manager as sm


def render() -> None:
    st.title("Sistema de Mentoría Académica Multiagente")
    st.success(f"PDF cargado: **{sm.get('pdf_nombre')}**")

    rubrica = sm.get("rubrica_dinamica")
    if rubrica:
        st.info(
            f"Rúbrica activa: **{sm.get('rubrica_nombre')}** "
            f"({rubrica['total_items']} ítems)"
        )
    else:
        st.caption("Rúbrica activa: UPAO oficial (33 ítems) — puedes subir tu propia rúbrica en el paso anterior.")

    st.subheader("Paso 2 — Selecciona la sección a evaluar")

    # ── Construir opciones del dropdown ──────────────────────────────────────
    estructura_toc = sm.get("estructura_toc") or {}
    if estructura_toc:
        secciones_ord = sorted(estructura_toc.items(), key=lambda x: x[1])
        opciones      = [nombre for nombre, _ in secciones_ord]
        usando_pdf    = True
    else:
        opciones   = [s["nombre"] for s in SECCIONES_TESIS]
        usando_pdf = False

    col_form, col_config = st.columns([2, 1])

    with col_form:
        seccion_elegida = st.selectbox(
            "Sección del proyecto de tesis:",
            options=opciones,
            help=(
                "Secciones extraídas del índice de tu PDF. "
                "Al seleccionar una sección, el sistema recupera "
                "automáticamente su contenido y subsecciones."
            ) if usando_pdf else (
                "Secciones estándar UPAO. El sistema buscará los fragmentos "
                "relevantes del PDF para esta sección."
            ),
        )

        # ── Info de rúbrica aplicable ─────────────────────────────────────
        if rubrica:
            secciones_rub = rubrica.get("secciones", {})
            if secciones_rub:
                st.caption(
                    f"Rúbrica personalizada: **{rubrica['total_items']} ítems** en "
                    f"{len(secciones_rub)} secciones · "
                    f"puntaje máx: {rubrica['puntaje_maximo']} pts"
                )
        else:
            clave_config = _mapear_a_clave_config(seccion_elegida) if usando_pdf else seccion_elegida
            items = SECCION_ITEMS_MAP.get(clave_config or "", [])
            if items:
                info_sec = SECCIONES.get(clave_config, {})
                label    = info_sec.get("label", clave_config)
                st.caption(
                    f"Ítems UPAO a evaluar ({label}): "
                    f"**{', '.join(str(i) for i in items)}** "
                    f"(máx. {len(items) * 3} pts)"
                )
            else:
                st.caption(
                    "Esta sección del PDF no tiene un mapeo directo a ítems UPAO — "
                    "se evaluará con todos los criterios relevantes."
                )

        # ── Dependencias cruzadas ─────────────────────────────────────────
        if not usando_pdf:
            from backend.config import CROSS_DEPS
            deps = CROSS_DEPS.get(seccion_elegida, [])
            if deps:
                deps_labels = [SECCIONES.get(d, {}).get("label", d) for d in deps]
                st.caption(f"Contexto cruzado: {', '.join(deps_labels)}")
        else:
            st.caption(
                "Contexto: subsecciones de la sección seleccionada + "
                "secciones estructuralmente relacionadas del proyecto."
            )

    with col_config:
        with st.expander("Configuración avanzada", expanded=False):
            from backend.config import MAX_ITERACIONES
            max_iter = st.slider(
                "Iteraciones de mejora automática:",
                min_value=1,
                max_value=3,
                value=min(MAX_ITERACIONES, 2),
                help=(
                    "Ciclos Director → Auditor ↔ Metodólogo. "
                    "1 = una pasada rápida. "
                    "2–3 = el Director itera varias veces para texto más refinado (más tiempo)."
                ),
            )

    st.divider()

    # ── Tiempo estimado ───────────────────────────────────────────────────────
    t_min = max(1, max_iter * 2)
    t_max = max(2, max_iter * 5)
    st.info(
        f"{max_iter} iteración(es) · jerarquía Director→Auditor/Metodólogo · "
        f"Tiempo estimado: {t_min}–{t_max} min · "
        "Revisión final HITL (tú apruebas el texto)",
        icon="ℹ️",
    )

    if st.button("Iniciar Evaluación", type="primary", use_container_width=True):
        # Traducir nombre de sección del PDF a clave config si es posible
        if usando_pdf:
            clave_activa = _mapear_a_clave_config(seccion_elegida) or seccion_elegida
        else:
            clave_activa = seccion_elegida

        sm.set("seccion_activa",  clave_activa)
        sm.set("seccion_nombre_toc", seccion_elegida)   # nombre original del TOC para mostrar
        sm.set("iteracion_hitl",  0)
        sm.set("resultado",       None)
        sm.set("max_iter_override", max_iter)
        sm.ir_a("procesando")

    st.divider()
    if st.button("← Volver / Cargar otro PDF", type="secondary"):
        sm.ir_a("upload")


# ── Mapeo TOC → clave de config ───────────────────────────────────────────────
# (Mapeado dinámicamente desde backend.config)

