"""
Maqueta común de los documentos PDF del WMS (orden de compra, recepción, orden
de salida, hoja de picking, remisión de despacho y traslado).

Un documento es: encabezado con los datos de la empresa, título y número (con su
código de barras Code 39 para escanearlo en bodega), un recuadro de datos en dos
columnas, una o varias tablas con totales, notas, firmas y pie con la fecha de
generación y el número de página.

Usa DejaVu Sans (viene en el contenedor) para que tildes, eñes y símbolos salgan
bien; si no está, cae a Helvetica limpiando el texto a Latin-1.
"""
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

FUENTES = Path("/usr/share/fonts/truetype/dejavu")
INDIGO, TINTA, GRIS, BRUMA = (79, 70, 229), (11, 17, 32), (100, 116, 139), (241, 245, 249)


def num(v: Any, dec: int = 0) -> str:
    """Número en formato colombiano: 1.234.567,89."""
    if v is None or v == "":
        return "-"
    try:
        x = float(v)
    except (TypeError, ValueError):
        return str(v)
    if dec == 0 and abs(x - round(x)) < 1e-9:
        s = f"{round(x):,}"
    else:
        s = f"{x:,.{dec or 2}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def dinero(v: Any) -> str:
    return "-" if v is None else "$ " + num(v, 0 if float(v or 0) == round(float(v or 0)) else 2)


def fecha(v: Any, con_hora: bool = False) -> str:
    if not v:
        return "-"
    if isinstance(v, str):
        try:
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return v
    if isinstance(v, datetime) and v.tzinfo:
        from zoneinfo import ZoneInfo
        v = v.astimezone(ZoneInfo("America/Bogota"))     # en la base van en UTC
    if con_hora and isinstance(v, datetime):
        return v.strftime("%d/%m/%Y %H:%M")
    return v.strftime("%d/%m/%Y")


Columna = Tuple[str, float, str]          # (título, ancho relativo, alineación L/C/R)


def construir(*, empresa: Dict[str, Any], titulo: str, numero: str, estado: Optional[str] = None,
              datos: Sequence[Tuple[str, Any]] = (), tablas: Sequence[Dict[str, Any]] = (),
              notas: Optional[str] = None, firmas: Sequence[str] = (), usuario: Optional[str] = None,
              horizontal: bool = False) -> bytes:
    from fpdf import FPDF

    unicode = (FUENTES / "DejaVuSans.ttf").exists()

    def t(v: Any) -> str:
        s = "-" if v is None or v == "" else str(v)
        return s if unicode else s.encode("latin-1", "replace").decode("latin-1")

    generado = datetime.now().strftime("%d/%m/%Y %H:%M")

    class Doc(FPDF):
        def footer(self):
            self.set_y(-12)
            self.set_font(F, "", 7.5)
            self.set_text_color(*GRIS)
            self.cell(0, 5, t(f"{empresa.get('nombre', '')} · {titulo} {numero} · generado {generado}"
                              f"{' por ' + usuario if usuario else ''}"), align="L")
            self.cell(0, 5, f"Página {self.page_no()} de {{nb}}", align="R")

    pdf = Doc(orientation="L" if horizontal else "P", format="A4", unit="mm")
    if unicode:
        pdf.add_font("DejaVu", "", str(FUENTES / "DejaVuSans.ttf"))
        pdf.add_font("DejaVu", "B", str(FUENTES / "DejaVuSans-Bold.ttf"))
        F = "DejaVu"
    else:
        F = "Helvetica"
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(14, 14, 14)
    pdf.add_page()
    ancho = pdf.w - 28

    # ── Encabezado ──────────────────────────────────────────────────────────
    pdf.set_fill_color(*INDIGO)
    pdf.rect(0, 0, pdf.w, 4, style="F")
    pdf.set_xy(14, 9)
    pdf.set_font(F, "B", 13)
    pdf.set_text_color(*TINTA)
    pdf.cell(ancho * 0.58, 6, t(empresa.get("nombre")), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(F, "", 8)
    pdf.set_text_color(*GRIS)
    for linea in (f"NIT {empresa['nit']}" if empresa.get("nit") else None,
                  " · ".join(x for x in (empresa.get("direccion"), empresa.get("ciudad")) if x) or None,
                  " · ".join(x for x in (empresa.get("telefono"), empresa.get("email")) if x) or None):
        if linea:
            pdf.cell(ancho * 0.58, 4, t(linea), new_x="LMARGIN", new_y="NEXT")
    # Título, número y código de barras a la derecha
    xd = 14 + ancho * 0.58
    wd = ancho * 0.42
    pdf.set_xy(xd, 8)
    pdf.set_font(F, "B", 14)
    pdf.set_text_color(*INDIGO)
    pdf.cell(wd, 7, t(titulo.upper()), align="R", new_x="LEFT", new_y="NEXT")
    pdf.set_font(F, "B", 12)
    pdf.set_text_color(*TINTA)
    pdf.cell(wd, 6, t(f"N.º {numero}"), align="R", new_x="LEFT", new_y="NEXT")
    if estado:
        pdf.set_font(F, "", 8)
        pdf.set_text_color(*GRIS)
        pdf.cell(wd, 4.5, t(f"Estado: {estado}"), align="R", new_x="LEFT", new_y="NEXT")
    codigo = "".join(c for c in str(numero).upper() if c.isalnum() or c in "-. ")
    if codigo:
        # En fpdf2 `w` es la barra ANCHA (la angosta es w/3); cada carácter mide
        # 5w + el espacio w/3. Barra angosta de 0,25 mm: la lee cualquier lector.
        ancha = 0.75
        largo = (len(codigo) + 2) * (5 * ancha + ancha / 3) - ancha / 3
        try:
            pdf.set_fill_color(0, 0, 0)
            pdf.code39(f"*{codigo}*", x=14 + ancho - largo, y=pdf.get_y() + 1, w=ancha, h=9)
        except Exception:  # noqa: BLE001 — un código raro no debe impedir el documento
            pass
        pdf.set_y(pdf.get_y() + 1)
    pdf.set_y(max(pdf.get_y() + 11, 34))
    pdf.set_draw_color(*INDIGO)
    pdf.set_line_width(0.5)
    pdf.line(14, pdf.get_y(), 14 + ancho, pdf.get_y())
    pdf.ln(3)

    # ── Datos en dos columnas ───────────────────────────────────────────────
    if datos:
        pdf.set_fill_color(*BRUMA)
        y0 = pdf.get_y()
        mitad = (len(datos) + 1) // 2
        col_w = ancho / 2
        alto_fila = 5.2
        pdf.rect(14, y0, ancho, mitad * alto_fila + 3, style="F")
        for i, (etq, val) in enumerate(datos):
            col, fila = (0, i) if i < mitad else (1, i - mitad)
            pdf.set_xy(16 + col * col_w, y0 + 1.5 + fila * alto_fila)
            pdf.set_font(F, "B", 8)
            pdf.set_text_color(*GRIS)
            pdf.cell(32, alto_fila, t(etq))
            pdf.set_font(F, "", 8.5)
            pdf.set_text_color(*TINTA)
            valor = t(val)
            while pdf.get_string_width(valor) > col_w - 38 and len(valor) > 4:
                valor = valor[:-2]
            pdf.cell(col_w - 36, alto_fila, valor if valor == t(val) else valor + "…")
        pdf.set_y(y0 + mitad * alto_fila + 6)

    # ── Tablas ──────────────────────────────────────────────────────────────
    for tb in tablas:
        cols: List[Columna] = tb["columnas"]
        total_rel = sum(c[1] for c in cols)
        anchos = [ancho * c[1] / total_rel for c in cols]
        if tb.get("titulo"):
            if pdf.get_y() > pdf.h - 40:
                pdf.add_page()
            pdf.set_font(F, "B", 9.5)
            pdf.set_text_color(*INDIGO)
            pdf.cell(ancho, 6, t(tb["titulo"]), new_x="LMARGIN", new_y="NEXT")

        def cabecera():
            pdf.set_font(F, "B", 7.8)
            pdf.set_fill_color(*TINTA)
            pdf.set_text_color(255, 255, 255)
            for (tit, _, al), w in zip(cols, anchos):
                pdf.cell(w, 6.5, t(tit), fill=True, align=al)
            pdf.ln()

        cabecera()
        pdf.set_font(F, "", 8)
        pdf.set_text_color(*TINTA)
        for k, fila in enumerate(tb.get("filas", [])):
            textos = [t(v) for v in fila]
            # alto según la celda con más líneas
            lineas = 1
            for (tit, _, al), w, txt in zip(cols, anchos, textos):
                lineas = max(lineas, len(pdf.multi_cell(w, 4.6, txt, dry_run=True, output="LINES")))
            h = 4.6 * lineas + 1.4
            if pdf.get_y() + h > pdf.h - 20:
                pdf.add_page()
                cabecera()
                pdf.set_font(F, "", 8)
                pdf.set_text_color(*TINTA)
            y = pdf.get_y()
            if k % 2:
                pdf.set_fill_color(248, 250, 252)
                pdf.rect(14, y, ancho, h, style="F")
            x = 14
            for (tit, _, al), w, txt in zip(cols, anchos, textos):
                pdf.set_xy(x, y + 0.7)
                pdf.multi_cell(w, 4.6, txt, align=al)
                x += w
            pdf.set_xy(14, y + h)
            pdf.set_draw_color(226, 232, 240)
            pdf.set_line_width(0.2)
            pdf.line(14, y + h, 14 + ancho, y + h)
        if not tb.get("filas"):
            pdf.set_font(F, "", 8)
            pdf.set_text_color(*GRIS)
            pdf.cell(ancho, 7, "Sin líneas", align="C", new_x="LMARGIN", new_y="NEXT")
        for etq, val in tb.get("totales", []):
            pdf.set_font(F, "B", 9)
            pdf.set_text_color(*TINTA)
            pdf.cell(ancho - 45, 6.5, t(etq), align="R")
            pdf.set_text_color(*INDIGO)
            pdf.cell(45, 6.5, t(val), align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    # ── Notas ───────────────────────────────────────────────────────────────
    if notas:
        if pdf.get_y() > pdf.h - 40:
            pdf.add_page()
        pdf.set_font(F, "B", 8.5)
        pdf.set_text_color(*INDIGO)
        pdf.cell(ancho, 5, "Notas", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(F, "", 8.5)
        pdf.set_text_color(*TINTA)
        pdf.multi_cell(ancho, 4.6, t(notas))
        pdf.ln(3)

    # ── Firmas ──────────────────────────────────────────────────────────────
    if firmas:
        if pdf.get_y() > pdf.h - 42:
            pdf.add_page()
        pdf.ln(12)
        y = pdf.get_y()
        w = ancho / len(firmas)
        pdf.set_draw_color(*GRIS)
        pdf.set_line_width(0.3)
        for i, f in enumerate(firmas):
            x = 14 + i * w
            pdf.line(x + 6, y, x + w - 6, y)
            pdf.set_xy(x, y + 1)
            pdf.set_font(F, "B", 8)
            pdf.set_text_color(*TINTA)
            pdf.cell(w, 4.5, t(f), align="C")
            pdf.set_xy(x, y + 5.5)
            pdf.set_font(F, "", 7)
            pdf.set_text_color(*GRIS)
            pdf.cell(w, 4, "Nombre, documento y fecha", align="C")

    salida = BytesIO()
    pdf.output(salida)
    return salida.getvalue()
