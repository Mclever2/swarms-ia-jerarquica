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
_UMBRAL_PAGINA_TOC = 0.28  # si ≥28 % de líneas son TOC → omitir página


def _es_pagina_indice(texto: str) -> bool:
    lineas = [l for l in texto.split('\n') if l.strip()]
    if not lineas:
        return False
    matches = sum(1 for l in lineas if _RE_TOC_LINEA.search(l.strip()))
    return matches / len(lineas) >= _UMBRAL_PAGINA_TOC


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
