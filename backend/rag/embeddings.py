"""
Embeddings locales HuggingFace — intfloat/multilingual-e5-small.

multilingual-e5-small requiere prefijos semánticos para funcionar correctamente:
  - Queries de búsqueda  → "query: <texto>"
  - Documentos indexados → "passage: <texto>"

MultilingualE5Embeddings sobreescribe embed_query/embed_documents para inyectarlos
automáticamente, de modo que ChromaDB los recibe ya prefijados sin cambios en el resto del código.
"""

import logging

from langchain_huggingface import HuggingFaceEmbeddings

logger = logging.getLogger(__name__)

MODELO_EMBEDDING = "intfloat/multilingual-e5-small"


class MultilingualE5Embeddings(HuggingFaceEmbeddings):
    """HuggingFaceEmbeddings con prefijos query:/passage: para e5-small."""

    def embed_documents(self, texts: list) -> list:
        prefixed = [f"passage: {t}" for t in texts]
        return super().embed_documents(prefixed)

    def embed_query(self, text: str) -> list:
        return super().embed_query(f"query: {text}")


def cargar_modelo_embeddings() -> MultilingualE5Embeddings:
    """
    Carga multilingual-e5-small en CPU (~117 MB en la primera descarga).
    Las siguientes ejecuciones usan la caché local de sentence-transformers.

    NOTA: Llamar con @st.cache_resource en Streamlit para no recargar en cada rerun.
    """
    logger.info(f"Cargando modelo de embeddings: {MODELO_EMBEDDING}")
    return MultilingualE5Embeddings(
        model_name=MODELO_EMBEDDING,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
