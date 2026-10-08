"""
El informe de causa raíz en PDF, con las evidencias embebidas.

Se arma en el servidor y no en el navegador porque hay que incrustar las
imágenes: hacerlo del lado del cliente obligaría a descargar cada evidencia
primero, y el resultado dependería del navegador de turno.

Va en su propio módulo porque maquetar un documento es harina de otro costal que
guardar un formulario, y mezclarlos hace ilegibles a los dos.
"""
import os
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, List, Optional

from app.core.config import settings
from app.infrastructure.models.eam import (
    EAMActivo, EAMCausaRaiz, EAMCausaRaizAccion, EAMCausaRaizEvidencia,
)

IMAGENES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}

METODOLOGIA_TEXTO = {
    "CINCO_PORQUES": "Cinco porques",
    "ISHIKAWA": "Ishikawa (espina de pescado)",
    "ARBOL_FALLOS": "Arbol de fallos",
    "OTRA": "Otra",
}


def _limpio(valor: Any) -> str:
    """A texto imprimible por la fuente base de fpdf.

    Las fuentes incrustadas por defecto son Latin-1; un carácter fuera de ese
    juego —una comilla tipográfica pegada desde Word, un emoji— aborta la
    generación entera. Se sustituye en vez de fallar: es preferible un informe
    con un guion raro a no tener informe.
    """
    if valor is None or valor == "":
        return "-"
    texto = str(valor).replace("\r", "")
    reemplazos = {
        "‘": "'", "’": "'", "“": '"', "”": '"',
        "–": "-", "—": "-", "…": "...", " ": " ",
        "·": "-",
    }
    for viejo, nuevo in reemplazos.items():
        texto = texto.replace(viejo, nuevo)
    return texto.encode("latin-1", "replace").decode("latin-1")


def construir(
    rca: EAMCausaRaiz,
    activo: Optional[EAMActivo],
    acciones: List[EAMCausaRaizAccion],
    evidencias: List[EAMCausaRaizEvidencia],
) -> BytesIO:
    from fpdf import FPDF

    pdf = FPDF(format="A4", unit="mm")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(16, 16, 16)
    pdf.add_page()
    ancho = pdf.w - 32

    def titulo(texto: str):
        if pdf.get_y() > pdf.h - 40:
            pdf.add_page()
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_fill_color(26, 26, 26)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(ancho, 8, "  " + _limpio(texto), fill=True,
                 new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2.5)

    def campo(etiqueta: str, valor: Any, w: float = 46):
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(w, 5.5, _limpio(etiqueta))
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(ancho - w, 5.5, _limpio(valor), new_x="LMARGIN", new_y="NEXT")

    def parrafo(etiqueta: str, valor: Any):
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(ancho, 5.5, _limpio(etiqueta), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(ancho, 5, _limpio(valor), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1.5)

    # ── Encabezado ──
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(ancho, 9, "Informe de analisis de causa raiz",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(ancho, 6, "Orden de trabajo " + _limpio(rca.ot_numero),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    titulo("Identificacion")
    campo("Orden de trabajo", rca.ot_numero)
    if activo:
        campo("Activo", f"{activo.codigo} - {activo.nombre}")
        jerarquia = " / ".join(
            x for x in [activo.marca, activo.linea, activo.modelo] if x)
        campo("Marca / linea / modelo", jerarquia or "-")
        campo("Tipo de activo", activo.tipo_activo)
    campo("Fecha del analisis", rca.fecha_analisis)
    campo("Analista", rca.analista)
    campo("Participantes", rca.participantes)
    campo("Metodologia", METODOLOGIA_TEXTO.get(rca.metodologia or "", rca.metodologia))
    campo("Estado", rca.estado)
    pdf.ln(2)

    titulo("Descripcion del evento")
    parrafo("Que ocurrio", rca.descripcion_evento)
    parrafo("Como se detecto", rca.deteccion)
    campo("Modo de falla", rca.modo_falla)
    campo("Categoria de causa", rca.categoria_causa)
    pdf.ln(2)

    titulo("Consecuencias")
    campo("Horas de parada", rca.horas_parada)
    costo = (f"$ {rca.costo_estimado:,.0f}".replace(",", ".")
             if rca.costo_estimado else "-")
    campo("Costo estimado", costo)
    campo("Hubo lesion", "Si" if rca.hubo_lesion else "No")
    campo("Impacto ambiental", "Si" if rca.hubo_ambiental else "No")
    pdf.ln(2)

    titulo("Analisis")
    porques = rca.porques or []
    if porques:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(ancho, 5.5, "Secuencia de porques", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        for i, p in enumerate(porques, 1):
            pregunta = (p or {}).get("pregunta") or f"Por que? ({i})"
            respuesta = (p or {}).get("respuesta") or ""
            pdf.multi_cell(ancho, 5, f"{i}. {_limpio(pregunta)}\n     {_limpio(respuesta)}",
                           new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1.5)
    parrafo("Causa inmediata", rca.causa_inmediata)
    parrafo("Causa raiz", rca.causa_raiz)
    parrafo("Factores contribuyentes", rca.factores_contribuyentes)

    # ── Acciones ──
    titulo("Acciones")
    if not acciones:
        pdf.set_font("Helvetica", "I", 9)
        pdf.multi_cell(ancho, 5, "Sin acciones registradas.",
                       new_x="LMARGIN", new_y="NEXT")
    else:
        columnas = [("Tipo", 24), ("Accion", 76), ("Responsable", 32),
                    ("Compromiso", 24), ("Estado", 22)]
        pdf.set_font("Helvetica", "B", 8.5)
        for etiqueta, w in columnas:
            pdf.cell(w, 6, etiqueta, border="B")
        pdf.ln()
        pdf.set_font("Helvetica", "", 8.5)
        for a in acciones:
            texto = _limpio(a.descripcion)
            # Alto aproximado por número de líneas, para reservar el espacio
            # antes de escribir y no partir una fila entre dos páginas.
            lineas = max(1, len(texto) // 48 + texto.count("\n") + 1)
            alto = lineas * 4.6
            if pdf.get_y() + alto > pdf.h - 22:
                pdf.add_page()
            y0, x0 = pdf.get_y(), pdf.l_margin
            pdf.set_xy(x0, y0)
            pdf.multi_cell(24, 4.6, _limpio(a.tipo)[:14])
            pdf.set_xy(x0 + 24, y0)
            pdf.multi_cell(76, 4.6, texto)
            y_fin = pdf.get_y()
            pdf.set_xy(x0 + 100, y0); pdf.multi_cell(32, 4.6, _limpio(a.responsable))
            pdf.set_xy(x0 + 132, y0); pdf.multi_cell(24, 4.6, _limpio(a.fecha_compromiso))
            pdf.set_xy(x0 + 156, y0); pdf.multi_cell(22, 4.6, _limpio(a.estado))
            pdf.set_y(max(y_fin, y0 + 4.6) + 1.2)
    pdf.ln(2)

    titulo("Conclusiones y verificacion")
    parrafo("Conclusiones", rca.conclusiones)
    parrafo("Verificacion de eficacia", rca.verificacion_eficacia)
    campo("Fecha de verificacion", rca.fecha_verificacion)
    campo("Fue eficaz?",
          "Si" if rca.eficaz else ("No" if rca.eficaz is False else "Sin verificar"))

    # ── Evidencias ──
    imagenes = [e for e in evidencias
                if os.path.splitext(e.nombre)[1].lower() in IMAGENES]
    otras = [e for e in evidencias if e not in imagenes]

    if evidencias:
        pdf.add_page()
        titulo("Evidencias")
        for i, e in enumerate(imagenes, 1):
            ruta = Path(settings.UPLOAD_DIR) / e.ruta
            if not ruta.exists():
                continue
            if pdf.get_y() > pdf.h - 105:
                pdf.add_page()
            pdf.set_font("Helvetica", "B", 9)
            pdf.multi_cell(ancho, 5.5, f"Evidencia {i}: {_limpio(e.nombre)}",
                           new_x="LMARGIN", new_y="NEXT")
            if e.descripcion:
                pdf.set_font("Helvetica", "", 9)
                pdf.multi_cell(ancho, 5, _limpio(e.descripcion),
                               new_x="LMARGIN", new_y="NEXT")
            try:
                # Se acota el ancho para que una foto vertical no ocupe tres
                # páginas ella sola.
                pdf.image(str(ruta), w=min(ancho, 128))
            except Exception:
                # Un archivo corrupto o un formato que la librería no abre no
                # debe impedir que salga el resto del informe.
                pdf.set_font("Helvetica", "I", 8.5)
                pdf.multi_cell(
                    ancho, 5,
                    "(No se pudo incrustar esta imagen; queda adjunta al analisis.)",
                    new_x="LMARGIN", new_y="NEXT")
            pdf.ln(4)

        if otras:
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 9)
            pdf.multi_cell(ancho, 5.5, "Otras evidencias adjuntas",
                           new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 9)
            for e in otras:
                linea = "- " + _limpio(e.nombre)
                if e.descripcion:
                    linea += " - " + _limpio(e.descripcion)
                pdf.multi_cell(ancho, 5, linea, new_x="LMARGIN", new_y="NEXT")

    pdf.set_y(-15)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(130, 130, 130)
    pdf.cell(ancho, 5,
             f"Elaborado por {_limpio(rca.elaborado_por)} - "
             f"generado el {datetime.now():%d/%m/%Y %H:%M}", align="C")

    return BytesIO(bytes(pdf.output()))
