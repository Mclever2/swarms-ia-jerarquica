"""
Pantalla 4: Resultado final aprobado por el mentor.
Muestra el texto definitivo, métricas, análisis de consenso/disenso y permite descargarlo.
"""
from __future__ import annotations
import json
from datetime import datetime

import streamlit as st

from backend.config import SECCIONES
from frontend import session_manager as sm


def render():
    st.title("Mentoría Completada")
    st.success("El mentor aprobó el texto mejorado.")

    resultado   = sm.get("resultado") or {}
    seccion_key = sm.get("seccion_activa") or "?"
    info        = SECCIONES.get(seccion_key, {})
    nota        = resultado.get("nota_vigesimal", 0)
    aprobado    = resultado.get("aprobado", False)
    texto_final = resultado.get("texto_final_aprobado") or resultado.get("texto_mejorado", "")
    reporte     = resultado.get("reporte_auditor")

    # ── Métricas ──────────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Sección",    info.get("label", seccion_key))
    with col2:
        st.metric("Nota Final", f"{nota}/20")
    with col3:
        st.metric("Estado",     "Aprobado" if aprobado else "Observado")

    st.divider()

    # ── Texto final ───────────────────────────────────────────────────────────
    st.subheader(f"Texto Final Aprobado — {info.get('label', seccion_key)}")
    st.markdown(
        f"""<div style="background:#f0faf0;border-left:4px solid #28a745;
        padding:1.2rem 1.5rem;border-radius:6px;line-height:1.8;font-size:0.96rem;">
        {(texto_final or '_Sin texto producido_').replace(chr(10), '<br>')}
        </div>""",
        unsafe_allow_html=True,
    )
    st.code(texto_final or "", language=None)
    st.caption("Usa el ícono de copia para exportar el texto aprobado.")

    if "[COMPLETAR:" in (texto_final or ""):
        st.warning(
            "El texto contiene marcadores `[COMPLETAR: ...]`. "
            "Estos indican secciones que **el estudiante debe completar** "
            "con información real de su investigación."
        )

    st.divider()

    # ── Resumen del proceso ───────────────────────────────────────────────────
    with st.expander("Resumen completo del proceso de mentoría"):
        col_r1, col_r2 = st.columns(2)

        with col_r1:
            st.markdown("**Feedback final del Auditor:**")
            st.info(reporte.feedback_general if reporte else "—")

            cons = resultado.get("resultado_consenso", "")
            diss = resultado.get("resultado_disenso",  "")
            if cons:
                st.markdown("**Análisis de Consenso:**")
                st.info(cons)
            if diss:
                st.markdown("**Análisis de Disenso:**")
                st.warning(diss)

        with col_r2:
            rubrica = sm.get("rubrica_dinamica")
            if reporte:
                observados = [i for i in reporte.items_evaluados if i.puntaje < 2]
                if observados:
                    if rubrica:
                        secciones_rub = rubrica.get("secciones", {})
                        item_a_sec    = {n: sec for sec, nums in secciones_rub.items() for n in nums}
                        por_sec: dict = {}
                        for item in observados:
                            sec = item_a_sec.get(item.item_numero, "General")
                            por_sec.setdefault(sec, []).append(item)
                        st.markdown(f"**Observaciones restantes ({len(observados)} ítems, no bloqueantes):**")
                        for sec_nombre, items in por_sec.items():
                            st.markdown(f"*{sec_nombre}*")
                            for item in items:
                                st.markdown(
                                    f"- Ítem **{item.item_numero:02d}** "
                                    f"(puntaje={item.puntaje}): {item.observacion}"
                                )
                    else:
                        st.markdown(f"**Observaciones restantes ({len(observados)} ítems, no bloqueantes):**")
                        for item in observados:
                            st.markdown(
                                f"- Ítem **{item.item_numero:02d}** "
                                f"(puntaje={item.puntaje}): {item.observacion}"
                            )
                else:
                    tipo = "la rúbrica personalizada" if rubrica else "la rúbrica UPAO"
                    st.success(f"El texto cumple todos los ítems evaluados de {tipo}.")

        st.divider()
        st.markdown("**Log de la jerarquía:**")
        st.caption(resultado.get("log_debate", "—"))
        st.caption(
            "Las métricas de coherencia multiagente (TF-IDF Cosine, ROUGE-L, Acuerdo, Mejora) "
            "se guardaron en backend/logs/ para análisis del investigador."
        )

    st.divider()

    # ── Descargas ─────────────────────────────────────────────────────────────
    st.subheader("Descargar")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    col_txt, col_json = st.columns(2)

    with col_txt:
        st.download_button(
            "Texto mejorado (.txt)",
            data=(texto_final or "").encode("utf-8"),
            file_name=f"mentoria_{seccion_key}_{timestamp}.txt",
            mime="text/plain",
            use_container_width=True,
        )

    with col_json:
        export = {
            "seccion":           seccion_key,
            "nota_vigesimal":    nota,
            "aprobado":          aprobado,
            "puntaje_total":     reporte.puntaje_total if reporte else 0,
            "texto_final":       texto_final,
            "veredicto_director":resultado.get("veredicto_director", ""),
            "resultado_consenso":resultado.get("resultado_consenso", ""),
            "resultado_disenso": resultado.get("resultado_disenso",  ""),
            "timestamp":         timestamp,
        }
        st.download_button(
            "Informe completo (.json)",
            data=json.dumps(export, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name=f"informe_{seccion_key}_{timestamp}.json",
            mime="application/json",
            use_container_width=True,
        )

    st.divider()

    # ── Historial y botones ───────────────────────────────────────────────────
    historial = sm.get("historial_sesion") or []
    historial.append({"seccion": info.get("label", seccion_key), "nota": nota})
    sm.set("historial_sesion", historial)

    if len(historial) > 1:
        st.subheader("Historial de esta sesión")
        for entry in historial:
            st.markdown(f"- **{entry['seccion']}** — Nota: {entry['nota']}/20")

    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("Evaluar otra sección (mismo PDF)", use_container_width=True):
            sm.set("resultado",       None)
            sm.set("seccion_activa",  None)
            sm.set("seccion_preview", None)
            sm.ir_a("seleccion")
    with col_b2:
        if st.button("Nueva evaluación (nuevo PDF)", type="primary", use_container_width=True):
            sm.reiniciar()
