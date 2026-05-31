"""
ChromaDB efímero para el PDF del estudiante.

Ciclo de vida: se crea por sesión y se destruye al cerrar el navegador.
Usa chunking inteligente basado en TOC para asignar fragmentos a secciones reales.
"""

import logging
import re
from collections import Counter

import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.config import SECCIONES_TESIS, CROSS_DEPS, CROSS_QUERIES, SECTION_QUERIES

logger = logging.getLogger(__name__)


# ── Helpers de jerarquía de secciones ────────────────────────────────────────

def _extraer_prefijo(nombre: str) -> str:
    m = re.match(r'^(\d[\d\.]*)', nombre.strip())
    return m.group(1).rstrip('.') if m else ""


def _extraer_prefijos_rango(seccion: str) -> list:
    m = re.match(r'^(\d[\d\.]*)[\s]*[–\-][\s]*(\d[\d\.]*)', seccion.strip())
    if not m:
        p = _extraer_prefijo(seccion)
        return [p] if p else []
    ini = m.group(1).rstrip('.')
    fin = m.group(2).rstrip('.')
    p_ini = [int(x) for x in ini.split('.')]
    p_fin = [int(x) for x in fin.split('.')]
    if len(p_ini) != len(p_fin) or not p_ini:
        return [ini]
    if p_ini[:-1] != p_fin[:-1]:
        return [ini]
    padre = '.'.join(str(x) for x in p_ini[:-1])
    return [
        f"{padre}.{i}" if padre else str(i)
        for i in range(p_ini[-1], p_fin[-1] + 1)
    ]


def _prefijo_ancestro_comun(prefijos: list) -> str:
    unicos = list({p for p in prefijos if p})
    if not unicos:
        return ""
    if len(unicos) == 1:
        return unicos[0]
    partes = [p.split('.') for p in unicos]
    prof_max = max(len(p) for p in partes)
    prof_min = min(len(p) for p in partes)
    for nivel in range(prof_min, 0, -1):
        candidatos = {'.'.join(p[:nivel]) for p in partes}
        if len(candidatos) == 1:
            if prof_max - nivel <= 2:
                return candidatos.pop()
            return ""
    return ""


def _es_subseccion(nombre: str, prefijo_padre: str) -> bool:
    if not prefijo_padre:
        return False
    p = _extraer_prefijo(nombre)
    return p == prefijo_padre or p.startswith(prefijo_padre + ".")


CHUNK_SIZE    = 600
CHUNK_OVERLAP = 80
K_RESULTADOS  = 4
K_INICIAL     = 6
MAX_FRAGMENTOS_SECCION = 20

_MIN_CHARS_CHUNK = 80


# ── Agrupación por TOC ────────────────────────────────────────────────────────

def _encontrar_encabezado_en_texto(texto: str, nombre_seccion: str) -> int:
    idx = texto.find(nombre_seccion)
    if idx >= 0:
        return idx

    nombre_norm = re.sub(r'\s+', ' ', nombre_seccion).strip()
    idx = texto.find(nombre_norm)
    if idx >= 0:
        return idx

    m_pref = re.match(r'^(\d[\d\.]*)', nombre_norm)
    if m_pref:
        prefix = m_pref.group(1).rstrip('.')
        pattern = r'(?:(?<=\n)|^)' + re.escape(prefix) + r'[.\s]'
        m = re.search(pattern, texto)
        if m:
            pos = m.start()
            return pos + (1 if pos < len(texto) and texto[pos] == '\n' else 0)

    return -1


def _agrupar_por_toc(
    paginas: list,
    estructura_toc: dict,
) -> list:

    if not estructura_toc or not paginas:
        texto_total = "\n\n".join(t for _, t in sorted(paginas))
        return [("Documento completo", texto_total, 1)]

    secciones_ord = sorted(estructura_toc.items(), key=lambda x: x[1])
    acumulado: dict = {nombre: [] for nombre, _ in secciones_ord}
    paginas_asignadas = 0

    for pag, texto_pag in sorted(paginas):
        secciones_en_pag = [n for n, p in secciones_ord if p == pag]

        if not secciones_en_pag:
            running = None
            for nombre, pag_inicio in reversed(secciones_ord):
                if pag_inicio <= pag:
                    running = nombre
                    break
            if running is not None:
                acumulado[running].append(texto_pag)
                paginas_asignadas += 1
        else:
            prev = None
            for nombre, pag_inicio in reversed(secciones_ord):
                if pag_inicio < pag:
                    prev = nombre
                    break

            posiciones: dict = {}
            for nombre in secciones_en_pag:
                pos = _encontrar_encabezado_en_texto(texto_pag, nombre)
                if pos >= 0:
                    posiciones[nombre] = pos

            if posiciones:
                secciones_pos = sorted(posiciones.items(), key=lambda x: x[1])
                primera_pos = secciones_pos[0][1]
                if primera_pos > 0 and prev is not None:
                    previo = texto_pag[:primera_pos].strip()
                    if previo:
                        acumulado[prev].append(previo)
                for i, (nombre, pos) in enumerate(secciones_pos):
                    sig = secciones_pos[i + 1][1] if i + 1 < len(secciones_pos) else len(texto_pag)
                    frag = texto_pag[pos:sig].strip()
                    if frag:
                        acumulado[nombre].append(frag)
            else:
                acumulado[secciones_en_pag[-1]].append(texto_pag)

            paginas_asignadas += 1

    if paginas_asignadas == 0:
        logger.warning(
            "TOC detectado pero ninguna página coincide con sus números de página. "
            "Fallback a chunking por tamaño fijo."
        )
        texto_total = "\n\n".join(t for _, t in sorted(paginas))
        return [("Documento completo", texto_total, 1)]

    grupos: list = []
    for nombre, pag_inicio in secciones_ord:
        texto_sec = "\n\n".join(acumulado[nombre])
        if texto_sec.strip():
            grupos.append((nombre, texto_sec.strip(), pag_inicio))

    logger.info(
        f"TOC: {len(grupos)} secciones con contenido "
        f"({paginas_asignadas}/{len(paginas)} páginas asignadas)"
    )
    return grupos


def _secciones_a_documentos(
    grupos: list,
    collection_name: str,
    splitter: RecursiveCharacterTextSplitter,
) -> list:

    docs: list = []
    for nombre, texto, pag_inicio in grupos:
        texto_limpio = texto.strip()
        if len(texto_limpio) < _MIN_CHARS_CHUNK:
            logger.debug(f"Sección '{nombre}' descartada ({len(texto_limpio)} chars — solo título)")
            continue

        metadata = {
            "source":        collection_name,
            "tipo":          "proyecto_tesis",
            "seccion":       nombre,
            "pagina_inicio": pag_inicio,
        }

        if len(texto_limpio) <= CHUNK_SIZE:
            docs.append(Document(page_content=texto_limpio, metadata=metadata))
        else:
            chunks = splitter.create_documents([texto_limpio], metadatas=[metadata])
            docs.extend(chunks)

    return docs


_STOP_WORDS = {
    "de", "del", "la", "el", "los", "las", "un", "una", "y", "e", "o", "u",
    "con", "en", "al", "para", "por", "que", "se", "su", "sus", "es", "son",
    "a", "ante", "bajo", "desde", "sin", "sobre", "tras", "como",
}


def _palabras_clave(texto: str) -> set:
    tokens = re.sub(r'[\d\.\,\-–\(\)\[\]/]', ' ', texto.lower()).split()
    return {t for t in tokens if len(t) > 2 and t not in _STOP_WORDS}


def _buscar_query_semantica(seccion: str) -> str:
    for sec in SECCIONES_TESIS:
        if sec["nombre"] == seccion:
            return sec["query"]

    kw_seccion = _palabras_clave(seccion)
    if kw_seccion:
        mejor_score = 0
        mejor_query = None
        for sec in SECCIONES_TESIS:
            score = len(kw_seccion & _palabras_clave(sec["nombre"]))
            if score > mejor_score:
                mejor_score = score
                mejor_query = sec["query"]
        if mejor_score >= 1 and mejor_query:
            return mejor_query

    prefijo = _extraer_prefijo(seccion)
    if prefijo:
        for sec in SECCIONES_TESIS:
            p = _extraer_prefijo(sec["nombre"])
            if p and p == prefijo:
                return sec["query"]

    return seccion


# ── API pública ───────────────────────────────────────────────────────────────

def construir_vector_store(
    paginas: list,
    estructura_toc: dict,
    embeddings: "Embeddings | None" = None,
    collection_name: str = "tesis_upao",
) -> Chroma:
    """
    Divide el PDF en fragmentos usando el TOC detectado e indexa en ChromaDB.

    Args:
        paginas:         lista de (numero_pagina, texto_pagina) de extraer_contenido_sin_indice.
        estructura_toc:  dict {nombre_sección → pagina_inicio} del TOC del PDF.
        embeddings:      modelo de embeddings (si None, carga internamente).
        collection_name: nombre de la colección ChromaDB.
    """
    if not paginas:
        raise ValueError("El texto extraído del PDF está vacío.")

    if embeddings is None:
        from backend.rag.embeddings import cargar_modelo_embeddings
        embeddings = cargar_modelo_embeddings()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", "   ", " ", ""],
    )

    if estructura_toc:
        grupos = _agrupar_por_toc(paginas, estructura_toc)
        documentos = _secciones_a_documentos(grupos, collection_name, splitter)
        logger.info(f"Chunking por TOC: {len(grupos)} secciones → {len(documentos)} fragmentos")
    else:
        texto_total = "\n\n".join(t for _, t in sorted(paginas))
        documentos = splitter.create_documents(
            [texto_total],
            metadatas=[{"source": collection_name, "tipo": "proyecto_tesis"}],
        )
        logger.info(f"Chunking fijo (sin TOC): {len(documentos)} fragmentos")

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

    query = _buscar_query_semantica(seccion)
    logger.info(f"RAG tesis → '{seccion}' | query: '{query[:55]}…'")

    try:
        n_total = vector_store._collection.count()
        todos_docs = vector_store.similarity_search(query, k=n_total)
    except Exception as exc:
        logger.error(f"Error en similarity_search tesis: {exc}")
        return f"[Error en búsqueda RAG: {exc}]"

    if not todos_docs:
        return (
            f"No se encontró contenido relevante en el PDF para '{seccion}'.\n"
            "El estudiante puede no haber redactado aún esta sección."
        )

    top_meta = [d.metadata.get("seccion") for d in todos_docs[:K_INICIAL]
                if d.metadata.get("seccion")]

    if not top_meta:
        docs = todos_docs[:k]
        logger.info(f"RAG tesis: {len(docs)} fragmentos (sin metadata de sección)")
    else:
        config_prefijos = _extraer_prefijos_rango(seccion)
        top_prefijos    = [_extraer_prefijo(s) for s in top_meta if _extraer_prefijo(s)]

        config_relevante = bool(config_prefijos) and any(
            any(pt == cp or pt.startswith(cp + ".") or cp.startswith(pt + ".")
                for pt in top_prefijos)
            for cp in config_prefijos
        )

        if config_relevante:
            docs = [d for d in todos_docs
                    if any(_es_subseccion(d.metadata.get("seccion", ""), cp)
                           for cp in config_prefijos)]
            docs = docs[:MAX_FRAGMENTOS_SECCION]
            logger.info(f"RAG tesis: prefijos config {config_prefijos} → {len(docs)} fragmentos")
        else:
            ancestor = _prefijo_ancestro_comun(top_prefijos)
            if ancestor:
                docs = [d for d in todos_docs
                        if _es_subseccion(d.metadata.get("seccion", ""), ancestor)]
                docs = docs[:MAX_FRAGMENTOS_SECCION]
                logger.info(f"RAG tesis: ancestro semántico '{ancestor}' → {len(docs)} fragmentos")
            else:
                seccion_dominante = Counter(top_meta).most_common(1)[0][0]
                prefijo_dom = _extraer_prefijo(seccion_dominante)
                if prefijo_dom:
                    docs = [d for d in todos_docs
                            if _es_subseccion(d.metadata.get("seccion", ""), prefijo_dom)]
                else:
                    docs = [d for d in todos_docs
                            if d.metadata.get("seccion") == seccion_dominante]
                docs = docs[:MAX_FRAGMENTOS_SECCION]
                logger.info(f"RAG tesis: dominante '{seccion_dominante}' → {len(docs)} fragmentos")

    fragmentos = [f"[Fragmento {i + 1}]\n{d.page_content}" for i, d in enumerate(docs)]
    resultado = "\n\n" + "\n\n---\n\n".join(fragmentos) + "\n"
    logger.info(f"RAG tesis: {len(resultado)} chars totales recuperados")
    return resultado


_CONSULTAS_CRUZADAS: dict = {
    "Título y delimitación":  "título investigación variables independiente dependiente espacio tiempo",
    "Problema central":       "problema central formulación pregunta investigación planteamiento realidad",
    "Objetivos":              "objetivo general específicos investigación derivan problema",
    "Hipótesis":              "hipótesis relación variables supuesto básico específicas",
    "Operacionalización":     "operacionalización variables dimensiones indicadores escala medición",
    "Marco metodológico":     "tipo método diseño investigación cuantitativo cualitativo",
    "Antecedentes / Marco teórico": "antecedentes investigaciones previas base teórica conceptos",
}

_MAX_CHARS_POR_FRAGMENTO = 500
_MAX_CHARS_CRUZADO       = 6_000


def recuperar_contexto_cruzado(
    vector_store: Chroma,
    seccion_principal: str,
) -> str:

    prefijo_principal = _extraer_prefijo(seccion_principal)
    partes: list = []
    prefijos_visitados: set = set()
    chars_acumulados = 0

    for nombre_consulta, query in _CONSULTAS_CRUZADAS.items():
        if chars_acumulados >= _MAX_CHARS_CRUZADO:
            break
        try:
            docs = vector_store.similarity_search(query, k=6)
            for doc in docs:
                seccion_doc = doc.metadata.get("seccion", "")
                prefijo_doc = _extraer_prefijo(seccion_doc)

                if prefijo_principal and prefijo_doc and _es_subseccion(seccion_doc, prefijo_principal):
                    continue
                if prefijo_doc in prefijos_visitados:
                    continue
                if len(doc.page_content.strip()) < _MIN_CHARS_CHUNK:
                    continue

                fragmento = doc.page_content[:_MAX_CHARS_POR_FRAGMENTO]
                partes.append(f"**{seccion_doc}**\n{fragmento}")
                prefijos_visitados.add(prefijo_doc)
                chars_acumulados += len(fragmento)
                break
        except Exception as exc:
            logger.warning(f"[Cross-context] Error en query '{nombre_consulta}': {exc}")

    if not partes:
        return ""

    resultado = "\n\n---\n\n".join(partes)
    logger.info(f"[Cross-context] {len(partes)} secciones cruzadas recuperadas ({chars_acumulados} chars)")
    return resultado


def recuperar_vista_general(vector_store: Chroma) -> str:

    try:
        result = vector_store._collection.get(include=["metadatas", "documents"])
        metadatas = result.get("metadatas") or []
        documents = result.get("documents") or []

        por_capitulo: dict = {}
        for meta, doc in zip(metadatas, documents):
            seccion = meta.get("seccion", "")
            m = re.match(r'^(\d)', seccion.strip())
            capitulo = m.group(1) if m else "?"
            por_capitulo.setdefault(capitulo, []).append((seccion, doc))

        partes: list = []
        for cap in sorted(por_capitulo.keys()):
            mejor_seccion, mejor_doc = max(por_capitulo[cap], key=lambda x: len(x[1]))
            partes.append(f"**{mejor_seccion}**\n{mejor_doc[:600]}")

        if not partes:
            return ""

        resultado = "\n\n---\n\n".join(partes)
        logger.info(f"[Vista general] {len(partes)} capítulos representados ({len(resultado)} chars)")
        return resultado

    except Exception as exc:
        logger.error(f"Error en recuperar_vista_general: {exc}")
        return ""


def obtener_stats_secciones(vector_store: Chroma) -> list:

    try:
        result = vector_store._collection.get(include=["metadatas", "documents"])
        metadatas = result.get("metadatas") or []
        documents = result.get("documents") or []

        stats: dict = {}
        for meta, doc in zip(metadatas, documents):
            seccion = meta.get("seccion", "Sin sección")
            pag     = meta.get("pagina_inicio", 0)
            chars   = len(doc)
            if seccion not in stats:
                stats[seccion] = {"seccion": seccion, "pagina_inicio": pag, "chars": 0, "n_fragmentos": 0}
            stats[seccion]["chars"]        += chars
            stats[seccion]["n_fragmentos"] += 1

        return sorted(stats.values(), key=lambda x: x["pagina_inicio"])
    except Exception as exc:
        logger.error(f"Error obteniendo stats de secciones: {exc}")
        return []


# ── Wrappers de compatibilidad con pantalla_revision ─────────────────────────

def query_context(
    vector_store: Chroma,
    seccion_key: str,
    k: int = K_RESULTADOS,
) -> str:
    return recuperar_contexto(vector_store, seccion_key, k=k)


def query_cross_context(
    vector_store: Chroma,
    seccion_key: str,
    k_por_dep: int = 2,
) -> str:
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
