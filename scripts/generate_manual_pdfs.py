"""Generate the AHG CONSTRUFERRET POS manuals as printable PDFs."""

from html import escape
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, Preformatted, SimpleDocTemplate, Spacer


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf"


def inline_markup(value: str) -> str:
    value = escape(value, quote=False)
    value = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", value)
    return value


def footer(canvas, document):
    canvas.saveState()
    width, _ = A4
    canvas.setStrokeColor(colors.HexColor("#d7e2e5"))
    canvas.line(18 * mm, 14 * mm, width - 18 * mm, 14 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#60777d"))
    canvas.drawString(18 * mm, 9 * mm, "AHG CONSTRUFERRET POS - Documento de apoyo")
    canvas.drawRightString(width - 18 * mm, 9 * mm, f"Pagina {document.page}")
    canvas.restoreState()


def make_pdf(markdown_path: Path, pdf_path: Path) -> None:
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "ManualTitle", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=22, leading=27, alignment=TA_CENTER, textColor=colors.HexColor("#075e68"),
        spaceAfter=12,
    )
    h2 = ParagraphStyle(
        "ManualH2", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=14, leading=18, textColor=colors.HexColor("#075e68"),
        spaceBefore=10, spaceAfter=6,
    )
    h3 = ParagraphStyle(
        "ManualH3", parent=styles["Heading3"], fontName="Helvetica-Bold",
        fontSize=11, leading=14, textColor=colors.HexColor("#174b52"),
        spaceBefore=7, spaceAfter=4,
    )
    body = ParagraphStyle(
        "ManualBody", parent=styles["BodyText"], fontName="Helvetica",
        fontSize=9.5, leading=13, textColor=colors.HexColor("#243b40"),
        spaceAfter=5,
    )
    bullet = ParagraphStyle("ManualBullet", parent=body, leftIndent=13, firstLineIndent=-8)
    code = ParagraphStyle(
        "ManualCode", parent=styles["Code"], fontName="Courier", fontSize=8,
        leading=10, backColor=colors.HexColor("#f1f5f5"), borderPadding=5,
        leftIndent=7, rightIndent=7, spaceAfter=5,
    )

    story = []
    lines = markdown_path.read_text(encoding="utf-8").splitlines()
    index = 0
    first_heading = True
    while index < len(lines):
        raw = lines[index]
        if not raw.strip():
            story.append(Spacer(1, 3))
            index += 1
            continue
        image_match = re.match(r"^!\[([^]]*)\]\(([^)]+)\)$", raw.strip())
        if image_match:
            image_path = (markdown_path.parent / image_match.group(2)).resolve()
            if image_path.exists():
                image = Image(str(image_path))
                # Mantener las capturas dentro del ancho útil y reservar espacio
                # para que su explicación no quede separada en otra página.
                max_width, max_height = 155 * mm, 150 * mm
                scale = min(max_width / image.imageWidth, max_height / image.imageHeight, 1)
                image.drawWidth = image.imageWidth * scale
                image.drawHeight = image.imageHeight * scale
                story.append(image)
                story.append(Paragraph(inline_markup(image_match.group(1)), body))
                story.append(Spacer(1, 5))
            index += 1
            continue
        if raw.startswith("    "):
            block = []
            while index < len(lines) and (lines[index].startswith("    ") or not lines[index].strip()):
                block.append(lines[index][4:] if lines[index].startswith("    ") else "")
                index += 1
            story.append(Preformatted("\n".join(block).rstrip(), code))
            continue
        match = re.match(r"^(#{1,3})\s+(.*)$", raw)
        if match:
            level, text = len(match.group(1)), match.group(2)
            if level == 1:
                story.append(Spacer(1, 28 * mm))
                story.append(Paragraph(inline_markup(text), title))
                story.append(Paragraph("Guia practica para instalar, operar y mantener el sistema.", body))
                story.append(Spacer(1, 20 * mm))
                story.append(Paragraph("Versión documentada: agosto de 2026", body))
                story.append(Spacer(1, 28 * mm))
                story.append(Paragraph("AHG CONSTRUFERRET POS", h2))
                story.append(Spacer(1, 8 * mm))
            else:
                story.append(Paragraph(inline_markup(text), h2 if level == 2 else h3))
            if first_heading:
                story.append(Spacer(1, 8 * mm))
                from reportlab.platypus import PageBreak
                story.append(PageBreak())
                first_heading = False
            index += 1
            continue
        if raw.startswith("- "):
            item = raw[2:]
            marker = "&#9744;" if item.startswith("[ ] ") else "&#8226;"
            if item.startswith("[ ] "):
                item = item[4:]
            story.append(Paragraph(f"{marker} {inline_markup(item)}", bullet))
        elif re.match(r"^\d+\.\s+", raw):
            story.append(Paragraph(inline_markup(raw), bullet))
        else:
            story.append(Paragraph(inline_markup(raw), body))
        index += 1

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(pdf_path), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=20 * mm, title=markdown_path.stem,
        author="AHG CONSTRUFERRET POS",
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    files = [
        (ROOT / "docs" / "manuales" / "MANUAL_INSTALACION.md", OUTPUT / "manual_instalacion_ahg_construferret_pos.pdf"),
        (ROOT / "docs" / "manuales" / "MANUAL_USUARIO.md", OUTPUT / "manual_usuario_ahg_construferret_pos.pdf"),
    ]
    for source, target in files:
        make_pdf(source, target)
        print(target)


if __name__ == "__main__":
    main()
