"""Extracción de texto desde archivos PDF usando pdfplumber."""

import io
import logging
import re
import warnings
from typing import Dict

import pdfplumber

logger = logging.getLogger(__name__)

# pdfplumber emite warnings de bajo nivel por PDFs con espacios de color
# no estándar (ej. 2 componentes). Son inofensivos: el texto se extrae igual.
_PDFPLUMBER_WARNINGS = [
    "Cannot set non-stroke color",
    "Cannot set stroke color",
]

# Detecta líneas de índice/TOC: "Título del capítulo ......... 12"
_RE_TOC_LINEA = re.compile(r'\.{4,}\s*\d{1,4}\s*$')
# Parsea una entrada de TOC: "3.3 Título de sección .... 22"
_RE_ENTRADA_TOC = re.compile(
    r'^(\d[\d\.\-–]*\.?\s*[A-ZÁÉÍÓÚÜÑ][^\.]{3,}?)\s*\.{3,}\s*(\d{1,4})\s*$',
    re.IGNORECASE,
)
_UMBRAL_PAGINA_TOC = 0.28  # si ≥28 % de líneas son TOC → omitir página


def _ratio_lineas_toc(texto_pagina: str) -> float:
    lineas = [l.strip() for l in texto_pagina.split('\n') if l.strip()]
    if len(lineas) < 2:
        return 0.0
    n_toc = sum(1 for l in lineas if _RE_TOC_LINEA.search(l))
    return n_toc / len(lineas)


def _es_pagina_indice(texto: str) -> bool:
    return _ratio_lineas_toc(texto) >= _UMBRAL_PAGINA_TOC


def _parsear_toc(paginas_toc: list) -> dict:
    """Extrae la estructura del índice: {nombre_seccion: numero_pagina}."""
    estructura: dict = {}
    for texto in paginas_toc:
        for linea in texto.split('\n'):
            m = _RE_ENTRADA_TOC.match(linea.strip())
            if m:
                nombre = re.sub(r'\s+', ' ', m.group(1)).strip()
                try:
                    estructura[nombre] = int(m.group(2))
                except ValueError:
                    pass
    return estructura


def extraer_texto_pdf(pdf_bytes: bytes) -> str:
    """
    Extrae el texto completo de un PDF dado como bytes.
    Las páginas identificadas como índice/TOC se omiten automáticamente.

    Args:
        pdf_bytes: Contenido del archivo PDF como bytes.

    Returns:
        Texto limpio, una página por párrafo, con páginas vacías e índices omitidos.

    Raises:
        Exception: Si pdfplumber no puede abrir el archivo.
    """
    paginas = []
    paginas_toc = 0
    try:
        # Suprimir warnings de espacios de color no estándar en el PDF
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Cannot set.*color")
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for i, pagina in enumerate(pdf.pages):
                    texto = pagina.extract_text()
                    if not texto or not texto.strip():
                        continue
                    if _es_pagina_indice(texto.strip()):
                        paginas_toc += 1
                        logger.debug(f"  Pág. {i + 1}: índice/TOC omitida")
                        continue
                    paginas.append(texto.strip())
                    logger.debug(f"  Pág. {i + 1}: {len(texto)} chars")
    except Exception as exc:
        logger.error(f"Error extrayendo texto del PDF: {exc}")
        raise

    resultado = "\n\n".join(paginas)
    logger.info(
        f"PDF extraído: {len(paginas)} páginas de contenido, "
        f"{paginas_toc} de índice/TOC omitidas, "
        f"{len(resultado):,} caracteres totales"
    )
    return resultado


def extraer_contenido_sin_indice(
    pdf_bytes: bytes,
) -> tuple:
    """
    Extrae el texto del PDF separando contenido real de páginas de índice/TOC.

    Devuelve:
        paginas_contenido: lista de (numero_pagina_1indexed, texto_pagina).
        estructura_toc:    dict {nombre_sección → numero_pagina_inicio}.
    """
    paginas_contenido: list = []
    paginas_toc_texto: list = []
    n_toc = 0

    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Cannot set.*color")
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                total = len(pdf.pages)
                for i, pagina in enumerate(pdf.pages):
                    numero_pagina = i + 1
                    texto = pagina.extract_text()
                    if not texto or not texto.strip():
                        continue

                    ratio = _ratio_lineas_toc(texto)
                    if ratio >= _UMBRAL_PAGINA_TOC:
                        n_toc += 1
                        paginas_toc_texto.append(texto)
                        logger.info(
                            f"Pág. {numero_pagina}/{total}: ÍNDICE (ratio={ratio:.2f}) — excluida del RAG"
                        )
                    else:
                        paginas_contenido.append((numero_pagina, texto.strip()))
    except Exception as exc:
        logger.error(f"Error extrayendo contenido sin índice: {exc}")
        raise

    estructura_toc = _parsear_toc(paginas_toc_texto)

    logger.info(
        f"Extracción inteligente: {len(paginas_contenido)} páginas de contenido, "
        f"{n_toc} páginas de índice omitidas, "
        f"{len(estructura_toc)} secciones detectadas en TOC"
    )
    if estructura_toc:
        secciones_str = ', '.join(list(estructura_toc.keys())[:6])
        logger.info(f"Estructura TOC: {secciones_str}{'…' if len(estructura_toc) > 6 else ''}")

    return paginas_contenido, estructura_toc


# ── Segmentación por secciones ────────────────────────────────────────────────

# Patrones de encabezado para cada sección de la tesis UPAO.
# Orden importa: se busca en secuencia y se captura el texto hasta el siguiente patrón.
_PATRONES_SECCION: Dict[str, str] = {
    "titulo":                  r"(?i)(t[ií]tulo|i\.\s*informaci[oó]n\s*general)",
    "planteamiento_problema":  r"(?i)(planteamiento\s+del\s+problema|ii\.\s*planteamiento)",
    "marco_teorico":           r"(?i)(marco\s+te[oó]rico|iii\.\s*marco\s*te[oó]rico)",
    "hipotesis_variables":     r"(?i)(hip[oó]tesis|variables|iv\.\s*hip[oó]tesis)",
    "marco_metodologico":      r"(?i)(marco\s+metodol[oó]gico|v\.\s*marco\s*metodol[oó]gico)",
    "aspectos_administrativos":r"(?i)(aspectos\s+administrativos|vi\.\s*aspectos)",
    "referencias":             r"(?i)(referencias\s+bibliogr[aá]ficas|referencias|bibliograf[ií]a)",
}


def split_into_sections(texto: str) -> Dict[str, str]:
    """
    Segmenta el texto completo del PDF en las 7 secciones estándar de la tesis UPAO.

    Estrategia: busca encabezados de sección con regex y extrae el texto
    comprendido entre encabezados consecutivos.

    Returns:
        Dict {seccion_key: texto_de_la_seccion}
        Si una sección no se detecta, su valor es "[Sección no encontrada en el PDF]".
    """
    # Encontrar posición de inicio de cada sección detectada
    posiciones: Dict[str, int] = {}
    for clave, patron in _PATRONES_SECCION.items():
        match = re.search(patron, texto)
        if match:
            posiciones[clave] = match.start()

    secciones_ordenadas = sorted(posiciones.items(), key=lambda x: x[1])
    resultado: Dict[str, str] = {}

    for i, (clave, inicio) in enumerate(secciones_ordenadas):
        fin = secciones_ordenadas[i + 1][1] if i + 1 < len(secciones_ordenadas) else len(texto)
        fragmento = texto[inicio:fin].strip()
        resultado[clave] = fragmento if fragmento else "[Sección vacía]"

    # Marcar las no detectadas
    for clave in _PATRONES_SECCION:
        if clave not in resultado:
            resultado[clave] = "[Sección no encontrada en el PDF]"
            logger.warning(f"split_into_sections: sección '{clave}' no detectada")

    logger.info(
        f"Secciones detectadas: {[k for k, v in resultado.items() if not v.startswith('[')]}"
    )
    return resultado
