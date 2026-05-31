"""
Sidebar: gestión de la biblioteca metodológica y estado del sistema.
"""
from __future__ import annotations
from pathlib import Path

import streamlit as st

from backend.rag.library_store import agregar_libro, listar_libros_ligero
from frontend.resources import get_library, check_api_key
from frontend import session_manager as sm

_BOOKS_DIR = Path(__file__).parent.parent.parent / "books"


def render():
    with st.sidebar:
        st.title("🎓 Mentoría UPAO")
        st.caption("Sistema multiagente jerárquico")
        st.divider()

        # ── Estado de API ──────────────────────────────────────────────────
        if check_api_key():
            st.success("✅ Groq API conectada")
        else:
            st.error("❌ Sin clave Groq — configure .env")

        st.divider()

        # ── Biblioteca metodológica ───────────────────────────────────────
        st.subheader("📚 Biblioteca Metodológica")
        libros_raw = listar_libros_ligero()
        libros = [l["nombre"] for l in libros_raw]

        if libros_raw:
            st.write(f"**{len(libros_raw)} libro(s) indexado(s):**")
            for libro in libros_raw:
                st.markdown(f"• {libro['nombre']} ({libro['fragmentos']} fragmentos)")
        else:
            st.info("Sin libros indexados aún.")

        uploaded_book = st.file_uploader(
            "Agregar libro PDF", type=["pdf"], key="book_uploader"
        )
        if uploaded_book:
            nombre = uploaded_book.name.replace(".pdf", "")
            with st.spinner(f"Indexando '{nombre}'..."):
                library = get_library()  # carga modelo solo cuando se necesita
                n = agregar_libro(library, uploaded_book.getvalue(), nombre)
            st.success(f"✅ {n} fragmentos indexados")
            st.rerun()

        # Indexar libros pre-cargados en /books
        pdfs_preload = list(_BOOKS_DIR.glob("*.pdf")) if _BOOKS_DIR.exists() else []
        indexados = set(libros)
        pendientes = [p for p in pdfs_preload if p.stem not in indexados]
        if pendientes:
            if st.button(f"Indexar {len(pendientes)} libro(s) de /books"):
                library = get_library()  # carga modelo solo cuando se necesita
                for p in pendientes:
                    agregar_libro(library, p.read_bytes(), p.stem)
                st.success("Indexación completada")
                st.rerun()

        st.divider()

        # ── Navegación / reinicio ──────────────────────────────────────────
        pantalla = sm.get("pantalla")
        if pantalla not in ("upload", "procesando"):
            if st.button("🔄 Nuevo análisis"):
                sm.reiniciar()

        st.caption(f"Pantalla: `{pantalla}`")
