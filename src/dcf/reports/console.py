"""Presentación del informe Markdown en la terminal con ``rich``.

En una terminal el Markdown se muestra formateado (títulos, tablas con bordes, negritas).
Si la salida se redirige a un fichero o a otro programa, o se pide ``raw``, se escribe
el Markdown tal cual, sin códigos de color.
"""

from __future__ import annotations

import sys
from typing import TextIO

from rich.console import Console
from rich.markdown import Markdown


# Muestra el informe: formateado con rich en una terminal, Markdown plano si no.
def print_report(
    markdown: str, raw: bool = False, file: TextIO | None = None, force_format: bool = False
) -> None:
    """Escribe el informe en la consola.

    Args:
        markdown: Informe en Markdown (ver :func:`dcf.reports.markdown.render_report`).
        raw: Si es ``True``, escribe el Markdown sin formatear.
        file: Destino; ``None`` = salida estándar.
        force_format: Formatea aunque el destino no sea una terminal (para tests).
    """
    out = file if file is not None else sys.stdout
    if raw or not (force_format or out.isatty()):
        print(markdown, file=out)
        return
    console = Console(file=out, force_terminal=force_format or None, soft_wrap=False)
    console.print(Markdown(markdown))
