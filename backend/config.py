"""
Configuración global para Swarmsia (Arquitectura Jerárquica).
Integra las mejoras de granularidad y descripciones exactas del proyecto GraphRAG,
adaptadas a las macro-secciones y subsecciones que maneja el enjambre.
"""
from __future__ import annotations
import os
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Tuple

# ── Rutas del sistema ─────────────────────────────────────────────────────────
_BASE_DIR = Path(__file__).parent.parent
LIBRARY_CHROMA_PATH: str = str(_BASE_DIR / "chroma_db")
BOOKS_PRELOAD_DIR: str   = str(_BASE_DIR / "books")

# ── Parámetros del pipeline (Swarmsia) ───────────────────────────────────────
MAX_ITERACIONES: int = int(os.getenv("MAX_ITERACIONES", "3"))
MAX_RONDAS_DEBATE: int = int(os.getenv("MAX_RONDAS_DEBATE", "2"))

DIRECTOR_MODEL: str = os.getenv("DIRECTOR_MODEL", "gpt-4o-mini")
WORKER_MODEL: str   = os.getenv("WORKER_MODEL",   "gpt-4o-mini")
MODEL_NAME: str     = WORKER_MODEL  # alias de compatibilidad

SLEEP_BETWEEN_AGENTS: int = int(os.getenv("SLEEP_BETWEEN_AGENTS", "1"))
MAX_CONTEXT_CHARS: int = 1200

# ── Rúbrica oficial UPAO — 33 ítems ──────────────────────────────────────────
RUBRICA_ITEMS_UPAO: Dict[int, str] = {
    # ── TÍTULO (01-03)
    1:  "El título es claro, conciso y refleja fielmente el contenido y el propósito de la investigación.",
    2:  "El título articula las variables, espacio y tiempo de la investigación.",
    3:  "El estudio se enmarca en la línea de investigación que promueve el programa de estudios.",
    # ── PLANTEAMIENTO DEL PROBLEMA (04-10)
    4:  "El problema central del estudio describe con claridad la reality social, económica, cultural, científica o tecnológica que motiva la investigación.",
    5:  "El problema central del estudio recoge el estado de la investigación (antecedentes) de las variables de estudio.",
    6:  "El objetivo general guarda relación con el problema.",
    7:  "Los objetivos específicos derivan del objetivo general.",
    8:  "Se explica por qué el estudio es relevante y qué aportaciones hará al campo de investigación.",
    9:  "El problema está claramente formulado.",
    10: "Se detalla la justificación de la investigación, precisando cómo contribuirá al conocimiento existente y su impacto potencial.",
    # ── MARCO TEÓRICO (11-17)
    11: "Los antecedentes guardan relación con el problema de investigación.",
    12: "Las bases teóricas / científicas proporcionan una base sólida con teorías, modelos y conceptos relevantes.",
    13: "La definición de términos básicos define claramente términos técnicos y específicos para evitar confusiones.",
    14: "Las citas textuales o de paráfrasis son concordantes con la naturaleza de las variables.",
    15: "Los textos y autores citados se encuentran en las referencias bibliográficas.",
    16: "Los autores asumen una postura crítica y no solo copian las ideas de los autores citados.",
    17: "Se citan a los autores conforme a las normas internacionales (HARVARD, VANCOUVER, APA, ISO).",
    # ── HIPÓTESIS Y VARIABLES (18-21)
    18: "Las hipótesis guardan relación con el problema de investigación.",
    19: "Si hay hipótesis específicas, éstas derivan de problemas derivados.",
    20: "Es clara la definición operacional de las variables: dimensiones o indicadores.",
    21: "La matriz de consistencia asegura que todos los elementos del estudio están alineados.",
    # ── MARCO METODOLÓGICO (22-27)
    22: "El tipo de investigación y el método de investigación guardan relación con el problema de investigación.",
    23: "Se presenta el esquema (gráfico) del diseño de investigación.",
    24: "Define claramente la población y muestra de estudio. Si fuera el caso, se hace uso del cálculo estadístico para el tamaño y selección de la muestra.",
    25: "Describe los instrumentos de recolección de datos de manera detallada en correspondencia con el problema y diseño metodológico.",
    26: "Especifica el procedimiento de ejecución del estudio.",
    27: "Especifica las técnicas de procesamiento y análisis de datos apropiadas conforme al problema y naturaleza de las variables.",
    # ── ASPECTOS ADMINISTRATIVOS (28-31)
    28: "El cronograma detalla todas las actividades y plazos para el desarrollo del proyecto.",
    29: "Se detallan claramente los recursos humanos y materiales para ejecutar el proyecto.",
    30: "El presupuesto estima los costos de los bienes y servicios requeridos para ejecutar el proyecto.",
    31: "Se precisa las fuentes de financiamiento para ejecutar el proyecto: propia y/o externas.",
    # ── REFERENCIAS BIBLIOGRÁFICAS (32-33)
    32: "Se encuentran incorporados todos los autores citados.",
    33: "La redacción de las referencias bibliográficas es conforme a las normas internacionales (HARVARD, VANCOUVER, APA, ISO).",
}

# Tabla de conversión de puntaje a nota vigesimal (UPAO oficial)
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

# ── Mapa macro-secciones jerárquicas (Workers) para compatibilidad ─────────────
SECCIONES: Dict[str, Dict] = {
    "titulo":                  {"label": "Título",                        "nums": list(range(1, 4))},
    "planteamiento_problema":  {"label": "Planteamiento del Problema",    "nums": list(range(4, 11))},
    "marco_teorico":           {"label": "Marco Teórico",                 "nums": list(range(11, 18))},
    "hipotesis_variables":     {"label": "Hipótesis y Variables",         "nums": list(range(18, 22))},
    "marco_metodologico":      {"label": "Marco Metodológico",            "nums": list(range(22, 28))},
    "aspectos_administrativos":{"label": "Aspectos Administrativos",      "nums": list(range(28, 32))},
    "referencias":             {"label": "Referencias Bibliográficas",    "nums": [32, 33]},
}

# ── Mapa de granularidad fina (19 subsecciones) ────────────────────────────────
SECCION_ITEMS_MAP: Dict[str, List[int]] = {
    "1. Título del proyecto":                    [1, 2, 3],
    "1.1 Descripción y delimitación":            [4, 5],
    "1.1.2 Problema central (formulación)":      [4, 5, 9],
    "1.2 Objetivos (General y Específicos)":     [6, 7],
    "1.3 Importancia del estudio":               [8],
    "1.4 Justificación del estudio":             [10],
    "2.2 Investigaciones antecedentes":          [11, 15],
    "2.3 Base teórica (Variables)":              [12, 14, 16, 17],
    "2.4 Definición de términos básicos":        [13],
    "3.1–3.2 Hipótesis":                         [18, 19],
    "3.3 Variables (Operacionalización)":        [20],
    "3.4 Matriz de consistencia":                [21],
    "4.1–4.3 Tipo, Método y Diseño":             [22, 23],
    "4.4 Población y muestra":                   [24],
    "4.5 Instrumentos de recolección de datos":  [25],
    "4.6 Procedimiento de ejecución":            [26],
    "4.7 Análisis de datos":                     [27],
    "5. Aspectos administrativos":               [28, 29, 30, 31],
    "III. Referencias bibliográficas":           [32, 33],
}

# ── Secciones del menú con query de búsqueda semántica para ChromaDB ──────────
SECCIONES_TESIS: List[Dict] = [
    {
        "nombre": "1. Título del proyecto",
        "query":  "título proyecto investigación variables espacio tiempo línea investigación",
    },
    {
        "nombre": "1.1 Descripción y delimitación",
        "query":  "descripción problema central delimitación realidad antecedentes variables",
    },
    {
        "nombre": "1.1.2 Problema central (formulación)",
        "query":  "formulación problema central estudio planteamiento pregunta investigación",
    },
    {
        "nombre": "1.2 Objetivos (General y Específicos)",
        "query":  "objetivo general específicos investigación derivan problema",
    },
    {
        "nombre": "1.3 Importancia del estudio",
        "query":  "importancia relevancia aportaciones campo investigación estudio",
    },
    {
        "nombre": "1.4 Justificación del estudio",
        "query":  "justificación teórica práctica metodológica social investigación",
    },
    {
        "nombre": "2.2 Investigaciones antecedentes",
        "query":  "antecedentes investigaciones previas estudios relacionados citados",
    },
    {
        "nombre": "2.3 Base teórica (Variables)",
        "query":  "base teórica científica modelos teorías conceptos citas paráfrasis",
    },
    {
        "nombre": "2.4 Definición de términos básicos",
        "query":  "definición términos básicos técnicos específicos glosario",
    },
    {
        "nombre": "3.1–3.2 Hipótesis",
        "query":  "hipótesis general específicas supuestos básicos problema relación",
    },
    {
        "nombre": "3.3 Variables (Operacionalización)",
        "query":  "variables definición operacional dimensiones indicadores ítems escala",
    },
    {
        "nombre": "3.4 Matriz de consistencia",
        "query":  "matriz de consistencia alineación elementos problema objetivo hipótesis variable",
    },
    {
        "nombre": "4.1–4.3 Tipo, Método y Diseño",
        "query":  "tipo investigación método diseño esquema gráfico investigación",
    },
    {
        "nombre": "4.4 Población y muestra",
        "query":  "población muestra estudio cálculo estadístico selección criterios",
    },
    {
        "nombre": "4.5 Instrumentos de recolección de datos",
        "query":  "instrumentos técnicas recolección datos correspondencia diseño",
    },
    {
        "nombre": "4.6 Procedimiento de ejecución",
        "query":  "procedimiento ejecución estudio pasos etapas actividades",
    },
    {
        "nombre": "4.7 Análisis de datos",
        "query":  "técnicas procesamiento análisis datos estadísticas naturaleza variables",
    },
    {
        "nombre": "5. Aspectos administrativos",
        "query":  "cronograma actividades recursos humanos materiales presupuesto financiamiento",
    },
    {
        "nombre": "III. Referencias bibliográficas",
        "query":  "referencias bibliográficas autores citados normas APA VANCOUVER HARVARD",
    },
]

# ── Dependencias cruzadas entre subsecciones ─────────────────────────────────
DEPENDENCIAS_SECCIONES: Dict[str, List[str]] = {
    "1. Título del proyecto": [
        "1.1.2 Problema central (formulación)",
        "1.2 Objetivos (General y Específicos)",
        "3.3 Variables (Operacionalización)",
        "3.1–3.2 Hipótesis",
        "2.3 Base teórica (Variables)",
        "4.1–4.3 Tipo, Método y Diseño",
    ],
    "1.1 Descripción y delimitación": [
        "1. Título del proyecto",
        "1.2 Objetivos (General y Específicos)",
    ],
    "1.1.2 Problema central (formulación)": [
        "1. Título del proyecto",
        "1.2 Objetivos (General y Específicos)",
        "3.1–3.2 Hipótesis",
    ],
    "1.2 Objetivos (General y Específicos)": [
        "1.1.2 Problema central (formulación)",
        "3.1–3.2 Hipótesis",
        "3.3 Variables (Operacionalización)",
    ],
    "1.3 Importancia del estudio": [
        "1.1.2 Problema central (formulación)",
    ],
    "1.4 Justificación del estudio": [
        "1.1.2 Problema central (formulación)",
        "1.2 Objetivos (General y Específicos)",
    ],
    "2.2 Investigaciones antecedentes": [
        "1.1.2 Problema central (formulación)",
        "3.3 Variables (Operacionalización)",
    ],
    "2.3 Base teórica (Variables)": [
        "3.3 Variables (Operacionalización)",
        "1. Título del proyecto",
    ],
    "2.4 Definición de términos básicos": [
        "3.3 Variables (Operacionalización)",
        "2.3 Base teórica (Variables)",
    ],
    "3.1–3.2 Hipótesis": [
        "1.1.2 Problema central (formulación)",
        "1.2 Objetivos (General y Específicos)",
        "3.3 Variables (Operacionalización)",
    ],
    "3.3 Variables (Operacionalización)": [
        "3.4 Matriz de consistencia",
        "4.1–4.3 Tipo, Método y Diseño",
        "4.5 Instrumentos de recolección de datos",
    ],
    "3.4 Matriz de consistencia": [
        "3.3 Variables (Operacionalización)",
        "4.1–4.3 Tipo, Método y Diseño",
        "4.7 Análisis de datos",
    ],
    "4.1–4.3 Tipo, Método y Diseño": [
        "3.3 Variables (Operacionalización)",
        "3.4 Matriz de consistencia",
        "4.4 Población y muestra",
    ],
    "4.4 Población y muestra": [
        "4.1–4.3 Tipo, Método y Diseño",
        "4.5 Instrumentos de recolección de datos",
        "3.3 Variables (Operacionalización)",
    ],
    "4.5 Instrumentos de recolección de datos": [
        "3.3 Variables (Operacionalización)",
        "4.1–4.3 Tipo, Método y Diseño",
        "4.4 Población y muestra",
    ],
    "4.6 Procedimiento de ejecución": [
        "4.1–4.3 Tipo, Método y Diseño",
        "4.4 Población y muestra",
        "4.5 Instrumentos de recolección de datos",
    ],
    "4.7 Análisis de datos": [
        "3.3 Variables (Operacionalización)",
        "4.1–4.3 Tipo, Método y Diseño",
        "4.5 Instrumentos de recolección de datos",
    ],
    "5. Aspectos administrativos": [
        "4.1–4.3 Tipo, Método y Diseño",
        "4.4 Población y muestra",
        "4.6 Procedimiento de ejecución",
    ],
    "III. Referencias bibliográficas": [
        "3.3 Variables (Operacionalización)",
        "4.1–4.3 Tipo, Método y Diseño",
        "4.5 Instrumentos de recolección de datos",
    ],
}

# Compatibilidad con variables legacy
CROSS_DEPS = DEPENDENCIAS_SECCIONES

_STOP_CFG = {
    "de", "del", "la", "el", "los", "las", "un", "una", "y", "e", "o", "u",
    "con", "en", "al", "para", "por", "que", "se", "su", "sus", "es", "son",
    "a", "ante", "bajo", "desde", "sin", "sobre", "tras", "como",
    "estudio", "investigacion", "proyecto",
}

def _kw_seccion(texto: str) -> set[str]:
    """Palabras significativas de un nombre de sección."""
    sin_acentos = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii')
    tokens = re.sub(r'[\d\.\,\-–\(\)\[\]/]', ' ', sin_acentos.lower()).split()
    return {t for t in tokens if len(t) > 2 and t not in _STOP_CFG}

def _mapear_a_clave_config(seccion: str) -> str | None:
    """Mapea un nombre de sección (TOC o entrada) a una clave de SECCION_ITEMS_MAP."""
    # 1. Coincidencia exacta
    if seccion in SECCION_ITEMS_MAP:
        return seccion

    # 2. Prefijo numérico exacto
    m = re.match(r'^(\d[\d\.]*)', seccion.strip())
    prefijo_num = m.group(1).rstrip('.') if m else None
    if prefijo_num:
        for k in SECCION_ITEMS_MAP.keys():
            m2 = re.match(r'^(\d[\d\.]*)', k.strip())
            if m2 and m2.group(1).rstrip('.') == prefijo_num:
                return k

    # 3. Overlap de palabras clave
    kw = _kw_seccion(seccion)
    if kw:
        mejor_jaccard = 0.0
        mejor_clave = None
        for k in SECCION_ITEMS_MAP.keys():
            kw_k    = _kw_seccion(k)
            inter   = len(kw & kw_k)
            if inter == 0:
                continue
            union   = len(kw | kw_k)
            jaccard = inter / union if union else 0.0
            if jaccard > mejor_jaccard:
                mejor_jaccard = jaccard
                mejor_clave   = k
        if mejor_jaccard > 0:
            return mejor_clave

    # 4. Prefijo padre
    if prefijo_num and '.' in prefijo_num:
        padre = prefijo_num.rsplit('.', 1)[0]
        for k in SECCION_ITEMS_MAP.keys():
            m2 = re.match(r'^(\d[\d\.]*)', k.strip())
            if m2 and m2.group(1).rstrip('.') == padre:
                return k

    return None

def _buscar_items_seccion(seccion: str) -> List[int]:
    """Busca los ítems de la rúbrica aplicables a la sección."""
    clave = _mapear_a_clave_config(seccion)
    if clave:
        return SECCION_ITEMS_MAP[clave]
    return []

def items_de_seccion(seccion_key: str) -> List[Dict]:
    """Retorna los ítems de la rúbrica formateados para la sección dada."""
    nums = _buscar_items_seccion(seccion_key)
    if not nums:
        # Fallback a macro-secciones si seccion_key es macro
        if seccion_key in SECCIONES:
            nums = SECCIONES[seccion_key]["nums"]
            label = SECCIONES[seccion_key]["label"]
        else:
            nums = list(RUBRICA_ITEMS_UPAO.keys())
            label = "General"
    else:
        clave_mapped = _mapear_a_clave_config(seccion_key) or seccion_key
        label = clave_mapped

    return [{"n": n, "sec": label, "desc": RUBRICA_ITEMS_UPAO[n]} for n in nums]

def get_items_texto_para_seccion(seccion: str) -> str:
    """Genera la tabla de ítems relevantes para una sección, lista para inyectar en el prompt."""
    items_nums = _buscar_items_seccion(seccion)
    if not items_nums:
        if seccion in SECCIONES:
            items_nums = SECCIONES[seccion]["nums"]
        else:
            items_nums = list(RUBRICA_ITEMS_UPAO.keys())
            
    lineas = ["| N° | Ítem de la Rúbrica UPAO | Puntaje (0-3) |",
              "|----|-----------------------------|--------------|"]
    for num in items_nums:
        desc = RUBRICA_ITEMS_UPAO.get(num, "Ítem sin descripción")
        lineas.append(f"| {num:02d} | {desc} | ___ |")
    return "\n".join(lineas)

def get_puntaje_maximo_seccion(seccion: str) -> int:
    """Puntaje máximo posible para la sección (nro. de ítems × 3)."""
    items_nums = _buscar_items_seccion(seccion)
    if not items_nums:
        if seccion in SECCIONES:
            items_nums = SECCIONES[seccion]["nums"]
        else:
            items_nums = list(RUBRICA_ITEMS_UPAO.keys())
    return len(items_nums) * 3

def get_texto_rubrica_para_seccion(seccion_key: str) -> str:
    """Genera la tabla markdown de la rúbrica lista para inyectar en el prompt."""
    return get_items_texto_para_seccion(seccion_key)