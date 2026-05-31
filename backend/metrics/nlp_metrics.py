"""
Métricas NLP del ciclo multiagente.

Implementación idéntica al evaluador del proyecto LangGraph (poc_langgraph_mentoria),
portada al sistema swarms con las adaptaciones necesarias.

Métricas calculadas:
  ROUGE-1, ROUGE-2, ROUGE-L  — rouge_score library
  BLEU                        — sacrebleu library (effective_order=True)
  Cosine Similarity           — TF-IDF + sklearn
  Cohen's Kappa               — sklearn (requiere historial de debate con ≥2 turnos)
  Gain Score (Hake)           — (final − inicial) / (máx − inicial)
  Puntaje 0-10                — max(gain, 0) × 10

Comparan el texto original analizado (contexto RAG) vs el texto sugerido
(reescritura propuesta por el pipeline).

Dependencias: rouge-score, sacrebleu, scikit-learn (todas ya en requirements.txt).
"""
from __future__ import annotations

import logging

logger = logging.getLogger("mentoria")


# ── ROUGE-1, ROUGE-2, ROUGE-L ────────────────────────────────────────────────

def calcular_rouge(texto_referencia: str, texto_generado: str) -> dict:
    """F-measure para ROUGE-1, ROUGE-2 y ROUGE-L."""
    if not texto_referencia.strip() or not texto_generado.strip():
        return {"rouge1_f": 0.0, "rouge2_f": 0.0, "rougeL_f": 0.0}
    try:
        from rouge_score import rouge_scorer
        scorer = rouge_scorer.RougeScorer(
            ["rouge1", "rouge2", "rougeL"], use_stemmer=False
        )
        s = scorer.score(texto_referencia, texto_generado)
        return {
            "rouge1_f": round(s["rouge1"].fmeasure, 4),
            "rouge2_f": round(s["rouge2"].fmeasure, 4),
            "rougeL_f": round(s["rougeL"].fmeasure, 4),
        }
    except Exception as exc:
        logger.warning(f"[NLP] ROUGE error: {exc}")
        return {"rouge1_f": 0.0, "rouge2_f": 0.0, "rougeL_f": 0.0}


# ── BLEU ─────────────────────────────────────────────────────────────────────

def calcular_bleu(texto_referencia: str, texto_generado: str) -> dict:
    """SacreBLEU sentence-level score (normalizado a [0, 1])."""
    if not texto_referencia.strip() or not texto_generado.strip():
        return {"bleu_score": 0.0}
    try:
        from sacrebleu.metrics import BLEU
        bleu = BLEU(effective_order=True)
        score = bleu.sentence_score(texto_generado, [texto_referencia])
        return {"bleu_score": round(score.score / 100.0, 4)}
    except Exception as exc:
        logger.warning(f"[NLP] BLEU error: {exc}")
        return {"bleu_score": 0.0}


# ── Cosine Similarity (TF-IDF) ────────────────────────────────────────────────

def calcular_cosine_sim(texto1: str, texto2: str) -> dict:
    """TF-IDF Cosine Similarity entre dos textos."""
    if not texto1.strip() or not texto2.strip():
        return {"similitud_coseno": 0.0}
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        vec = TfidfVectorizer()
        mat = vec.fit_transform([texto1, texto2])
        sim = cosine_similarity(mat[0:1], mat[1:2])[0][0]
        return {"similitud_coseno": round(float(sim), 4)}
    except Exception as exc:
        logger.warning(f"[NLP] Cosine sim error: {exc}")
        return {"similitud_coseno": 0.0}


# ── Cohen's Kappa ─────────────────────────────────────────────────────────────

_RAICES_ACUERDO = [
    "coincid", "correct", "valid", "acept", "confirm", "adecuad",
    "concuerd", "precis", "exact", "acertad", "pertinent",
    "suficient", "satisfactor", "complet", "coherent",
    "de acuerdo", "tiene razón", "comparto", "avalo",
    "bien planteado", "bien formulad",
]
_RAICES_DESACUERDO = [
    "discrepo", "incorrect", "error", "invalid", "rechaz", "inadecuad",
    "inconsistent", "imprecis", "incomplet", "deficient", "ausent",
    "no cumple", "falt", "carec", "insuficient", "ambigu",
]


def _clasificar_turno(texto: str) -> int:
    t = texto.lower()
    acuerdo    = sum(1 for r in _RAICES_ACUERDO    if r in t)
    desacuerdo = sum(1 for r in _RAICES_DESACUERDO if r in t)
    return 1 if acuerdo >= desacuerdo else 0


def calcular_kappa(historial_texto: list[str]) -> dict:
    """
    Cohen's Kappa sobre el historial de debate (turnos de texto).
    Turnos pares = Auditor, impares = Metodólogo.
    Requiere ≥2 turnos completos para ser calculable.
    En swarms sin debate formal, pasar lista vacía → kappa = None.
    """
    if len(historial_texto) < 2:
        return {"kappa": None, "nota_kappa": "requiere ≥2 iteraciones"}
    try:
        from sklearn.metrics import cohen_kappa_score
        turnos_a = historial_texto[0::2]
        turnos_b = historial_texto[1::2]
        n = min(len(turnos_a), len(turnos_b))
        if n < 2:
            return {"kappa": None, "nota_kappa": "requiere ≥2 rondas completas"}
        etiq_a = [_clasificar_turno(turnos_a[i]) for i in range(n)]
        etiq_b = [_clasificar_turno(turnos_b[i]) for i in range(n)]
        if len(set(etiq_a)) == 1 or len(set(etiq_b)) == 1:
            return {"kappa": None, "nota_kappa": "kappa indefinido — sin varianza"}
        kappa = cohen_kappa_score(etiq_a, etiq_b)
        return {"kappa": round(float(kappa), 4), "nota_kappa": ""}
    except Exception as exc:
        logger.warning(f"[NLP] Kappa error: {exc}")
        return {"kappa": None, "nota_kappa": str(exc)[:80]}


# ── Gain Score (Hake) ─────────────────────────────────────────────────────────

def calcular_gain_score(
    puntaje_inicial: float,
    puntaje_final: float,
    puntaje_maximo: float,
) -> dict:
    """
    Gain Score normalizado de Hake:
        gain = (final − inicial) / (máximo − inicial)
    Rango: (−∞, 1].  Negativo = regresión.  1.0 = mejora perfecta.
    """
    if puntaje_maximo <= 0:
        return {"gain_score": None}
    if puntaje_inicial >= puntaje_maximo:
        return {"gain_score": 1.0}
    if puntaje_inicial == puntaje_final:
        return {"gain_score": 0.0}
    gain = (puntaje_final - puntaje_inicial) / (puntaje_maximo - puntaje_inicial)
    return {"gain_score": round(float(gain), 4)}


# ── Puntaje 0-10 ──────────────────────────────────────────────────────────────

def calcular_puntaje_10(gain_score) -> float:
    """Escala el Gain Score al rango 0-10. Valores negativos → 0.0."""
    if gain_score is None:
        return 0.0
    return round(max(float(gain_score), 0.0) * 10.0, 1)


# ── API unificada ─────────────────────────────────────────────────────────────

def calcular_todas(
    texto_referencia: str,
    texto_generado: str,
    puntaje_inicial: float,
    puntaje_final: float,
    puntaje_maximo: float,
    historial_texto: list[str] | None = None,
) -> dict:
    """
    Calcula todas las métricas NLP en una sola llamada.

    Args:
        texto_referencia: Texto original del estudiante (contexto RAG).
        texto_generado:   Texto mejorado por el Redactor.
        puntaje_inicial:  Puntaje de rúbrica antes del pipeline (0 si no se conoce).
        puntaje_final:    Puntaje de rúbrica al final del ciclo.
        puntaje_maximo:   Puntaje máximo posible de la rúbrica.
        historial_texto:  Lista de strings con los turnos del debate (vacía en swarms).

    Returns:
        Dict con: rouge1_f, rouge2_f, rougeL_f, bleu_score, similitud_coseno,
                  kappa, gain_score, puntaje_10.
    """
    resultado: dict = {}
    resultado.update(calcular_rouge(texto_referencia, texto_generado))
    resultado.update(calcular_bleu(texto_referencia, texto_generado))
    resultado.update(calcular_cosine_sim(texto_referencia, texto_generado))
    resultado.update(calcular_kappa(historial_texto or []))
    resultado.update(calcular_gain_score(puntaje_inicial, puntaje_final, puntaje_maximo))
    resultado["puntaje_10"] = calcular_puntaje_10(resultado.get("gain_score"))
    return resultado
