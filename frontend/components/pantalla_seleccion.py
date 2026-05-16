"""
Pantalla 2: Selección de sección a evaluar.

Muestra las 7 secciones como tarjetas seleccionables. Al elegir una,
despliega el panel de detalles con: ítems de la rúbrica con sus descripciones
completas, preview del contenido detectado y dependencias cruzadas.
El mentor confirma con "Iniciar Evaluación".
"""
from __future__ import annotations
import streamlit as st

from backend.config import SECCIONES, RUBRICA_ITEMS_UPAO, CROSS_DEPS
from frontend import session_manager as sm


def render():
    st.title("Seleccionar Sección a Evaluar")

    nombre = sm.get("pdf_nombre")
    st.markdown(f"**Proyecto:** {nombre}")

    rubrica = sm.get("rubrica_dinamica")
    if rubrica:
        st.info(
            f"Rúbrica activa: **{sm.get('rubrica_nombre')}** "
            f"({rubrica['total_items']} ítems)"
        )
    else:
        st.caption("Rúbrica activa: UPAO oficial (33 ítems)")

    sections = sm.get("sections") or {}
    st.markdown("Selecciona la sección del proyecto que deseas analizar:")
    st.divider()

    # ── Tarjetas de sección (2 columnas) ─────────────────────────────────────
    seccion_preview = sm.get("seccion_preview")
    seccion_keys    = list(SECCIONES.keys())
    cols = st.columns(2)

    for i, sec_key in enumerate(seccion_keys):
        info          = SECCIONES[sec_key]
        texto         = sections.get(sec_key, "")
        tiene_cont    = texto and not texto.startswith("[Sección")
        chars         = len(texto) if tiene_cont else 0
        n_items       = len(info["nums"])
        seleccionada  = (sec_key == seccion_preview)

        with cols[i % 2]:
            estado = "✅" if tiene_cont else "⚠️"
            selmark = " ◀" if seleccionada else ""
            label = (
                f"{estado} **{info['label']}**{selmark}  \n"
                f"Ítems {min(info['nums'])}–{max(info['nums'])} · {n_items} criterios"
                + (f" · {chars:,} chars" if tiene_cont else " · no detectada")
            )
            tipo = "primary" if seleccionada else "secondary"
            if st.button(
                label,
                key=f"btn_{sec_key}",
                use_container_width=True,
                type=tipo,
                disabled=not tiene_cont,
            ):
                sm.set("seccion_preview", sec_key)
                st.rerun()

    # ── Panel de detalle (aparece al seleccionar) ─────────────────────────────
    if seccion_preview and sections.get(seccion_preview):
        st.divider()
        _render_detalle(seccion_preview, sections, rubrica)

    st.divider()
    if st.button("Volver / Cargar otro PDF"):
        sm.set("seccion_preview", None)
        sm.ir_a("upload")


# ── Panel de detalle ──────────────────────────────────────────────────────────

def _render_detalle(sec_key: str, sections: dict, rubrica) -> None:
    info    = SECCIONES[sec_key]
    texto   = sections.get(sec_key, "")
    deps    = CROSS_DEPS.get(sec_key, [])

    st.subheader(f"Sección seleccionada: {info['label']}")

    col_items, col_preview = st.columns([1, 1])

    with col_items:
        st.markdown("**Ítems de la rúbrica a evaluar:**")
        if rubrica:
            # Rúbrica dinámica: mostrar ítems de la rúbrica cargada
            secciones_rub = rubrica.get("secciones", {})
            items_rub     = rubrica.get("items", [])
            # Intentar agrupar por sección de la rúbrica dinámica
            for sec_nombre, nums in secciones_rub.items():
                st.markdown(f"*{sec_nombre}*")
                for item in items_rub:
                    if item["numero"] in nums:
                        st.markdown(
                            f"- **{item['numero']:02d}.** {item['descripcion']}"
                        )
        else:
            # Rúbrica UPAO: mostrar ítems de la sección
            for n in info["nums"]:
                desc = RUBRICA_ITEMS_UPAO.get(n, "")
                st.markdown(f"- **{n:02d}.** {desc}")

        pts_max = rubrica.get("puntaje_maximo", 0) if rubrica else len(info["nums"]) * 3
        st.caption(f"Puntaje máximo de sección: {pts_max} pts")

        if deps:
            st.markdown("**Secciones consultadas como contexto cruzado:**")
            for dep in deps:
                dep_label = SECCIONES.get(dep, {}).get("label", dep)
                dep_ok    = sections.get(dep, "").startswith("[Sección") is False
                icon      = "✅" if dep_ok else "⚠️"
                st.markdown(f"- {icon} {dep_label}")

    with col_preview:
        st.markdown("**Contenido detectado en el PDF:**")
        preview = texto[:800].strip() if texto else ""
        if preview:
            st.text_area(
                label="preview",
                value=preview + ("…" if len(texto) > 800 else ""),
                height=280,
                disabled=True,
                label_visibility="collapsed",
            )
        else:
            st.warning("No se detectó contenido para esta sección en el PDF.")

    st.markdown(" ")
    if st.button(
        f"Iniciar Evaluación — {info['label']}",
        type="primary",
        use_container_width=True,
        key="btn_iniciar",
    ):
        sm.set("seccion_activa",  sec_key)
        sm.set("seccion_preview", None)
        sm.set("iteracion_hitl",  0)
        sm.set("resultado",       None)
        sm.ir_a("procesando")
