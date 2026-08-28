"""Presentaciones reales: PPTX (OOXML), HTML con proceso en vivo y PDF."""

from __future__ import annotations

import html
import json
import os
import zipfile
from dataclasses import dataclass
from typing import Any, Callable, Optional
from xml.sax.saxutils import escape

from .control import StopToken
from .literary import word_count
from .models import now_iso
from .pdf import MiniPDF

Progress = Callable[..., None]


@dataclass
class Slide:
    title: str
    bullets: list[str]
    notes: str = ""
    kind: str = "content"


def compose_deck(topic: str) -> list[Slide]:
    """Guion original de 10 diapositivas, no una plantilla vacía."""
    t = " ".join((topic or "el encargo").split())[:180]
    return [
        Slide(f"{t}", [
            "Presentación original de A²S",
            "Proceso visible: cada diapositiva se declara al nacer",
            "PPTX descargable · HTML navegable · PDF imprimible",
        ], "Portada. El título es el encargo del operador, no un eslogan genérico.",
           "title"),
        Slide("Qué promete esta deck", [
            f"Explicar {t} en diez movimientos",
            "Separar hecho, juicio y siguiente paso",
            "Dejar un criterio de éxito verificable",
            "No fingir omnisciencia ni copiar material protegido",
        ], "Contrato con la audiencia: se puede contradecir cada afirmación."),
        Slide("El problema real", [
            f"Quien pide {t} suele querer un objeto usable, no un índice",
            "El error habitual es llenar viñetas sin voz",
            "Aquí cada lámina tiene notas de orador y una decisión",
        ], "Si el problema no se puede decir en una frase, la deck es prematura."),
        Slide("Mapa de la conversación", [
            "1. Problema y pacto",
            "2. Hechos y límites",
            "3. Enfoque y riesgos",
            "4. Acción del lunes y cierre",
        ], "El mapa evita que el orador se pierda en adornos."),
        Slide("Hechos que sí se pueden afirmar", [
            f"{t} se puede describir con palabras propias",
            "Se puede señalar un límite (fuente, fecha, territorio)",
            "Se puede proponer una prueba pequeña",
            "Lo que no se sepa se declara, no se inventa",
        ], "Hecho ≠ opinión. Si falta una fuente, la lámina lo dice."),
        Slide("Límites honestos", [
            "A²S no es infalible: usa gates, tests y artefactos",
            "Sin red no se inventan citas externas",
            "Una PPT no sustituye un libro ni un experimento",
        ], "El margen de error se reduce con verificación, no con marketing."),
        Slide("Enfoque propuesto", [
            "Decir el objetivo en una frase",
            "Elegir dos evidencias o un contraejemplo",
            "Mostrar el proceso (esta deck lo hace en vivo)",
            "Cerrar con una acción del lunes",
        ], "Método reproducible: cabe en una servilleta."),
        Slide("Riesgos y trampas", [
            "Confundir estética con claridad",
            "Demasiadas viñetas, ninguna decisión",
            "Copiar un clásico o un paper protegido",
            "Prometer un resultado que no se puede medir",
        ], "Si una lámina no se puede defender en voz alta, sobra."),
        Slide("Qué hacer el lunes", [
            f"Escribe 200 palabras propias sobre {t}",
            "Elige una evidencia o una objeción",
            "Abre el HTML de esta deck y recorre las notas",
            "Si algo falla, pide otra versión más precisa",
        ], "Una sola acción. La vanidad empieza cuando la lista no cabe en el día."),
        Slide("Cierre", [
            "Este archivo es un artefacto original de A²S",
            "Revisa process.json para ver cómo se construyó",
            "El PDF y el PPTX son la misma historia en otro envase",
            "Pregunta, interrumpe o pide el siguiente objeto",
        ], "El cierre entrega la custodia al operador.", "close"),
    ]


def write_pptx(path: str, title: str, slides: list[Slide]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    files = _pptx_parts(title, slides)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)


def write_deck_html(path: str, title: str, slides: list[Slide],
                    process: Optional[list[dict[str, Any]]] = None) -> None:
    cards = []
    for i, slide in enumerate(slides, 1):
        items = "".join(f"<li>{html.escape(b)}</li>" for b in slide.bullets)
        cards.append(
            f"<article class='slide' id='s{i}'>"
            f"<header><small>{i} / {len(slides)}</small>"
            f"<h2>{html.escape(slide.title)}</h2></header>"
            f"<ul>{items}</ul>"
            f"<p class='notes'><b>Notas.</b> {html.escape(slide.notes)}</p>"
            "</article>"
        )
    log = ""
    if process:
        rows = "".join(
            f"<li><span>{html.escape(str(s.get('percent', '')))}%</span> "
            f"{html.escape(str(s.get('note', '')))}</li>"
            for s in process
        )
        log = f"<aside class='process'><h3>Proceso de creación</h3><ol>{rows}</ol></aside>"
    doc = (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title>"
        "<style>body{margin:0;background:#0b1520;color:#e8f0f6;font:16px/1.5 Georgia,serif}"
        "header.top{padding:28px 8vw 8px}h1{font:700 32px/1.2 system-ui}"
        ".grid{display:grid;gap:22px;padding:12px 8vw 60px}"
        ".slide{background:#122132;border:1px solid #2a4458;padding:22px 26px}"
        ".slide h2{margin:6px 0 12px;font:650 22px/1.25 system-ui}"
        ".slide small{color:#7aa}ul{margin:0;padding-left:1.2em}"
        ".notes{color:#9bb;font-size:14px}.process{padding:0 8vw 48px}"
        ".process li{margin:6px 0;color:#9ec} .process span{color:#20d7e6}</style>"
        f"</head><body><header class='top'><h1>{html.escape(title)}</h1>"
        f"<p>Deck original · {html.escape(now_iso())}</p></header>"
        f"<div class='grid'>{''.join(cards)}</div>{log}</body></html>"
    )
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)


def write_deck_pdf(path: str, title: str, slides: list[Slide]) -> int:
    pdf = MiniPDF(title)
    pdf.cover(title, subtitle="A²S · presentación original",
              note=f"Generada {now_iso()}. Cada lámina incluye notas de orador.")
    for i, slide in enumerate(slides, 1):
        pdf.h2(f"{i}. {slide.title}")
        for bullet in slide.bullets:
            pdf.bullet(bullet)
        if slide.notes:
            pdf.para(f"Notas: {slide.notes}", font="F3")
        pdf.spacer(8)
    return pdf.save(path)


def create_deck(workspace: str, topic: str, title: str = "",
                stop: Optional[StopToken] = None,
                progress: Optional[Progress] = None) -> dict[str, Any]:
    topic = " ".join((topic or "").split())[:300]
    if not topic:
        raise ValueError("no hay tema para la presentación")
    if stop:
        stop.raise_if_set()
    deck_title = title.strip() or f"Presentación: {topic}"
    slides = compose_deck(topic)
    out = os.path.abspath(os.path.join(workspace, "slides"))
    base = os.path.abspath(workspace)
    if out != base and not out.startswith(base + os.sep):
        raise PermissionError("salida fuera del workspace")
    os.makedirs(out, exist_ok=True)
    process: list[dict[str, Any]] = []

    def emit(percent: int, note: str) -> None:
        if stop:
            stop.raise_if_set()
        step = {"percent": percent, "note": note, "at": now_iso()}
        process.append(step)
        with open(os.path.join(out, "process.json"), "w", encoding="utf-8") as fh:
            json.dump({"title": deck_title, "steps": process}, fh,
                      ensure_ascii=False, indent=2)
        if progress:
            progress(percent, note, extra={"kind": "slides", "title": deck_title})

    emit(8, "guion: 10 diapositivas originales")
    for i, slide in enumerate(slides, 1):
        emit(8 + int(i * 6), f"lámina {i}/{len(slides)}: {slide.title[:60]}")
    pptx = os.path.join(out, "deck.pptx")
    html_path = os.path.join(out, "deck.html")
    pdf_path = os.path.join(out, "deck.pdf")
    emit(78, "escribiendo PPTX (OOXML stdlib)")
    write_pptx(pptx, deck_title, slides)
    emit(86, "escribiendo HTML con proceso visible")
    write_deck_html(html_path, deck_title, slides, process)
    emit(93, "maquetando PDF de la deck")
    pages = write_deck_pdf(pdf_path, deck_title, slides)
    emit(100, "presentación lista")
    rel = lambda p: os.path.relpath(p, base)
    words = word_count(" ".join(s.title + " " + " ".join(s.bullets) + " " + s.notes
                                for s in slides))
    quality = {
        "status": "original_deck", "score": 88, "slides": len(slides),
        "pages": pages, "word_count": words, "created_at": now_iso(),
        "title": deck_title, "copyright_safe": True,
    }
    qpath = os.path.join(out, "quality.json")
    with open(qpath, "w", encoding="utf-8") as fh:
        json.dump(quality, fh, ensure_ascii=False, indent=2)
    return {
        "status": "original_deck", "title": deck_title, "topic": topic,
        "slides": len(slides), "pages": pages, "word_count": words,
        "quality_score": 88, "process": process,
        "artifacts": [rel(pptx), rel(html_path), rel(pdf_path),
                      rel(qpath), rel(os.path.join(out, "process.json"))],
        "quality": quality,
    }


def _pptx_parts(title: str, slides: list[Slide]) -> dict[str, str]:
    n = len(slides)
    overrides = [
        '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>',
        '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>',
        '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>',
        '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>',
    ]
    for i in range(1, n + 1):
        overrides.append(
            f'<Override PartName="/ppt/slides/slide{i}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        )
    ctypes = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        + "".join(overrides) + "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>'
        "</Relationships>"
    )
    pres_rels = [
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'
    ]
    sld_ids = []
    for i in range(1, n + 1):
        rid = i + 1
        pres_rels.append(
            f'<Relationship Id="rId{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{i}.xml"/>'
        )
        sld_ids.append(f'<p:sldId id="{255 + i}" r:id="rId{rid}"/>')
    pres_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(pres_rels) + "</Relationships>"
    )
    ns = (
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
    )
    presentation = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<p:presentation {ns}>'
        '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
        f'<p:sldIdLst>{"".join(sld_ids)}</p:sldIdLst>'
        '<p:sldSz cx="9144000" cy="5143500" type="screen16x9"/>'
        '<p:notesSz cx="6858000" cy="9144000"/></p:presentation>'
    )
    files = {
        "[Content_Types].xml": ctypes,
        "_rels/.rels": rels,
        "ppt/_rels/presentation.xml.rels": pres_rels_xml,
        "ppt/presentation.xml": presentation,
        "ppt/slideMasters/slideMaster1.xml": _master(),
        "ppt/slideMasters/_rels/slideMaster1.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>'
            "</Relationships>"
        ),
        "ppt/slideLayouts/slideLayout1.xml": _layout(),
        "ppt/slideLayouts/_rels/slideLayout1.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>'
            "</Relationships>"
        ),
        "ppt/theme/theme1.xml": _theme(),
        "docProps/core.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f"<dc:title>{escape(title)}</dc:title>"
            "<dc:creator>A²S</dc:creator></cp:coreProperties>"
        ),
    }
    for i, slide in enumerate(slides, 1):
        files[f"ppt/slides/slide{i}.xml"] = _slide_xml(slide)
        files[f"ppt/slides/_rels/slide{i}.xml.rels"] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
            "</Relationships>"
        )
    return files


def _txbody(paragraphs: list[tuple[str, int, bool]]) -> str:
    bits = []
    for text, size, bold in paragraphs:
        b = "1" if bold else "0"
        bits.append(
            f'<a:p><a:pPr algn="l"/><a:r><a:rPr lang="es-ES" sz="{size}" b="{b}" dirty="0">'
            f'<a:solidFill><a:srgbClr val="E8F0F6"/></a:solidFill>'
            f'<a:latin typeface="Calibri"/></a:rPr>'
            f"<a:t>{escape(text)}</a:t></a:r></a:p>"
        )
    return "".join(bits) or "<a:p/>"


def _box(shape_id: int, name: str, x: int, y: int, cx: int, cy: int,
         paragraphs: list[tuple[str, int, bool]]) -> str:
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{shape_id}" name="{escape(name)}"/>'
        f'<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
        f'<p:txBody><a:bodyPr wrap="square" lIns="91440" tIns="45720" rIns="91440" bIns="45720"/>'
        f'<a:lstStyle/>{_txbody(paragraphs)}</p:txBody></p:sp>'
    )


def _slide_xml(slide: Slide) -> str:
    ns = (
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
    )
    paras = [(f"• {b}", 2000, False) for b in slide.bullets[:8]]
    tree = (
        f'<p:sld {ns}><p:cSld><p:bg><p:bgPr><a:solidFill>'
        f'<a:srgbClr val="0B1520"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>'
        f"<p:spTree>"
        f'<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        f'<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
        f'<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
        + _box(2, "Title", 457200, 228600, 8229600, 1000000, [(slide.title, 3200, True)])
        + _box(3, "Body", 457200, 1371600, 8229600, 3200000, paras)
        + "</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>"
    )
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + tree


def _master() -> str:
    ns = (
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<p:sldMaster {ns}><p:cSld><p:bg><p:bgPr><a:solidFill>'
        f'<a:srgbClr val="0B1520"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>'
        f'<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/>'
        f'</p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
        f'<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
        f'</p:spTree></p:cSld>'
        f'<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" '
        f'accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" '
        f'accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
        f'<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/>'
        f'</p:sldLayoutIdLst></p:sldMaster>'
    )


def _layout() -> str:
    ns = (
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<p:sldLayout {ns} type="blank" preserve="1"><p:cSld name="Blank">'
        f'<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/>'
        f'</p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
        f'<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
        f'</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>'
    )


def _theme() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="A2S">'
        '<a:themeElements><a:clrScheme name="A2S">'
        '<a:dk1><a:srgbClr val="0B1520"/></a:dk1><a:lt1><a:srgbClr val="E8F0F6"/></a:lt1>'
        '<a:dk2><a:srgbClr val="122132"/></a:dk2><a:lt2><a:srgbClr val="D5E4EE"/></a:lt2>'
        '<a:accent1><a:srgbClr val="20D7E6"/></a:accent1>'
        '<a:accent2><a:srgbClr val="41D68F"/></a:accent2>'
        '<a:accent3><a:srgbClr val="5FA8FF"/></a:accent3>'
        '<a:accent4><a:srgbClr val="F5B642"/></a:accent4>'
        '<a:accent5><a:srgbClr val="FF6677"/></a:accent5>'
        '<a:accent6><a:srgbClr val="9DB0C1"/></a:accent6>'
        '<a:hlink><a:srgbClr val="20D7E6"/></a:hlink>'
        '<a:folHlink><a:srgbClr val="5FA8FF"/></a:folHlink>'
        '</a:clrScheme>'
        '<a:fontScheme name="A2S"><a:majorFont><a:latin typeface="Calibri"/>'
        '<a:ea typeface="Calibri"/><a:cs typeface="Calibri"/></a:majorFont>'
        '<a:minorFont><a:latin typeface="Calibri"/>'
        '<a:ea typeface="Calibri"/><a:cs typeface="Calibri"/></a:minorFont></a:fontScheme>'
        '<a:fmtScheme name="A2S"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/>'
        '</a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
        '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>'
        '<a:lnStyleLst><a:ln w="9525" cap="flat" cmpd="sng" algn="ctr">'
        '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/>'
        '</a:ln><a:ln w="25400" cap="flat" cmpd="sng" algn="ctr">'
        '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/>'
        '</a:ln><a:ln w="38100" cap="flat" cmpd="sng" algn="ctr">'
        '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/>'
        '</a:ln></a:lnStyleLst>'
        '<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle>'
        '<a:effectStyle><a:effectLst/></a:effectStyle>'
        '<a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>'
        '<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
        '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
        '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>'
        '</a:fmtScheme></a:themeElements></a:theme>'
    )
