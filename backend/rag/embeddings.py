"""Carga del modelo de embeddings local HuggingFace (all-MiniLM-L6-v2)."""

import logging

from langchain_huggingface import HuggingFaceEmbeddings

logger = logging.getLogger(__name__)

MODELO_EMBEDDING = "sentence-transformers/all-MiniLM-L6-v2"


def cargar_modelo_embeddings() -> HuggingFaceEmbeddings:
    """
    Carga el modelo de embeddings HuggingFace en CPU.

    La primera ejecución descarga ~80 MB del modelo.
    Las siguientes usan la caché local de sentence-transformers.

    NOTA: Llamar con @st.cache_resource en Streamlit para no recargar en cada rerun.
    """
    logger.info(f"Cargando modelo de embeddings: {MODELO_EMBEDDING}")
    return HuggingFaceEmbeddings(
        model_name=MODELO_EMBEDDING,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
