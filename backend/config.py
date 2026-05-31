"""
Configuración global para Swarmsia (Arquitectura Jerárquica).
Integra las mejoras de granularidad y descripciones exactas del proyecto GraphRAG,
adaptadas a las macro-secciones que manejan los Workers.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Dict, List, Tuple

# ── Rutas del sistema ─────────────────────────────────────────────────────────
_BASE_DIR = Path(__file__).parent.parent
LIBRARY_CHROMA_PATH: str = str(_BASE_DIR / "chroma_db")
BOOKS_PRELOAD_DIR: str   = str(_BASE_DIR / "books")

# ── Parámetros del pipeline (Swarmsia) ───────────────────────────────────────
# Variables exclusivas de la arquitectura jerárquica (Director/Workers)
MAX_ITERACIONES: int = int(os.getenv("MAX_ITERACIONES", "3"))
MAX_RONDAS_DEBATE: int = int(os.getenv("MAX_RONDAS_DEBATE", "2"))

DIRECTOR_MODEL: str = os.getenv("DIRECTOR_MODEL", "groq/meta-llama/llama-4-scout-17b-16e-instruct")
WORKER_MODEL: str   = os.getenv("WORKER_MODEL",   "groq/meta-llama/llama-4-scout-17b-16e-instruct")
MODEL_NAME: str     = WORKER_MODEL  # alias de compatibilidad

SLEEP_BETWEEN_AGENTS: int = int(os.getenv("SLEEP_BETWEEN_AGENTS", "25"))
MAX_CONTEXT_CHARS: int = 1200

# ── Rúbrica oficial UPAO — 33 ítems ──────────────────────────────────────────
# Importado de la versión GraphRAG para un código mucho más limpio y mantenible
RUBRICA_ITEMS_UPAO: Dict[int, str] = {
    # ── TÍTULO
    1:  "El título es claro, conciso y refleja fielmente el contenido y el propósito de la investigación.",
    2:  "El título articula las variables, espacio y tiempo de la investigación.",
    3:  "El estudio se enmarca en la línea de investigación que promueve el programa de estudios.",
    # ── PLANTEAMIENTO DEL PROBLEMA
    4:  "El problema central del estudio describe con claridad la realidad social, económica, cultural, científica o tecnológica que motiva la investigación.",
    5:  "El problema central del estudio recoge el estado de la investigación (antecedentes) de las variables de estudio.",
    6:  "El objetivo general guarda relación con el problema.",
    7:  "Los objetivos específicos derivan del objetivo general.",
    8:  "Se explica por qué el estudio es relevante y qué aportaciones hará al campo de investigación.",
    9:  "El problema está claramente formulado.",
    10: "Se detalla la justificación de la investigación, precisando cómo contribuirá al conocimiento existente y su impacto potencial.",
    # ── MARCO TEÓRICO
    11: "Los antecedentes guardan relación con el problema de investigación.",
    12: "Las bases teóricas / científicas proporcionan una base sólida con teorías, modelos y conceptos relevantes.",
    13: "La definición de términos básicos define claramente términos técnicos y específicos para evitar confusiones.",
    14: "Las citas textuales o de paráfrasis son concordantes con la naturaleza de las variables.",
    15: "Los textos y autores citados se encuentran en las referencias bibliográficas.",
    16: "Los autores asumen una postura crítica y no solo copian las ideas de los autores citados.",
    17: "Se citan a los autores conforme a las normas internacionales (HARVARD, VANCOUVER, APA, ISO).",
    # ── HIPÓTESIS Y VARIABLES
    18: "Las hipótesis guardan relación con el problema de investigación.",
    19: "Si hay hipótesis específicas, éstas derivan de problemas derivados.",
    20: "Es clara la definición operacional de las variables: dimensiones o indicadores.",
    21: "La matriz de consistencia asegura que todos los elementos del estudio están alineados.",
    # ── MARCO METODOLÓGICO
    22: "El tipo de investigación y el método de investigación guardan relación con el problema de investigación.",
    23: "Se presenta el esquema (gráfico) del diseño de investigación.",
    24: "Define claramente la población y muestra de estudio. Si fuera el caso, se hace uso del cálculo estadístico para el tamaño y selección de la muestra.",
    25: "Describe los instrumentos de recolección de datos de manera detallada en correspondencia con el problema y diseño metodológico.",
    26: "Especifica el procedimiento de ejecución del estudio.",
    27: "Especifica las técnicas de procesamiento y análisis de datos apropiadas conforme al problema y naturaleza de las variables.",
    # ── ASPECTOS ADMINISTRATIVOS
    28: "El cronograma detalla todas las actividades y plazos para el desarrollo del proyecto.",
    29: "Se detallan claramente los recursos humanos y materiales para ejecutar el proyecto.",
    30: "El presupuesto estima los costos de los bienes y servicios requeridos para ejecutar el proyecto.",
    31: "Se precisa las fuentes de financiamiento para ejecutar el proyecto: propia y/o externas.",
    # ── REFERENCIAS BIBLIOGRÁFICAS
    32: "Se encuentran incorporados todos los autores citados.",
    33: "La redacción de las referencias bibliográficas es conforme a las normas internacionales (HARVARD, VANCOUVER, APA, ISO).",
}

# ── Mapa macro-secciones jerárquicas (Workers) → ítems ─────────────────────
SECCIONES: Dict[str, Dict] = {
    "titulo":                  {"label": "Título",                        "nums": list(range(1, 4))},
    "planteamiento_problema":  {"label": "Planteamiento del Problema",    "nums": list(range(4, 11))},
    "marco_teorico":           {"label": "Marco Teórico",                 "nums": list(range(11, 18))},
    "hipotesis_variables":     {"label": "Hipótesis y Variables",         "nums": list(range(18, 22))},
    "marco_metodologico":      {"label": "Marco Metodológico",            "nums": list(range(22, 28))},
    "aspectos_administrativos":{"label": "Aspectos Administrativos",      "nums": list(range(28, 32))},
    "referencias":             {"label": "Referencias Bibliográficas",    "nums": [32, 33]},
}

# ── Queries semánticas unificadas (Mejoradas desde GraphRAG) ─────────────────
# Se combinaron las sub-queries del código v1 para que el Worker de Swarmsia busque profundo
SECTION_QUERIES: Dict[str, str] = {
    "titulo":                  "título proyecto investigación variables espacio tiempo línea investigación",
    "planteamiento_problema":  "problema central formulación delimitación realidad antecedentes objetivos general específicos justificación importancia relevancia",
    "marco_teorico":           "antecedentes investigaciones previas base teórica científica modelos teorías conceptos definición términos básicos",
    "hipotesis_variables":     "hipótesis general específicas operacionalización variables definición operacional dimensiones indicadores matriz consistencia alineación",
    "marco_metodologico":      "tipo investigación método diseño esquema gráfico población muestra cálculo estadístico instrumentos técnicas recolección procedimiento ejecución análisis",
    "aspectos_administrativos":"cronograma actividades recursos humanos materiales presupuesto financiamiento",
    "referencias":             "referencias bibliográficas autores citados normas APA VANCOUVER HARVARD",
}

# ── Dependencias cruzadas para RAG (Adaptadas a la lógica de v1) ─────────────
# Se abstrae la lógica fina de dependencias de la versión GraphRAG para uso de los Workers
CROSS_DEPS: Dict[str, List[str]] = {
    "titulo":                  ["planteamiento_problema", "marco_teorico", "hipotesis_variables", "marco_metodologico"],
    "planteamiento_problema":  ["titulo", "hipotesis_variables"],
    "marco_teorico":           ["titulo", "hipotesis_variables"],
    "hipotesis_variables":     ["titulo", "planteamiento_problema", "marco_metodologico"],
    "marco_metodologico":      ["planteamiento_problema", "hipotesis_variables"],
    "aspectos_administrativos":["planteamiento_problema"], # Requerido para conectar presupuesto/cronograma con objetivos
    "referencias":             ["marco_teorico"],
}

# Queries de contexto cruzado específicas para el puente entre workers
CROSS_QUERIES: Dict[tuple, str] = {
    ("hipotesis_variables",      "planteamiento_problema"): "objetivos general específicos problema central formulación",
    ("hipotesis_variables",      "titulo"):                 "variables independiente dependiente espacio tiempo",
    ("marco_teorico",            "hipotesis_variables"):    "definición operacional variables dimensiones indicadores",
    ("marco_teorico",            "titulo"):                 "variables título línea investigación",
    ("marco_metodologico",       "hipotesis_variables"):    "hipótesis tipo investigación diseño",
    ("marco_metodologico",       "planteamiento_problema"): "objetivos población muestra",
    ("titulo",                   "planteamiento_problema"): "problema central objetivos variables",
    ("titulo",                   "marco_metodologico"):     "tipo investigación diseño",
    ("aspectos_administrativos", "planteamiento_problema"): "objetivos general específicos",
    ("referencias",              "marco_teorico"):          "antecedentes base teórica autores citados",
}

# ── Tabla de conversión vigesimal ────────────────────────────────────────────
SCORE_TABLE: List[Tuple[int, int, int]] = [
    (96, 99, 20), (91, 95, 19), (86, 90, 18), (81, 85, 17),
    (76, 80, 16), (71, 75, 15), (66, 70, 14), (61, 65, 13),
    (56, 60, 12), (51, 55, 11), (46, 50, 10), (41, 45,  9),
    (36, 40,  8), (31, 35,  7), (26, 30,  6), (21, 25,  5),
    (0,  20,  0),
]

def puntaje_a_nota(puntaje: int) -> int:
    """Convierte puntaje bruto (0-99) a nota vigesimal."""
    for lo, hi, nota in SCORE_TABLE:
        if lo <= puntaje <= hi:
            return nota
    return 0

def items_de_seccion(seccion_key: str) -> List[Dict]:
    """
    Retorna los ítems de la rúbrica formateados para la sección dada.
    Reconstruye el diccionario 'al vuelo' para mantener el código base limpio.
    """
    if seccion_key not in SECCIONES:
        return []
    
    label = SECCIONES[seccion_key]["label"]
    nums = SECCIONES[seccion_key]["nums"]
    
    return [{"n": n, "sec": label, "desc": RUBRICA_ITEMS_UPAO[n]} for n in nums]

# ── Lista de secciones con queries (formato legacy compatible) ────────────────
# Usado por tesis_store.py y library_store.py para buscar por sección
SECCIONES_TESIS: List[Dict] = [
    {"nombre": k, "label": v["label"], "query": SECTION_QUERIES[k]}
    for k, v in SECCIONES.items()
]


# Mapa sección-config → ítems de rúbrica; usado por pantalla_seleccion para mostrar qué evalúa
SECCION_ITEMS_MAP: Dict[str, List[int]] = {k: v["nums"] for k, v in SECCIONES.items()}


def get_texto_rubrica_para_seccion(seccion_key: str) -> str:
    """
    Genera la tabla markdown de la rúbrica lista para inyectar en el prompt del Worker.
    (Adaptado del código v1).
    """
    items = items_de_seccion(seccion_key)
    if not items:
        return ""
        
    lineas = ["| N° | Ítem de la Rúbrica UPAO | Puntaje (0-3) |",
              "|----|-----------------------------|--------------|"]
    for item in items:
        lineas.append(f"| {item['n']:02d} | {item['desc']} | ___ |")
    return "\n".join(lineas)