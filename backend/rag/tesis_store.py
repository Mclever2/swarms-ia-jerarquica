"""
ChromaDB efímero para el PDF del estudiante.

Ciclo de vida: se crea por sesión y se destruye al cerrar el navegador.
Responsabilidad única: indexar la tesis y recuperar contexto por sección.
"""

import logging

import chromadb
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.config import SECCIONES_TESIS, CROSS_DEPS, CROSS_QUERIES, SECTION_QUERIES

logger = logging.getLogger(__name__)

CHUNK_SIZE    = 600
CHUNK_OVERLAP = 80
K_RESULTADOS  = 4


def construir_vector_store(
    texto: str,
    embeddings: HuggingFaceEmbeddings,
    collection_name: str = "tesis_upao",
) -> Chroma:
    """
    Divide el texto de la tesis en fragmentos y los indexa en ChromaDB en memoria.

    Args:
        texto:           Texto completo extraído del PDF del estudiante.
        embeddings:      Modelo de embeddings ya cargado.
        collection_name: Nombre único de la colección (evita colisiones entre PDFs).

    Returns:
        Chroma vector store listo para búsqueda de similitud.
    """
    if not texto.strip():
        raise ValueError("El texto extraído del PDF está vacío.")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", "   ", " ", ""],
    )
    documentos = splitter.create_documents(
        [texto],
        metadatas=[{"source": collection_name, "tipo": "proyecto_tesis"}],
    )
    logger.info(f"Tesis dividida en {len(documentos)} fragmentos")

    # EphemeralClient = solo en RAM, no escribe en disco
    cliente = chromadb.EphemeralClient()
    store = Chroma(
        client=cliente,
        collection_name=collection_name,
        embedding_function=embeddings,
    )
    store.add_documents(documentos)

    n = store._collection.count()
    logger.info(f"ChromaDB tesis listo: {n} fragmentos en '{collection_name}'")
    return store


def recuperar_contexto(
    vector_store: Chroma,
    seccion: str,
    k: int = K_RESULTADOS,
) -> str:
    """
    Recupera los k fragmentos más relevantes del PDF del estudiante para la sección.

    Usa la query semántica definida en SECCIONES_TESIS (config.py).
    """
    query = seccion  # fallback
    for sec in SECCIONES_TESIS:
        if sec["nombre"] == seccion:
            query = sec["query"]
            break

    logger.info(f"RAG tesis → '{seccion}' | query: '{query[:55]}…'")

    try:
        docs = vector_store.similarity_search(query, k=k)
    except Exception as exc:
        logger.error(f"Error en similarity_search tesis: {exc}")
        return f"[Error en búsqueda RAG: {exc}]"

    if not docs:
        return (
            f"No se encontró contenido relevante en el PDF para '{seccion}'.\n"
            "El estudiante puede no haber redactado aún esta sección."
        )

    fragmentos = [f"[Fragmento {i + 1}]\n{d.page_content}" for i, d in enumerate(docs)]
    resultado = "\n\n" + "\n\n---\n\n".join(fragmentos) + "\n"
    logger.info(f"RAG tesis: {len(docs)} fragmentos recuperados ({len(resultado)} chars)")
    return resultado


# ── API pública compatible con pantalla_upload / pantalla_revision ────────────

def build_tesis_store(
    sections: dict,
    embeddings: "HuggingFaceEmbeddings | None" = None,
    collection_name: str = "tesis_upao",
) -> Chroma:
    """
    Construye el vector store a partir del dict {seccion_key: texto} producido
    por split_into_sections(). Indexa cada sección con metadata de sección
    para permitir filtrado posterior.

    Si no se pasan embeddings, los carga internamente (singleton de módulo).
    """
    if embeddings is None:
        embeddings = _get_embeddings()

    textos, metadatas = [], []
    for clave, texto in sections.items():
        if texto.startswith("["):
            continue  # sección no detectada
        textos.append(texto)
        metadatas.append({"seccion": clave, "source": collection_name, "tipo": "proyecto_tesis"})

    if not textos:
        raise ValueError("El PDF no contiene secciones detectables. Verifica el formato.")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", "   ", " ", ""],
    )
    documentos = splitter.create_documents(textos, metadatas=metadatas)
    logger.info(f"Tesis dividida en {len(documentos)} fragmentos (con metadata de sección)")

    cliente = chromadb.EphemeralClient()
    store = Chroma(
        client=cliente,
        collection_name=collection_name,
        embedding_function=embeddings,
    )
    store.add_documents(documentos)
    logger.info(f"ChromaDB tesis listo: {store._collection.count()} fragmentos")
    return store


def query_context(
    vector_store: Chroma,
    seccion_key: str,
    k: int = K_RESULTADOS,
) -> str:
    """Recupera el contexto principal de la sección indicada (alias público)."""
    return recuperar_contexto(vector_store, seccion_key, k=k)


def query_cross_context(
    vector_store: Chroma,
    seccion_key: str,
    k_por_dep: int = 2,
) -> str:
    """
    Recupera contexto cruzado de las secciones dependientes según CROSS_DEPS.
    Usa CROSS_QUERIES para queries semánticamente precisas.
    Limita a k_por_dep fragmentos por dependencia para no saturar al agente.
    """
    deps = CROSS_DEPS.get(seccion_key, [])
    if not deps:
        return ""

    partes = []
    for dep in deps:
        cross_query = CROSS_QUERIES.get((seccion_key, dep)) or SECTION_QUERIES.get(dep, dep)
        try:
            docs = vector_store.similarity_search(cross_query, k=k_por_dep)
            if docs:
                textos = "\n---\n".join(d.page_content for d in docs)
                partes.append(f"[Contexto de '{dep}']\n{textos}")
        except Exception as exc:
            logger.warning(f"query_cross_context: error en dep '{dep}': {exc}")

    resultado = "\n\n".join(partes)
    logger.info(f"Contexto cruzado para '{seccion_key}': {len(partes)} secciones, {len(resultado)} chars")
    return resultado


# ── Singleton interno de embeddings ──────────────────────────────────────────
_embeddings_cache: "HuggingFaceEmbeddings | None" = None

def _get_embeddings() -> "HuggingFaceEmbeddings":
    global _embeddings_cache
    if _embeddings_cache is None:
        from backend.rag.embeddings import cargar_modelo_embeddings
        _embeddings_cache = cargar_modelo_embeddings()
    return _embeddings_cache
