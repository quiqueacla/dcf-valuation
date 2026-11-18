"""Presentación del informe en consola (rich)."""

import io

from dcf.reports.console import print_report

MD = "# Título\n\n| Dato | Valor |\n| --- | ---: |\n| WACC | **8,13 %** |\n"


def test_destino_no_terminal_escribe_markdown_plano() -> None:
    out = io.StringIO()
    print_report(MD, file=out)
    assert out.getvalue().startswith("# Título")
    assert "| WACC | **8,13 %** |" in out.getvalue()


def test_raw_escribe_markdown_aunque_se_fuerce() -> None:
    out = io.StringIO()
    print_report(MD, raw=True, file=out, force_format=True)
    assert "| WACC |" in out.getvalue()


def test_formateado_con_rich() -> None:
    out = io.StringIO()
    print_report(MD, file=out, force_format=True)
    text = out.getvalue()
    assert "Título" in text and "8,13 %" in text
    assert "# Título" not in text  # sin marcas de Markdown
    assert "**" not in text
    assert "\x1b[" in text  # códigos de formato de terminal
