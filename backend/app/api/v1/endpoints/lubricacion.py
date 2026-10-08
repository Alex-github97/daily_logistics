"""Lubricación — lector de boletines de análisis de aceite (motor propio, local).

NO usa ningún LLM ni servicio externo. Extrae los parámetros del boletín con:
  1) Texto del documento — pdfplumber para PDF digital, Tesseract OCR para foto/escaneo/PDF escaneado.
  2) Motor de reglas propio: un diccionario de sinónimos por campo + proximidad etiqueta→valor.
El diccionario de sinónimos es editable desde la app (CMMS → Config → IA/OCR de Lubricación)
y se guarda en disco; ese diccionario ES el "modelo" propio de la herramienta.

Endpoints:
  POST   /lubricacion/ocr        -> lee un boletín (imagen/PDF) y devuelve los campos tabulados
  GET    /lubricacion/config     -> diccionario de sinónimos (por defecto + overrides) + etiquetas
  PUT    /lubricacion/config     -> guarda overrides del diccionario de sinónimos
"""
import io
import re
import json
import unicodedata
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.infrastructure.models.usuario import Usuario

router = APIRouter(prefix="/lubricacion", tags=["Lubricación OCR"])

CONFIG_DIR = Path(__file__).parents[4] / "uploads" / "lube_ocr"
OVERRIDES_PATH = CONFIG_DIR / "sinonimos.json"

# Etiqueta legible por campo (para el editor del diccionario en el frontend).
LABELS: dict[str, str] = {
    "activo": "Activo / equipo", "componente": "Componente", "lubricante": "Lubricante",
    "fecha": "Fecha de muestra", "horas": "Horas / km", "laboratorio": "Laboratorio", "muestra_id": "N.º muestra",
    "fe": "Hierro (Fe)", "cr": "Cromo (Cr)", "pb": "Plomo (Pb)", "cu": "Cobre (Cu)",
    "sn": "Estaño (Sn)", "al": "Aluminio (Al)", "ni": "Níquel (Ni)", "mo": "Molibdeno (Mo)",
    "si": "Silicio (Si)", "na": "Sodio (Na)", "k": "Potasio (K)", "agua": "Agua",
    "combustible": "Combustible", "hollin": "Hollín", "glicol": "Glicol",
    "ca": "Calcio (Ca)", "mg": "Magnesio (Mg)", "zn": "Zinc (Zn)", "p": "Fósforo (P)",
    "b": "Boro (B)", "ba": "Bario (Ba)",
    "viscosidad": "Viscosidad 40°C", "visc100": "Viscosidad 100°C", "indice_viscosidad": "Índice de viscosidad",
    "tbn": "TBN", "tan": "TAN", "oxidacion": "Oxidación", "nitracion": "Nitración", "sulfatacion": "Sulfatación",
    "iso4406": "Código ISO 4406", "pq": "Índice PQ",
    "severidad": "Estado / severidad", "recomendacion": "Recomendación",
}
CAMPOS: list[str] = list(LABELS.keys())

# Diccionario de sinónimos por defecto. El usuario puede sobreescribirlo desde la app.
SINONIMOS_DEFAULT: dict[str, list[str]] = {
    "activo": ["activo", "equipo", "unidad", "placa", "vehiculo", "tag", "asset", "identificacion equipo"],
    "componente": ["componente", "sistema", "compartimiento", "compartimento", "component"],
    "lubricante": ["lubricante", "aceite", "producto", "oil", "lubricant", "marca aceite"],
    "fecha": ["fecha", "fecha muestra", "fecha de muestreo", "date", "sampled"],
    "horas": ["horas", "hrs", "horas aceite", "horas de uso", "km", "kilometraje", "odometro", "hours", "oil hours"],
    "laboratorio": ["laboratorio", "lab", "laboratory"],
    "muestra_id": ["muestra", "no muestra", "numero de muestra", "sample", "boletin", "informe", "reporte", "report no", "sample no"],
    "fe": ["hierro", "fe", "iron"], "cr": ["cromo", "cr", "chromium"], "pb": ["plomo", "pb", "lead"],
    "cu": ["cobre", "cu", "copper"], "sn": ["estano", "estaño", "sn", "tin"], "al": ["aluminio", "al", "aluminum", "aluminium"],
    "ni": ["niquel", "níquel", "ni", "nickel"], "mo": ["molibdeno", "mo", "molybdenum"],
    "si": ["silicio", "si", "silicon"], "na": ["sodio", "na", "sodium"], "k": ["potasio", "k", "potassium"],
    "agua": ["agua", "water", "h2o", "humedad", "contenido de agua"],
    "combustible": ["combustible", "dilucion combustible", "dilución", "fuel", "fuel dilution"],
    "hollin": ["hollin", "hollín", "soot"], "glicol": ["glicol", "glycol", "anticongelante", "coolant"],
    "ca": ["calcio", "ca", "calcium"], "mg": ["magnesio", "mg", "magnesium"], "zn": ["zinc", "zn"],
    "p": ["fosforo", "fósforo", "phosphorus"], "b": ["boro", "boron"], "ba": ["bario", "ba", "barium"],
    "viscosidad": ["viscosidad 40", "viscosidad a 40", "viscosity 40", "visc 40", "kv40", "cst 40", "40 c", "40°c"],
    "visc100": ["viscosidad 100", "viscosidad a 100", "viscosity 100", "visc 100", "kv100", "cst 100", "100 c", "100°c"],
    "indice_viscosidad": ["indice de viscosidad", "índice de viscosidad", "viscosity index", "indice viscosidad"],
    "tbn": ["tbn", "numero basico total", "número básico total", "base number", "nbt"],
    "tan": ["tan", "numero acido total", "número ácido total", "acid number", "nat"],
    "oxidacion": ["oxidacion", "oxidación", "oxidation"], "nitracion": ["nitracion", "nitración", "nitration"],
    "sulfatacion": ["sulfatacion", "sulfatación", "sulfation"],
    "iso4406": ["iso 4406", "iso4406", "codigo iso", "código iso", "limpieza iso", "cleanliness", "iso code"],
    "pq": ["pq", "indice pq", "índice pq", "pq index", "ferrous index"],
    "severidad": ["severidad", "estado", "condicion", "condición", "diagnostico", "diagnóstico", "evaluacion", "severity", "status"],
    "recomendacion": ["recomendacion", "recomendación", "comentario", "observaciones", "recommendation", "comments"],
}

# Clasificación de campos por tipo de valor a extraer.
NUM_FIELDS = {"horas", "fe", "cr", "pb", "cu", "sn", "al", "ni", "mo", "si", "na", "k",
              "agua", "combustible", "hollin", "ca", "mg", "zn", "p", "b", "ba",
              "viscosidad", "visc100", "indice_viscosidad", "tbn", "tan",
              "oxidacion", "nitracion", "sulfatacion", "pq"}
TEXT_FIELDS = {"activo", "componente", "lubricante", "laboratorio", "muestra_id", "glicol", "severidad", "recomendacion"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s.lower()).strip()


def _ensure_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _load_overrides() -> dict[str, list[str]]:
    try:
        return json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _sinonimos() -> dict[str, list[str]]:
    merged = {k: list(v) for k, v in SINONIMOS_DEFAULT.items()}
    for k, v in _load_overrides().items():
        if k in merged and isinstance(v, list) and v:
            merged[k] = [str(x) for x in v]
    return merged


def _first_number(s: str) -> str:
    m = re.search(r"[-+]?\d[\d.,]*\d|\d", s)
    if not m:
        return ""
    tok = m.group(0)
    if "," in tok and "." in tok:
        tok = tok.replace(".", "").replace(",", ".") if tok.rfind(",") > tok.rfind(".") else tok.replace(",", "")
    elif "," in tok:
        tok = tok.replace(",", ".") if (tok.count(",") == 1 and len(tok.split(",")[1]) <= 2) else tok.replace(",", "")
    return tok


def _extract_text(content: bytes, filename: str, content_type: str | None) -> str:
    ext = Path(filename or "").suffix.lower()
    is_pdf = ext == ".pdf" or (content_type or "").endswith("pdf")

    if is_pdf:
        # 1) Texto nativo del PDF (digital)
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                txt = "\n".join((page.extract_text() or "") for page in pdf.pages)
            if len(txt.strip()) >= 40:
                return txt
        except Exception:
            pass
        # 2) PDF escaneado -> imágenes -> OCR
        try:
            from pdf2image import convert_from_bytes
            import pytesseract
            pages = convert_from_bytes(content, dpi=200)
            return "\n".join(pytesseract.image_to_string(p, lang="spa+eng") for p in pages)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"No se pudo leer el PDF (OCR no disponible): {e}")

    # Imagen (foto/escaneo)
    try:
        from PIL import Image
        import pytesseract
        img = Image.open(io.BytesIO(content))
        return pytesseract.image_to_string(img, lang="spa+eng")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"No se pudo leer la imagen (OCR no disponible en el servidor): {e}")


def _find_numeric(norm_lines: list[str], aliases: list[str]) -> str:
    for alias in sorted(aliases, key=len, reverse=True):
        a = _norm(alias)
        if not a:
            continue
        pat = re.compile(r"(?<![a-z0-9])" + re.escape(a) + r"(?![a-z0-9])(.*)$")
        for ln in norm_lines:
            m = pat.search(ln)
            if m:
                val = _first_number(m.group(1))
                if val:
                    return val
    return ""


def _find_text(raw_lines: list[str], aliases: list[str]) -> str:
    norm_aliases = [_norm(a) for a in aliases if a.strip()]
    for raw in raw_lines:
        if ":" not in raw:
            continue
        left, right = raw.split(":", 1)
        nl = _norm(left)
        if any(a and a in nl for a in norm_aliases) and right.strip():
            return right.strip()[:80]
    return ""


def _extract_date(text: str) -> str:
    m = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b", text)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return ""


def _extract_fields(text: str) -> dict[str, str]:
    sinon = _sinonimos()
    raw_lines = [ln for ln in text.splitlines() if ln.strip()]
    norm_lines = [_norm(ln) for ln in raw_lines]
    norm_text = _norm(text)

    out: dict[str, str] = {k: "" for k in CAMPOS}

    for campo in CAMPOS:
        aliases = sinon.get(campo, [])
        if campo == "fecha":
            out[campo] = _extract_date(text)
        elif campo == "iso4406":
            m = re.search(r"\b\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{1,2}\b", norm_text)
            out[campo] = m.group(0).replace(" ", "") if m else ""
        elif campo in NUM_FIELDS:
            out[campo] = _find_numeric(norm_lines, aliases)
        elif campo in TEXT_FIELDS:
            out[campo] = _find_text(raw_lines, aliases)
    return out


@router.post("/ocr")
async def leer_boletin(
    file: UploadFile = File(...),
    current_user: Usuario = Depends(get_current_user),
):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Archivo vacío")
    text = _extract_text(content, file.filename or "", file.content_type)
    campos = _extract_fields(text)
    detectados = sum(1 for v in campos.values() if v)
    return {
        "campos": campos,
        "motor": "ocr-local",
        "campos_detectados": detectados,
        "texto_chars": len(text),
    }


@router.get("/config")
async def obtener_config(current_user: Usuario = Depends(get_current_user)):
    """Diccionario de sinónimos (por defecto + overrides) y etiquetas de cada campo."""
    return {"campos": CAMPOS, "labels": LABELS, "sinonimos": _sinonimos(),
            "num_fields": sorted(NUM_FIELDS), "text_fields": sorted(TEXT_FIELDS)}


class ConfigIn(BaseModel):
    sinonimos: dict[str, list[str]]


@router.put("/config")
async def guardar_config(body: ConfigIn, current_user: Usuario = Depends(get_current_user)):
    """Guarda overrides del diccionario de sinónimos (solo campos conocidos)."""
    _ensure_dir()
    limpio = {
        k: [str(x).strip() for x in v if str(x).strip()]
        for k, v in body.sinonimos.items()
        if k in LABELS and isinstance(v, list)
    }
    OVERRIDES_PATH.write_text(json.dumps(limpio, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "campos_configurados": len(limpio)}
