from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple

os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")

import tkinter as tk
from tkinter import filedialog, messagebox


AUTHOR_NAME = "Yashashchandra Kollu"
EMAIL = "yashashchandrakollu1@gmail.com"
PHONE = "+1 (205) 897 7790"
PHONE_LINK = "tel:+1%20(205)%20897%207790"
LOCATION = "Atlanta, GA"
DEFAULT_OUTPUT = "Yashashchandra_Kollu_Resume.docx"

FONT_CHOICES = (
    "Arial",
    "Calibri",
    "Cambria",
    "Garamond",
    "Georgia",
    "Times New Roman",
    "Verdana",
)
NAME_SIZE_CHOICES = ("14", "15", "16", "17", "18", "20")
HEADING_SIZE_CHOICES = ("11", "12", "13", "14")
BODY_SIZE_CHOICES = ("10", "11", "12")
MONTH_PATTERN = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)
DATE_RANGE_RE = re.compile(
    rf"\b(?:{MONTH_PATTERN})\s+\d{{4}}\s*(?:-|–|—|to)\s*(?:Present|Current|(?:{MONTH_PATTERN})\s+\d{{4}})\b",
    re.IGNORECASE,
)
KNOWN_EXPERIENCE_DATES = (
    ("first horizon bank", "January 2025 – May 2026"),
    ("aws cloud ai devops engineer", "January 2025 – May 2026"),
    ("software engineer", "January 2025 – May 2026"),
    ("dbs tech india", "July 2022 – July 2024"),
    ("software developer full stack (sdeii)", "September 2023 – July 2024"),
    ("software developer (sde ii)", "September 2023 – July 2024"),
    ("software developer (sde i)", "July 2022 – September 2023"),
    ("value labs", "February 2021 – March 2022"),
    ("software developer – devops", "February 2021 – March 2022"),
    ("software developer - devops", "February 2021 – March 2022"),
)

APP_BG = "#f4f6f8"
PANEL_BG = "#ffffff"
TEXT_BG = "#ffffff"
TEXT_FG = "#1f2933"
MUTED_FG = "#52606d"
ACCENT = "#2563eb"
BORDER = "#cbd5e1"


EDUCATION_LINES = (
    ("Master of Science in Computer Science", "August 2024 – May 2026"),
    ("University of Alabama at Birmingham, AL  |  GPA: 4.0 / 4.0", ""),
)


def load_docx_dependencies() -> None:
    global Document, Inches, OxmlElement, Pt, WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, qn

    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Inches, Pt
    except ImportError as exc:
        raise RuntimeError("python-docx is required. Run: python3 -m pip install -r requirements.txt") from exc


@dataclass(frozen=True)
class ResumeFormat:
    font_name: str = "Arial"
    name_size: int = 16
    heading_size: int = 12
    body_size: int = 11


@dataclass(frozen=True)
class ResumeContent:
    summary: str
    skills: str
    experience: str
    certifications: str
    top_skills: str


def normalize_experience_bullet_text(text: str) -> str:
    return re.sub(r"\s+—\s+", ", ", text.strip())


def clean_lines(text: str) -> list[str]:
    return [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]


def split_keywords(text: str) -> list[str]:
    parts = re.split(r"[,;\n]", text)
    return [part.strip() for part in parts if part.strip()][:5]


def normalize_date_text(text: str) -> str:
    return re.sub(r"\s*(?:-|–|—|to)\s*", " – ", text.strip(), flags=re.IGNORECASE)


def split_dated_line(line: str) -> Optional[Tuple[str, str]]:
    stripped = line.strip()
    known = split_known_experience_line(stripped)
    if known:
        return known

    if "\t" in stripped:
        left, right = stripped.rsplit("\t", 1)
        if DATE_RANGE_RE.search(right):
            return left.strip(), normalize_date_text(right)

    if "|" in stripped:
        left, right = stripped.rsplit("|", 1)
        if DATE_RANGE_RE.search(right):
            return left.strip(), normalize_date_text(right)

    match = DATE_RANGE_RE.search(stripped)
    if match and match.start() > 0:
        left = stripped[: match.start()].rstrip(" |,-")
        if left:
            return left, normalize_date_text(match.group(0))
    return None


def split_known_experience_line(line: str) -> Optional[Tuple[str, str]]:
    normalized = re.sub(r"\s+", " ", line.strip())
    normalized_lower = normalized.lower()
    for label, date_text in KNOWN_EXPERIENCE_DATES:
        is_dated_input = DATE_RANGE_RE.search(normalized) or "|" in normalized or "\t" in normalized
        if normalized_lower.startswith(label) or (is_dated_input and label in normalized_lower):
            left = DATE_RANGE_RE.sub("", normalized).strip(" |,-")
            left = re.sub(r"\s*\|\s*", " | ", left)
            return left, date_text
    return None


def set_run_font(run, font_name: str, size: int, bold: bool = False) -> None:
    run.font.name = font_name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), font_name)
    run.font.size = Pt(size)
    run.bold = bold


def format_paragraph(paragraph, before: float = 0, after: float = 3, alignment=None) -> None:
    paragraph.paragraph_format.space_before = Pt(before)
    paragraph.paragraph_format.space_after = Pt(after)
    paragraph.paragraph_format.line_spacing = 1.0
    if alignment is not None:
        paragraph.alignment = alignment


def add_border_rule(document: Document) -> None:
    paragraph = document.add_paragraph()
    format_paragraph(paragraph, before=0, after=3)
    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "2")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "AAAAAA")
    p_bdr.append(bottom)
    p_pr.append(p_bdr)


def add_hyperlink(paragraph, text: str, url: str, fmt: ResumeFormat, bold: bool = False) -> None:
    part = paragraph.part
    r_id = part.relate_to(
        url,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True,
    )
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)

    new_run = OxmlElement("w:r")
    r_pr = OxmlElement("w:rPr")

    fonts = OxmlElement("w:rFonts")
    fonts.set(qn("w:ascii"), fmt.font_name)
    fonts.set(qn("w:hAnsi"), fmt.font_name)
    fonts.set(qn("w:eastAsia"), fmt.font_name)
    r_pr.append(fonts)

    size = OxmlElement("w:sz")
    size.set(qn("w:val"), str(fmt.body_size * 2))
    r_pr.append(size)

    color = OxmlElement("w:color")
    color.set(qn("w:val"), "0563C1")
    r_pr.append(color)

    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    r_pr.append(underline)

    if bold:
        r_pr.append(OxmlElement("w:b"))

    new_run.append(r_pr)
    text_element = OxmlElement("w:t")
    text_element.text = text
    new_run.append(text_element)
    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)


def add_text_run(paragraph, text: str, fmt: ResumeFormat, bold: bool = False) -> None:
    run = paragraph.add_run(text)
    set_run_font(run, fmt.font_name, fmt.body_size, bold=bold)


def add_section_heading(document: Document, title: str, fmt: ResumeFormat) -> None:
    paragraph = document.add_paragraph()
    format_paragraph(paragraph, before=8, after=3, alignment=WD_ALIGN_PARAGRAPH.LEFT)
    run = paragraph.add_run(title)
    set_run_font(run, fmt.font_name, fmt.heading_size, bold=True)


def add_plain_paragraph(
    document: Document,
    text: str,
    fmt: ResumeFormat,
    alignment=None,
    before: float = 2,
    after: float = 4,
) -> None:
    paragraph = document.add_paragraph()
    if alignment is None:
        alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    format_paragraph(paragraph, before=before, after=after, alignment=alignment)
    add_text_run(paragraph, text, fmt)


def add_skill_line(document: Document, line: str, fmt: ResumeFormat) -> None:
    paragraph = document.add_paragraph()
    format_paragraph(paragraph, before=2.5, after=2.5, alignment=WD_ALIGN_PARAGRAPH.LEFT)
    if ":" in line:
        label, rest = line.split(":", 1)
        add_text_run(paragraph, f"{label.strip()}: ", fmt, bold=True)
        add_text_run(paragraph, rest.strip(), fmt)
    else:
        add_text_run(paragraph, line, fmt)


def add_bullet(document: Document, text: str, fmt: ResumeFormat, *, normalize_dash: bool = False) -> None:
    paragraph = document.add_paragraph(style="List Bullet")
    format_paragraph(paragraph, before=2, after=2, alignment=WD_ALIGN_PARAGRAPH.JUSTIFY)
    if normalize_dash:
        text = normalize_experience_bullet_text(text)
    add_text_run(paragraph, text, fmt)


def add_tabbed_line(document: Document, left_text: str, right_text: str, fmt: ResumeFormat) -> None:
    right_text = normalize_date_text(right_text) if DATE_RANGE_RE.search(right_text) else right_text.strip()
    paragraph = document.add_paragraph()
    format_paragraph(paragraph, before=4, after=2, alignment=WD_ALIGN_PARAGRAPH.LEFT)
    paragraph.paragraph_format.tab_stops.add_tab_stop(Inches(6.27), alignment=WD_TAB_ALIGNMENT.RIGHT)
    add_text_run(paragraph, left_text.strip(), fmt, bold=True)
    if right_text.strip():
        add_text_run(paragraph, "\t", fmt)
        add_text_run(paragraph, right_text.strip(), fmt, bold=True)


def strip_bullet_marker(line: str) -> str:
    return re.sub(r"^(?:[-*]|\u2022)\s+", "", line.strip())


def add_experience_section(document: Document, lines: Iterable[str], fmt: ResumeFormat) -> None:
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        dated = split_dated_line(strip_bullet_marker(stripped))
        if dated:
            left, right = dated
            add_tabbed_line(document, left, right, fmt)
            continue

        add_bullet(document, strip_bullet_marker(stripped), fmt, normalize_dash=True)


def add_multiline_section(
    document: Document,
    lines: Iterable[str],
    fmt: ResumeFormat,
    *,
    skill_mode: bool = False,
    paragraph_alignment=None,
) -> None:
    if paragraph_alignment is None:
        paragraph_alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        bullet_match = re.match(r"^(?:[-*]|\u2022)\s+(.*)$", stripped)
        if bullet_match:
            add_bullet(document, bullet_match.group(1).strip(), fmt)
        elif skill_mode:
            add_skill_line(document, stripped, fmt)
        elif "\t" in stripped:
            left, right = stripped.split("\t", 1)
            add_tabbed_line(document, left, right, fmt)
        elif split_dated_line(stripped):
            left, right = split_dated_line(stripped)
            add_tabbed_line(document, left, right, fmt)
        else:
            add_plain_paragraph(document, stripped, fmt, alignment=paragraph_alignment, before=2, after=3)


def apply_document_defaults(document: Document, fmt: ResumeFormat) -> None:
    section = document.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(0.75)
    section.right_margin = Inches(0.75)
    section.bottom_margin = Inches(0.75)
    section.left_margin = Inches(0.75)
    section.header_distance = Inches(0.4917)
    section.footer_distance = Inches(0.4917)

    normal = document.styles["Normal"]
    normal.font.name = fmt.font_name
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), fmt.font_name)
    normal.font.size = Pt(fmt.body_size)
    normal.paragraph_format.line_spacing = 1.0

    bullet = document.styles["List Bullet"]
    bullet.font.name = fmt.font_name
    bullet._element.rPr.rFonts.set(qn("w:eastAsia"), fmt.font_name)
    bullet.font.size = Pt(fmt.body_size)


def build_resume(content: ResumeContent, fmt: ResumeFormat, output_path: Path) -> Path:
    load_docx_dependencies()
    document = Document()
    apply_document_defaults(document, fmt)

    core = document.core_properties
    core.author = AUTHOR_NAME
    core.subject = "my resume"
    core.keywords = ", ".join(split_keywords(content.top_skills))
    core.title = f"{AUTHOR_NAME} Resume"

    name_paragraph = document.add_paragraph()
    format_paragraph(name_paragraph, before=0, after=3, alignment=WD_ALIGN_PARAGRAPH.LEFT)
    name_run = name_paragraph.add_run(AUTHOR_NAME)
    set_run_font(name_run, fmt.font_name, fmt.name_size, bold=True)

    contact = document.add_paragraph()
    format_paragraph(contact, before=0, after=3, alignment=WD_ALIGN_PARAGRAPH.LEFT)
    add_hyperlink(contact, EMAIL, f"mailto:{EMAIL}", fmt)
    add_text_run(contact, "  |  ", fmt, bold=True)
    add_hyperlink(contact, PHONE, PHONE_LINK, fmt)
    add_text_run(contact, "  |  ", fmt, bold=True)
    add_text_run(contact, LOCATION, fmt)

    add_border_rule(document)
    add_section_heading(document, "SUMMARY", fmt)
    add_multiline_section(document, clean_lines(content.summary), fmt, paragraph_alignment=WD_ALIGN_PARAGRAPH.JUSTIFY)

    add_border_rule(document)
    add_section_heading(document, "SKILLS", fmt)
    add_multiline_section(
        document,
        clean_lines(content.skills),
        fmt,
        skill_mode=True,
        paragraph_alignment=WD_ALIGN_PARAGRAPH.LEFT,
    )

    add_border_rule(document)
    add_section_heading(document, "WORK EXPERIENCE", fmt)
    add_experience_section(document, clean_lines(content.experience), fmt)

    add_border_rule(document)
    add_section_heading(document, "EDUCATION", fmt)
    for left, right in EDUCATION_LINES:
        if right:
            add_tabbed_line(document, left, right, fmt)
        else:
            add_plain_paragraph(document, left, fmt, alignment=WD_ALIGN_PARAGRAPH.JUSTIFY, before=0, after=3)

    if content.certifications.strip():
        add_border_rule(document)
        add_section_heading(document, "Certifications", fmt)
        add_multiline_section(
            document,
            clean_lines(content.certifications),
            fmt,
            paragraph_alignment=WD_ALIGN_PARAGRAPH.LEFT,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(output_path)
    return output_path


class ResumeWriterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Resume Writer")
        self.geometry("980x760")
        self.minsize(860, 650)
        self.configure(bg=APP_BG)

        self.font_var = tk.StringVar(value="Arial")
        self.name_size_var = tk.StringVar(value="16")
        self.heading_size_var = tk.StringVar(value="12")
        self.body_size_var = tk.StringVar(value="11")
        self.output_var = tk.StringVar(value=str(Path.home() / "Documents" / DEFAULT_OUTPUT))

        self._configure_style()
        self._build_ui()

    def _configure_style(self) -> None:
        self.option_add("*Font", "Arial 12")
        self.option_add("*Background", APP_BG)
        self.option_add("*Foreground", TEXT_FG)
        self.option_add("*Entry.Background", TEXT_BG)
        self.option_add("*Entry.Foreground", TEXT_FG)
        self.option_add("*Text.Background", TEXT_BG)
        self.option_add("*Text.Foreground", TEXT_FG)
        self.option_add("*insertBackground", TEXT_FG)

    def _build_ui(self) -> None:
        root = tk.Frame(self, bg=APP_BG, padx=16, pady=16)
        root.pack(fill=tk.BOTH, expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        controls = self._section(root, "Format options")
        controls.grid(row=0, column=0, sticky="ew")
        for column in range(8):
            controls.columnconfigure(column, weight=1 if column in (1, 3, 5, 7) else 0)

        self._combo(controls, "Font", self.font_var, FONT_CHOICES, 0, 0)
        self._combo(controls, "Name size", self.name_size_var, NAME_SIZE_CHOICES, 0, 2)
        self._combo(controls, "Heading size", self.heading_size_var, HEADING_SIZE_CHOICES, 0, 4)
        self._combo(controls, "Text size", self.body_size_var, BODY_SIZE_CHOICES, 0, 6)

        text_area = tk.Frame(root, bg=APP_BG)
        text_area.grid(row=1, column=0, sticky="nsew", pady=(12, 12))
        text_area.columnconfigure(0, weight=1)
        text_area.columnconfigure(1, weight=1)
        text_area.rowconfigure(1, weight=1)
        text_area.rowconfigure(3, weight=1)

        self.summary_text = self._text_box(text_area, "Summary", 0, 0)
        self.skills_text = self._text_box(text_area, "Skills", 0, 1)
        self.experience_text = self._text_box(text_area, "Job Experience", 2, 0, columnspan=2, height=11)
        self.certifications_text = self._text_box(text_area, "Certifications", 4, 0, height=5)
        self.top_skills_text = self._text_box(text_area, "Top 5 Skills for Metadata", 4, 1, height=5)

        output = self._section(root, "Output")
        output.grid(row=2, column=0, sticky="ew")
        output.columnconfigure(1, weight=1)

        self._label(output, "File").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._entry(output, self.output_var).grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self._button(output, "Browse", self._choose_output).grid(row=0, column=2, padx=(0, 8))
        self._button(output, "Generate DOCX", self._generate, accent=True).grid(row=0, column=3)

        details = tk.Label(
            root,
            text=(
                f"Fixed header: {AUTHOR_NAME} | {EMAIL} | {PHONE} | {LOCATION}. "
                "Education is hard coded from the base resume."
            ),
            bg=APP_BG,
            fg=MUTED_FG,
            anchor="w",
        )
        details.grid(row=3, column=0, sticky="w")

    def _section(self, parent, label: str) -> tk.LabelFrame:
        return tk.LabelFrame(
            parent,
            text=label,
            bg=PANEL_BG,
            fg=TEXT_FG,
            padx=12,
            pady=12,
            bd=1,
            relief=tk.SOLID,
            font=("Arial", 12, "bold"),
            highlightbackground=BORDER,
            highlightcolor=BORDER,
        )

    def _label(self, parent, text: str, *, muted: bool = False) -> tk.Label:
        return tk.Label(
            parent,
            text=text,
            bg=parent.cget("bg"),
            fg=MUTED_FG if muted else TEXT_FG,
            anchor="w",
        )

    def _entry(self, parent, variable: tk.StringVar) -> tk.Entry:
        return tk.Entry(
            parent,
            textvariable=variable,
            bg=TEXT_BG,
            fg=TEXT_FG,
            insertbackground=TEXT_FG,
            relief=tk.SOLID,
            bd=1,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
        )

    def _button(self, parent, text: str, command, *, accent: bool = False) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=ACCENT if accent else "#e8eef8",
            fg="#ffffff" if accent else TEXT_FG,
            activebackground="#1d4ed8" if accent else "#dbeafe",
            activeforeground="#ffffff" if accent else TEXT_FG,
            relief=tk.RAISED,
            bd=1,
            padx=10,
            pady=5,
            cursor="hand2",
        )

    def _combo(self, parent, label: str, variable: tk.StringVar, values: tuple[str, ...], row: int, column: int) -> None:
        self._label(parent, label).grid(row=row, column=column, sticky="w", padx=(0, 6))
        dropdown = tk.OptionMenu(parent, variable, *values)
        dropdown.configure(
            bg=TEXT_BG,
            fg=TEXT_FG,
            activebackground="#dbeafe",
            activeforeground=TEXT_FG,
            relief=tk.SOLID,
            bd=1,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
            anchor="w",
            width=14,
        )
        dropdown["menu"].configure(
            bg=TEXT_BG,
            fg=TEXT_FG,
            activebackground="#dbeafe",
            activeforeground=TEXT_FG,
        )
        dropdown.grid(row=row, column=column + 1, sticky="ew", padx=(0, 12))

    def _text_box(self, parent, label: str, row: int, column: int, columnspan: int = 1, height: int = 8) -> tk.Text:
        self._label(parent, label).grid(row=row, column=column, columnspan=columnspan, sticky="w")
        frame = tk.Frame(parent, bg=PANEL_BG)
        frame.grid(row=row + 1, column=column, columnspan=columnspan, sticky="nsew", padx=(0, 8), pady=(4, 12))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        text = tk.Text(
            frame,
            height=height,
            wrap=tk.WORD,
            undo=True,
            bg=TEXT_BG,
            fg=TEXT_FG,
            insertbackground=TEXT_FG,
            selectbackground="#bfdbfe",
            selectforeground=TEXT_FG,
            relief=tk.SOLID,
            borderwidth=1,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
            font=("Arial", 12),
        )
        scroll = tk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
        scroll.configure(
            bg="#e8eef8",
            activebackground="#dbeafe",
            troughcolor=APP_BG,
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
        )
        text.configure(yscrollcommand=scroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        return text

    def _choose_output(self) -> None:
        selected = filedialog.asksaveasfilename(
            title="Save resume as",
            defaultextension=".docx",
            filetypes=(("Word document", "*.docx"), ("All files", "*.*")),
            initialfile=DEFAULT_OUTPUT,
        )
        if selected:
            self.output_var.set(selected)

    def _generate(self) -> None:
        try:
            fmt = ResumeFormat(
                font_name=self.font_var.get(),
                name_size=int(self.name_size_var.get()),
                heading_size=int(self.heading_size_var.get()),
                body_size=int(self.body_size_var.get()),
            )
            content = ResumeContent(
                summary=self.summary_text.get("1.0", tk.END).strip(),
                skills=self.skills_text.get("1.0", tk.END).strip(),
                experience=self.experience_text.get("1.0", tk.END).strip(),
                certifications=self.certifications_text.get("1.0", tk.END).strip(),
                top_skills=self.top_skills_text.get("1.0", tk.END).strip(),
            )
            if not content.summary or not content.skills or not content.experience:
                messagebox.showerror("Missing content", "Summary, Skills, and Job Experience are required.")
                return
            output_path = Path(self.output_var.get()).expanduser()
            if output_path.suffix.lower() != ".docx":
                output_path = output_path.with_suffix(".docx")
            build_resume(content, fmt, output_path)
        except Exception as exc:
            messagebox.showerror("Could not generate resume", str(exc))
            return
        self._clear_text_inputs()
        messagebox.showinfo("Resume generated", f"Saved to:\n{output_path}")

    def _clear_text_inputs(self) -> None:
        for text_widget in (
            self.summary_text,
            self.skills_text,
            self.experience_text,
            self.certifications_text,
            self.top_skills_text,
        ):
            text_widget.delete("1.0", tk.END)


if __name__ == "__main__":
    ResumeWriterApp().mainloop()
