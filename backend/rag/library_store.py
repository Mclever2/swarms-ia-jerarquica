"""
ChromaDB persistente para la biblioteca de libros de metodología.

Ciclo de vida: persiste en disco entre sesiones y reinicios del servidor.
Responsabilidad única: gestionar los libros de referencia teórica.
"""

import os
import logging
import re
from typing import List

import chromadb
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.config import LIBRARY_CHROMA_PATH, BOOKS_PRELOAD_DIR, SECCIONES_TESIS
from .extractor import extraer_texto_pdf

logger = logging.getLogger(__name__)

_COLLECTION_NAME = "biblioteca_metodologia_e5"  # sufijo _e5: evita mezcla con vectores del modelo anterior
_CHUNK_LIBRO     = 800
_OVERLAP_LIBRO   = 100
_K_LIBROS        = 3

# Detecta chunks que son principalmente índice/TOC de libros
_RE_LINEA_INDICE = re.compile(r'\.{4,}\s*\d{1,4}\s*$')

def _es_chunk_indice(texto: str) -> bool:
    lineas = [l for l in texto.split('\n') if l.strip()]
    if not lineas:
        return False
    matches = sum(1 for l in lineas if _RE_LINEA_INDICE.search(l.strip()))
    return matches / len(lineas) >= 0.35


# ── Carga / creación ──────────────────────────────────────────────────────────

def cargar_o_crear_biblioteca(embeddings: HuggingFaceEmbeddings) -> Chroma:
    """
    Carga la biblioteca persistente existente o crea una nueva vacía.
    PersistentClient → los datos se guardan en LIBRARY_CHROMA_PATH (disco).

    Llamar con @st.cache_resource para compartir la instancia entre reruns.
    """
    os.makedirs(LIBRARY_CHROMA_PATH, exist_ok=True)
    cliente = chromadb.PersistentClient(path=LIBRARY_CHROMA_PATH)
    store = Chroma(
        client=cliente,
        collection_name=_COLLECTION_NAME,
        embedding_function=embeddings,
    )
    n = store._collection.count()
    logger.info(f"Biblioteca cargada: {n} fragmentos en '{LIBRARY_CHROMA_PATH}'")
    return store


# ── CRUD ──────────────────────────────────────────────────────────────────────

def agregar_libro(
    vs_libros: Chroma,
    pdf_bytes: bytes,
    nombre_libro: str,
) -> int:
    """
    Vectoriza un PDF y lo agrega a la biblioteca persistente.

    Returns:
        Número de fragmentos indexados.
    """
    texto = extraer_texto_pdf(pdf_bytes)
    if not texto.strip():
        raise ValueError(f"El PDF '{nombre_libro}' está vacío o no tiene texto seleccionable.")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=_CHUNK_LIBRO,
        chunk_overlap=_OVERLAP_LIBRO,
        separators=["\n\n", "\n", ". ", "   ", " ", ""],
    )
    docs = splitter.create_documents(
        [texto],
        metadatas=[{"fuente": nombre_libro, "tipo": "libro_metodologia"}],
    )
    antes = len(docs)
    docs = [d for d in docs if not _es_chunk_indice(d.page_content)]
    logger.info(
        f"Libro '{nombre_libro}': {antes} fragmentos → {len(docs)} útiles "
        f"({antes - len(docs)} chunks de índice/TOC filtrados)"
    )
    vs_libros.add_documents(docs)
    return len(docs)


def listar_libros(vs_libros: Chroma) -> List[dict]:
    """
    Lista los libros únicos con su conteo de fragmentos.

    Returns:
        Lista de dicts: [{"nombre": str, "fragmentos": int}, ...]
    """
    try:
        resultado = vs_libros._collection.get(include=["metadatas"])
        conteo: dict = {}
        for meta in (resultado.get("metadatas") or []):
            if meta and "fuente" in meta:
                nombre = meta["fuente"]
                conteo[nombre] = conteo.get(nombre, 0) + 1
        return [{"nombre": k, "fragmentos": v} for k, v in sorted(conteo.items())]
    except Exception as exc:
        logger.warning(f"Error listando libros: {exc}")
        return []


def eliminar_libro(vs_libros: Chroma, nombre_libro: str) -> int:
    """
    Elimina todos los fragmentos de un libro.

    Returns:
        Número de fragmentos eliminados.
    """
    try:
        col = vs_libros._collection
        res = col.get(where={"fuente": nombre_libro}, include=["metadatas"])
        ids = res.get("ids", [])
        if ids:
            col.delete(ids=ids)
            logger.info(f"Eliminado '{nombre_libro}': {len(ids)} fragmentos")
        return len(ids)
    except Exception as exc:
        logger.error(f"Error eliminando '{nombre_libro}': {exc}")
        return 0


# ── Pre-carga desde carpeta ./books/ ─────────────────────────────────────────

def precargar_libros_desde_carpeta(
    vs_libros: Chroma,
    libros_ya_cargados: List[str],
) -> List[str]:
    """
    Lee todos los PDFs de BOOKS_PRELOAD_DIR e indexa los que no estén ya cargados.
    Evita duplicados comparando con la lista de libros existentes.

    Returns:
        Nombres de libros recién indexados.
    """
    if not os.path.isdir(BOOKS_PRELOAD_DIR):
        os.makedirs(BOOKS_PRELOAD_DIR, exist_ok=True)
        return []

    nuevos = []
    for archivo in sorted(os.listdir(BOOKS_PRELOAD_DIR)):
        if not archivo.lower().endswith(".pdf"):
            continue
        nombre = os.path.splitext(archivo)[0]
        if nombre in libros_ya_cargados:
            logger.info(f"Libro '{nombre}' ya indexado, omitiendo.")
            continue
        ruta = os.path.join(BOOKS_PRELOAD_DIR, archivo)
        with open(ruta, "rb") as f:
            pdf_bytes = f.read()
        try:
            n = agregar_libro(vs_libros, pdf_bytes, nombre)
            nuevos.append(nombre)
            logger.info(f"Pre-cargado: '{nombre}' ({n} fragmentos)")
        except Exception as exc:
            logger.warning(f"No se pudo pre-cargar '{nombre}': {exc}")
    return nuevos


# ── Recuperación de contexto teórico ─────────────────────────────────────────

def recuperar_contexto_teorico(
    vs_libros: Chroma,
    seccion: str,
    k: int = _K_LIBROS,
) -> str:
    """
    Recupera fragmentos teóricos relevantes de la biblioteca para una sección.
    Retorna "" si la biblioteca está vacía (el sistema funciona sin libros).
    """
    try:
        n_total = vs_libros._collection.count()
        if n_total == 0:
            return ""

        query_base = seccion
        for sec in SECCIONES_TESIS:
            if sec["nombre"] == seccion:
                query_base = sec["query"]
                break
        query = f"metodología investigación {query_base}"

        docs = vs_libros.similarity_search(query, k=min(k, n_total))
        if not docs:
            return ""

        partes = [
            f"[Fuente: {d.metadata.get('fuente', 'Fuente desconocida')}]\n{d.page_content}"
            for d in docs
        ]
        resultado = "\n\n---\n\n".join(partes)
        logger.info(f"Biblioteca: {len(docs)} fragmentos para '{seccion}'")
        return resultado

    except Exception as exc:
        logger.warning(f"Error recuperando contexto teórico: {exc}")
        return ""


# ── Función de conveniencia para resources.py ─────────────────────────────────

def get_library_store() -> Chroma:
    """
    Carga (o crea) la biblioteca persistente usando el modelo de embeddings interno.
    Alias diseñado para ser llamado desde frontend/resources.py con @st.cache_resource.
    """
    from backend.rag.embeddings import cargar_modelo_embeddings
    embeddings = cargar_modelo_embeddings()
    return cargar_o_crear_biblioteca(embeddings)
