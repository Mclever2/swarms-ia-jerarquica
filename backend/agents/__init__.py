"""
Limpieza del workspace de Swarms al importar el módulo.
Previene la inyección de memoria acumulada entre sesiones.
"""
import shutil
from pathlib import Path

_WS = Path(__file__).parent.parent.parent / "agent_workspace"
if _WS.exists():
    shutil.rmtree(_WS, ignore_errors=True)
