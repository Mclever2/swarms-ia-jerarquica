"""
Pantalla 1: Carga del PDF de tesis y rúbrica opcional.

Estilo visual idéntico al proyecto langgraph:
- st.status() con pasos expandidos durante la vectorización
- Muestra estructura real del TOC detectado y stats por sección
- Evita re-vectorizar si el PDF no cambió (comparación por hash MD5)
"""
from __future__ import annotations
import hashlib

import streamlit as st

from backend.rag import (
    extraer_contenido_sin_indice,
    construir_vector_store,
    obtener_stats_secciones,
)
from backend.rag.extractor import split_into_sections
from backend.rag.rubric_parser import parse_rubrica_pdf
from frontend import session_manager as sm


def render() -> None:
    st.title("Sistema de Mentoría Académica Multiagente")

    st.markdown("""
**¿Cómo funciona este sistema?**
1. **Sube el PDF** de tu proyecto de tesis borrador
2. *(Opcional)* **Sube tu rúbrica de evaluación** — si no la subes, se usa la rúbrica UPAO por defecto
3. **El sistema vectoriza** el documento con embeddings locales (sin enviar datos al exterior)
4. **Elige una sección** y el sistema recupera solo ese fragmento *(anti-token-burn)*
5. **Red multiagente jerárquica** Director → Auditor ↔ Metodólogo mejora el texto iterativamente
6. **Tú revisas y apruebas** la versión final como mentor
""")

    st.divider()

    # ── Paso 1: PDF de tesis ──────────────────────────────────────────────────
    st.subheader("Paso 1 — Carga el PDF de tu proyecto de tesis")

    archivo_pdf = st.file_uploader(
        label="Sube el borrador del proyecto de tesis (PDF)",
        type=["pdf"],
        key="uploader_tesis",
        help="El PDF se procesa localmente. Los embeddings se generan en tu máquina.",
    )

    if archivo_pdf is not None:
        pdf_bytes  = archivo_pdf.getvalue()
        nuevo_hash = hashlib.md5(pdf_bytes).hexdigest()

        if sm.get("pdf_hash") == nuevo_hash:
            st.success(f"PDF **'{sm.get('pdf_nombre')}'** ya está vectorizado.")
            _mostrar_stats_secciones()
        else:
            col_info, col_btn = st.columns([3, 1])
            with col_info:
                st.info(
                    f"**{archivo_pdf.name}** ({len(pdf_bytes) / 1024:.1f} KB)\n\n"
                    "Primera vectorización descarga el modelo multilingual-e5-small (~117 MB). "
                    "Las siguientes son instantáneas (modelo en caché)."
                )
            with col_btn:
                if st.button("Vectorizar PDF", type="primary", use_container_width=True):
                    _vectorizar_tesis(pdf_bytes, archivo_pdf.name, nuevo_hash)
                    return

    # ── Paso 2: Rúbrica opcional ──────────────────────────────────────────────
    if sm.get("pdf_hash"):
        st.divider()
        st.subheader("Paso 2 — Rúbrica de evaluación (opcional)")

        col_rubrica, col_info_rubrica = st.columns([1, 2])

        with col_info_rubrica:
            rubrica = sm.get("rubrica_dinamica")
            if rubrica:
                st.success(
                    f"Rúbrica cargada: **{sm.get('rubrica_nombre')}**  \n"
                    f"{rubrica['total_items']} ítems · "
                    f"{len(rubrica['secciones'])} secciones · "
                    f"puntaje máximo: {rubrica['puntaje_maximo']} pts"
                )
                if st.button("Quitar rúbrica (usar UPAO por defecto)", type="secondary"):
                    sm.set("rubrica_dinamica", None)
                    sm.set("rubrica_hash",     None)
                    sm.set("rubrica_nombre",   None)
                    st.rerun()
            else:
                st.info(
                    "Sin rúbrica subida — se usará la **rúbrica oficial UPAO** (33 ítems).  \n"
                    "Puedes subir la rúbrica de tu jurado evaluador para una evaluación personalizada."
                )

        with col_rubrica:
            archivo_rubrica = st.file_uploader(
                label="Sube la rúbrica de evaluación (PDF)",
                type=["pdf"],
                key="uploader_rubrica",
                help="La rúbrica debe tener ítems numerados (01, 02…) con secciones visibles.",
            )

            if archivo_rubrica is not None:
                rb_bytes = archivo_rubrica.getvalue()
                rb_hash  = hashlib.md5(rb_bytes).hexdigest()

                if sm.get("rubrica_hash") != rb_hash:
                    if st.button("Cargar rúbrica", type="primary", use_container_width=True):
                        _cargar_rubrica(rb_bytes, archivo_rubrica.name, rb_hash)
                        return

        st.divider()

        if st.button("Continuar a selección de sección →", type="primary", use_container_width=True):
            sm.ir_a("seleccion")


# ── Funciones internas ────────────────────────────────────────────────────────

def _vectorizar_tesis(pdf_bytes: bytes, nombre: str, nuevo_hash: str) -> None:
    try:
        with st.status("Procesando PDF de tesis...", expanded=True) as status:
            st.write("Analizando estructura del PDF (separando índice del contenido)...")
            paginas, estructura_toc = extraer_contenido_sin_indice(pdf_bytes)

            total_chars = sum(len(t) for _, t in paginas)
            if total_chars < 100:
                raise ValueError(
                    "El PDF parece vacío o ser un escaneo sin texto seleccionable. "
                    "Asegúrate de que el PDF sea nativo (no solo imágenes)."
                )

            st.write(
                f"Texto extraído: **{total_chars:,} caracteres** en **{len(paginas)} páginas** de contenido"
            )

            if estructura_toc:
                secciones_preview = list(estructura_toc.keys())[:8]
                st.write(
                    f"Índice detectado: **{len(estructura_toc)} secciones**  \n"
                    + "  \n".join(f"- {s}" for s in secciones_preview)
                    + ("  \n- …" if len(estructura_toc) > 8 else "")
                )
                st.write("Dividiendo contenido por secciones del índice (chunking semántico)...")
            else:
                st.write("No se detectó índice formal — se aplica chunking por tamaño fijo.")

            st.write("Generando embeddings locales (multilingual-e5-small)...")

            collection_name = f"tesis_{nuevo_hash[:8]}"
            tesis_store = construir_vector_store(
                paginas, estructura_toc, collection_name=collection_name
            )

            stats  = obtener_stats_secciones(tesis_store)
            # sections dict para compatibilidad con pantalla_seleccion fallback
            raw_text = "\n\n".join(t for _, t in sorted(paginas))
            sections = split_into_sections(raw_text)

            sm.set("pdf_bytes",       pdf_bytes)
            sm.set("pdf_hash",        nuevo_hash)
            sm.set("pdf_nombre",      nombre)
            sm.set("tesis_store",     tesis_store)
            sm.set("estructura_toc",  estructura_toc)
            sm.set("stats_secciones", stats)
            sm.set("sections",        sections)
            sm.set("resultado",       None)
            sm.set("seccion_activa",  None)
            sm.set("seccion_preview", None)

            n_frags = tesis_store._collection.count()
            status.update(
                label=f"PDF vectorizado: {n_frags} fragmentos (índice excluido)",
                state="complete",
            )

        st.rerun()

    except Exception as exc:
        st.error(f"Error procesando el PDF: {exc}")


def _mostrar_stats_secciones() -> None:
    stats = sm.get("stats_secciones")
    vs    = sm.get("tesis_store")

    if not stats and vs is not None:
        stats = obtener_stats_secciones(vs)
        sm.set("stats_secciones", stats)

    if not stats:
        toc = sm.get("estructura_toc") or {}
        if toc:
            with st.expander(f"Estructura detectada ({len(toc)} secciones)"):
                for nombre_sec, pag in list(toc.items())[:30]:
                    st.markdown(f"- **{nombre_sec}** — pág. {pag}")
        return

    total_chars = sum(s["chars"] for s in stats)
    total_frags = sum(s["n_fragmentos"] for s in stats)

    with st.expander(
        f"Fragmentación: {len(stats)} secciones · "
        f"{total_frags} fragmentos · {total_chars:,} caracteres totales",
        expanded=False,
    ):
        cols = st.columns([4, 1, 1, 1])
        cols[0].markdown("**Sección**")
        cols[1].markdown("**Pág.**")
        cols[2].markdown("**Chars**")
        cols[3].markdown("**Frags**")
        st.divider()
        for s in stats:
            alerta = " ⚠️" if s["chars"] < 200 else ""
            cols = st.columns([4, 1, 1, 1])
            cols[0].markdown(f"{s['seccion']}{alerta}")
            cols[1].markdown(str(s["pagina_inicio"]))
            cols[2].markdown(f"{s['chars']:,}")
            cols[3].markdown(str(s["n_fragmentos"]))


def _cargar_rubrica(rb_bytes: bytes, nombre: str, rb_hash: str) -> None:
    with st.spinner(f"Parseando rúbrica '{nombre}'..."):
        rubrica = parse_rubrica_pdf(rb_bytes)

    if rubrica is None:
        st.error(
            "No se pudo parsear la rúbrica. Asegúrate de que el PDF tenga "
            "ítems numerados (01, 02…) y secciones en mayúsculas. "
            "Se seguirá usando la rúbrica UPAO por defecto."
        )
        return

    sm.set("rubrica_dinamica", rubrica)
    sm.set("rubrica_hash",     rb_hash)
    sm.set("rubrica_nombre",   nombre)
    st.success(
        f"Rúbrica cargada: {rubrica['total_items']} ítems en "
        f"{len(rubrica['secciones'])} secciones."
    )
    st.rerun()
