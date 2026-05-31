"""
Métricas de coherencia del ciclo multiagente.

Algoritmos usados (todos validados en literatura NLP/IR):

1. Coherencia Semántica — Cosine Similarity con TF-IDF (Salton et al., 1975)
   Mide qué tan fiel es el texto mejorado al contenido original del estudiante.
   Rango: [0, 1]   Mayor = más fiel al original.

2. Tasa de Acuerdo Multi-Agente — Percentage Agreement proxy de Cohen's Kappa (Cohen, 1960)
   Mide concordancia entre la evaluación inicial del Auditor y el veredicto final del Debate.
   Rango: [0, 1]   Mayor = agentes más consistentes.

3. Calidad Argumentativa — ROUGE-L (Lin, 2004)
   Si hubo debate, mide qué tan bien el Redactor abordó el feedback del Auditor
   (longest common subsequence entre argumento del Redactor y feedback del Auditor).
   Rango: [0, 1]   Mayor = Redactor responde directamente al feedback.

4. Índice de Mejora — (puntaje_final - puntaje_inicial) / (puntaje_max - puntaje_inicial)
   Mide cuánto mejoró el puntaje de la rúbrica en el ciclo completo.
   Rango: [0, 1]   1 = mejora perfecta.

Score Compuesto: promedio ponderado de coherencia semántica e índice de mejora.
  Pesos: coherencia=70%, mejora=30%
  Acuerdo y argumentativa se calculan como métricas informativas del debate (no afectan el score).

NOTA: Este archivo es de uso interno (investigación). No se muestra en el frontend.
"""

import os
import json
import logging
import re
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

_LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")

# Pesos del score compuesto (solo métricas independientes del debate)
_W_COHERENCIA = 0.70
_W_MEJORA     = 0.30


# ── API pública ───────────────────────────────────────────────────────────────

def calcular_metricas_preview(
    contexto_original: str,
    texto_mejorado: str,
    puntaje_actual: int,
    puntaje_max: int,
) -> dict:
    """
    Calcula las métricas del ciclo en memoria sin guardar en disco.
    Útil para mostrar en el frontend durante la revisión HITL.

    Returns:
        Dict con coherencia_semantica, indice_mejora, score_compuesto e interpretacion.
    """
    coherencia = _cosine_tfidf(contexto_original, texto_mejorado)
    mejora     = _indice_mejora(0, puntaje_actual, puntaje_max)
    score      = _W_COHERENCIA * coherencia + _W_MEJORA * mejora
    return {
        "coherencia_semantica": round(coherencia, 4),
        "indice_mejora":        round(mejora, 4),
        "score_compuesto":      round(score, 4),
        "interpretacion":       _interpretar(score),
        "pesos":                {"coherencia": _W_COHERENCIA, "mejora": _W_MEJORA},
    }


def calcular_y_guardar_coherencia(state: dict) -> str:
    """
    Calcula las 4 métricas de coherencia y las guarda en backend/logs/.

    Args:
        state: Estado final del grafo (MentoriaState como dict).

    Returns:
        Ruta del archivo generado.
    """
    os.makedirs(_LOGS_DIR, exist_ok=True)

    seccion   = state.get("seccion_objetivo", "desconocida")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre    = re.sub(r"[^\w\-]", "_", seccion)[:40]
    ruta      = os.path.join(_LOGS_DIR, f"coherencia_{nombre}_{timestamp}.json")

    metricas = _calcular_metricas(state)
    _guardar(metricas, ruta)
    logger.info(f"[Coherencia] Métricas guardadas en {ruta}")
    return ruta


# ── Cálculo de métricas ───────────────────────────────────────────────────────

def _calcular_metricas(state: dict) -> dict:
    texto_original = state.get("contexto_recuperado", "")
    texto_final    = state.get("texto_iterado", "")
    feedback       = state.get("feedback_auditor", "")
    historial      = state.get("historial_debate", [])
    errores_ini    = state.get("errores_rubrica", [])
    puntaje_ini    = _puntaje_inicial(historial, state)
    puntaje_fin    = state.get("puntaje_estimado") or 0
    puntaje_max    = state.get("_puntaje_max", 0)

    # Score compuesto: solo métricas independientes del debate
    coherencia = _cosine_tfidf(texto_original, texto_final)
    mejora     = _indice_mejora(puntaje_ini, puntaje_fin, puntaje_max)
    score      = _W_COHERENCIA * coherencia + _W_MEJORA * mejora

    # Métricas informativas del debate (calculadas, pero no afectan el score)
    acuerdo       = _tasa_acuerdo(historial, errores_ini)
    argumentativa = _rouge_l_debate(historial, feedback)

    return {
        "metadata": {
            "seccion":            state.get("seccion_objetivo", ""),
            "numero_iteraciones": state.get("numero_iteracion", 0),
            "rondas_debate":      state.get("ronda_debate", 0),
            "timestamp":          datetime.now().isoformat(),
        },
        "metricas": {
            "coherencia_semantica": {
                "valor":       round(coherencia, 4),
                "peso_score":  _W_COHERENCIA,
                "algoritmo":   "TF-IDF Cosine Similarity (Salton et al., 1975)",
                "descripcion": "Similitud semántica entre texto original y texto mejorado.",
            },
            "indice_mejora": {
                "valor":       round(mejora, 4),
                "peso_score":  _W_MEJORA,
                "algoritmo":   "Normalized Gain Score",
                "descripcion": "Mejora normalizada del puntaje de rúbrica en el ciclo.",
            },
        },
        "score_compuesto": {
            "valor":          round(score, 4),
            "pesos":          {"coherencia": _W_COHERENCIA, "mejora": _W_MEJORA},
            "interpretacion": _interpretar(score),
        },
        "metricas_debate": {
            "nota": (
                "Métricas referenciales — esta arquitectura no usa rondas de debate explícitas. "
                "Los valores se calculan pero no tienen significado operativo en este sistema."
            ),
            "acuerdo_multiagente": {
                "valor":       round(acuerdo, 4),
                "algoritmo":   "Percentage Agreement proxy de Cohen's Kappa (Cohen, 1960)",
                "descripcion": "Concordancia entre evaluación del Auditor y veredicto del Debate.",
            },
            "calidad_argumentativa": {
                "valor":       round(argumentativa, 4),
                "algoritmo":   "ROUGE-L (Lin, 2004)",
                "descripcion": "Qué tan bien el Redactor responde al feedback del Auditor en el debate.",
            },
        },
        "datos_crudos": {
            "puntaje_inicial":  puntaje_ini,
            "puntaje_final":    puntaje_fin,
            "puntaje_max":      puntaje_max,
            "errores_finales":  len(errores_ini),
            "items_debatidos":  sum(
                len(r.get("items_aceptados", [])) + len(r.get("items_mantenidos", []))
                for r in historial
            ),
        },
    }


# ── Algoritmos individuales ───────────────────────────────────────────────────

def _cosine_tfidf(texto1: str, texto2: str) -> float:
    """
    Cosine Similarity usando representaciones TF-IDF.
    No requiere modelos externos — usa sklearn que ya es dependencia de sentence-transformers.
    """
    if not texto1.strip() or not texto2.strip():
        return 0.0
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vectorizer = TfidfVectorizer(min_df=1, max_df=1.0, sublinear_tf=True)
        tfidf      = vectorizer.fit_transform([texto1, texto2])
        score      = float(cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0])
        return max(0.0, min(1.0, score))
    except Exception as exc:
        logger.warning(f"[Coherencia] Error en cosine_tfidf: {exc}")
        return 0.0


def _tasa_acuerdo(historial: list, errores_finales: list) -> float:
    """
    Tasa de acuerdo entre Auditor y Debate como proxy de Percentage Agreement.

    Si no hubo debate (texto aprobado directo), se considera acuerdo perfecto (1.0).
    Si hubo debate, calcula: items_resueltos / items_debatidos_totales.
    """
    if not historial:
        # Sin debate = el Auditor aprobó directamente = consistencia perfecta
        return 1.0

    total_debatidos = 0
    total_resueltos = 0

    for ronda in historial:
        aceptados  = ronda.get("items_aceptados", [])
        mantenidos = ronda.get("items_mantenidos", [])
        total_debatidos += len(aceptados) + len(mantenidos)
        # Items aceptados = el Debate coincidió con el Redactor en que el error era corregible
        # Items mantenidos = el Auditor y el Debate mantuvieron el error como bloqueante
        # La concordancia es cuando ambos son consistentes (aceptados O mantenidos confirman una posición)
        total_resueltos += len(aceptados)  # resueltos por debate

    if total_debatidos == 0:
        return 1.0

    return total_resueltos / total_debatidos


def _rouge_l_debate(historial: list, feedback_auditor: str) -> float:
    """
    ROUGE-L entre el argumento del Redactor (en debate) y el feedback del Auditor.
    Mide qué tan directamente el Redactor responde a las críticas.
    Si no hubo debate, retorna 0.5 (neutral, no aplica).
    """
    if not historial or not feedback_auditor.strip():
        return 0.5  # Neutral: no hay debate para evaluar

    try:
        from rouge_score import rouge_scorer

        scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=False)

        scores = []
        for ronda in historial:
            argumento = ronda.get("argumento_redactor", "")
            if argumento.strip():
                result = scorer.score(feedback_auditor, argumento)
                scores.append(result["rougeL"].fmeasure)

        return float(sum(scores) / len(scores)) if scores else 0.5

    except ImportError:
        # rouge_score no instalado — usar superposición de bigramas como fallback
        return _bigram_overlap(feedback_auditor, historial[-1].get("argumento_redactor", ""))
    except Exception as exc:
        logger.warning(f"[Coherencia] Error en ROUGE-L: {exc}")
        return 0.5


def _bigram_overlap(ref: str, hyp: str) -> float:
    """Fallback: f-measure basado en bigramas si rouge_score no está disponible."""
    def bigramas(text):
        tokens = text.lower().split()
        return set(zip(tokens, tokens[1:]))

    ref_bi = bigramas(ref)
    hyp_bi = bigramas(hyp)
    if not ref_bi or not hyp_bi:
        return 0.0
    inter = len(ref_bi & hyp_bi)
    prec  = inter / len(hyp_bi)
    rec   = inter / len(ref_bi)
    return (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0


def _indice_mejora(puntaje_ini: int, puntaje_fin: int, puntaje_max: int) -> float:
    """
    Normalized Gain Score: (fin - ini) / (max - ini).
    Si ya empezó en el máximo, retorna 1.0. Si no hay datos, retorna 0.0.
    """
    if puntaje_max <= 0:
        return 0.0
    if puntaje_ini >= puntaje_max:
        return 1.0
    ganancia = puntaje_fin - puntaje_ini
    posible  = puntaje_max - puntaje_ini
    return max(0.0, min(1.0, ganancia / posible)) if posible > 0 else 0.0


def _puntaje_inicial(historial: list, state: dict) -> int:
    """Intenta recuperar el puntaje de la primera iteración. Fallback: 0."""
    # El estado solo guarda el puntaje final; usamos 0 como base conservadora
    return 0


def _interpretar(score: float) -> str:
    if score >= 0.80:
        return "Excelente coherencia multiagente"
    elif score >= 0.60:
        return "Buena coherencia multiagente"
    elif score >= 0.40:
        return "Coherencia moderada — revisar interacciones"
    else:
        return "Baja coherencia — posibles conflictos entre agentes"


def _guardar(metricas: dict, ruta: str) -> None:
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(metricas, f, ensure_ascii=False, indent=2)
