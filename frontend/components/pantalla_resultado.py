"""
Pantalla 4: Resultado final aprobado por el mentor.
Muestra el texto definitivo y permite descargarlo.
"""
from __future__ import annotations
import json
from datetime import datetime

import streamlit as st

from backend.config import SECCIONES
from frontend import session_manager as sm


def render():
    st.title("🏆 Resultado Final Aprobado")
    st.success("El mentor ha aprobado el texto mejorado.")

    resultado   = sm.get("resultado") or {}
    seccion_key = sm.get("seccion_activa") or "?"
    info        = SECCIONES.get(seccion_key, {})
    nota        = resultado.get("nota_vigesimal", 0)
    aprobado    = resultado.get("aprobado", False)
    texto_final = resultado.get("texto_final_aprobado") or resultado.get("texto_mejorado", "")

    # ── Encabezado ────────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Sección", info.get("label", seccion_key))
    with col2:
        st.metric("Nota Final", f"{nota}/20")
    with col3:
        st.metric("Estado UPAO", "✅ Aprobado" if aprobado else "📝 Observado")

    st.divider()

    # ── Texto final ───────────────────────────────────────────────────────────
    st.subheader("📄 Texto Final")
    st.markdown(texto_final or "_Sin texto producido_")

    # ── Descargas ─────────────────────────────────────────────────────────────
    st.divider()
    st.subheader("⬇️ Descargar")
    col_txt, col_json = st.columns(2)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    with col_txt:
        st.download_button(
            "📝 Texto mejorado (.txt)",
            data=texto_final.encode("utf-8"),
            file_name=f"mentoria_{seccion_key}_{timestamp}.txt",
            mime="text/plain",
            use_container_width=True,
        )

    with col_json:
        reporte = resultado.get("reporte_auditor")
        export = {
            "seccion": seccion_key,
            "nota_vigesimal": nota,
            "aprobado": aprobado,
            "puntaje_total": reporte.puntaje_total if reporte else 0,
            "texto_final": texto_final,
            "veredicto_director": resultado.get("veredicto_director", ""),
            "timestamp": timestamp,
        }
        st.download_button(
            "📊 Informe completo (.json)",
            data=json.dumps(export, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name=f"informe_{seccion_key}_{timestamp}.json",
            mime="application/json",
            use_container_width=True,
        )

    st.divider()

    # ── Historial de sesión ───────────────────────────────────────────────────
    historial = sm.get("historial_sesion") or []
    historial.append({"seccion": info.get("label", seccion_key), "nota": nota})
    sm.set("historial_sesion", historial)

    if len(historial) > 1:
        st.subheader("📈 Historial de esta sesión")
        for entry in historial:
            st.markdown(f"• **{entry['seccion']}** — Nota: {entry['nota']}/20")

    if st.button("🔍 Evaluar otra sección", type="primary"):
        sm.set("resultado", None)
        sm.ir_a("seleccion")
