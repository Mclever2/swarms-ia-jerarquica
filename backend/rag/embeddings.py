"""
Embeddings locales HuggingFace — intfloat/multilingual-e5-small.

multilingual-e5-small requiere prefijos semánticos para funcionar correctamente:
  - Queries de búsqueda  → "query: <texto>"
  - Documentos indexados → "passage: <texto>"

Implementación directa con transformers (sin sentence-transformers) para evitar
problemas de mmap en Windows y compatibilidad con sentence-transformers 3.x.
"""

import logging

import torch
from langchain_core.embeddings import Embeddings
from transformers import AutoModel, AutoTokenizer

logger = logging.getLogger(__name__)

MODELO_EMBEDDING = "intfloat/multilingual-e5-small"


def _mean_pool(last_hidden_state: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
    mask = attention_mask[..., None].bool()
    hidden = last_hidden_state.masked_fill(~mask, 0.0)
    return hidden.sum(dim=1) / attention_mask.sum(dim=1)[..., None]


class MultilingualE5Embeddings(Embeddings):
    """E5-small con prefijos query:/passage: y mean pooling."""

    def __init__(self, model_name: str = MODELO_EMBEDDING):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name)
        self.model.eval()

    BATCH_SIZE = 4

    def _encode(self, texts: list) -> list:
        all_embeddings = []
        for i in range(0, len(texts), self.BATCH_SIZE):
            chunk = texts[i : i + self.BATCH_SIZE]
            batch = self.tokenizer(
                chunk, max_length=512, padding=True, truncation=True, return_tensors="pt"
            )
            with torch.no_grad():
                outputs = self.model(**batch)
            embeddings = _mean_pool(outputs.last_hidden_state, batch["attention_mask"])
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
            all_embeddings.extend(embeddings.tolist())
        return all_embeddings

    def embed_documents(self, texts: list) -> list:
        return self._encode([f"passage: {t}" for t in texts])

    def embed_query(self, text: str) -> list:
        return self._encode([f"query: {text}"])[0]


_singleton: MultilingualE5Embeddings | None = None


def cargar_modelo_embeddings() -> MultilingualE5Embeddings:
    """
    Carga multilingual-e5-small en CPU (~117 MB).
    Singleton de proceso: múltiples llamadas devuelven la misma instancia.
    """
    global _singleton
    if _singleton is None:
        logger.info(f"Cargando modelo de embeddings: {MODELO_EMBEDDING}")
        _singleton = MultilingualE5Embeddings()
    return _singleton
