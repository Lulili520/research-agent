#!/usr/bin/env python3
"""Render a dated radar Markdown report with a dedicated XeLaTeX-style brief template."""

import argparse
import os
import re
import shutil
import subprocess
from pathlib import Path


def tectonic_path() -> Path:
    configured = os.environ.get("RADAR_TECTONIC")
    candidates = [
        Path(configured) if configured else None,
        Path(os.environ.get("LOCALAPPDATA", "")) / "Research-Agent/tools/tectonic-0.17.0/tectonic.exe",
        Path(shutil.which("tectonic") or ""),
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    raise RuntimeError("未找到 Tectonic；请安装 0.17+ 或设置 RADAR_TECTONIC")


def escape_tex(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
        "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
        "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in text)


def inline(text: str) -> str:
    tokens = []

    def hold(value: str) -> str:
        tokens.append(value)
        return f"@@TOKEN{len(tokens)-1}@@"

    text = re.sub(r"\[([^]]+)]\(([^)]+)\)", lambda m: hold(r"\href{" + escape_tex(m.group(2)) + "}{" + escape_tex(m.group(1)) + "}"), text)
    text = re.sub(r"\*\*([^*]+)\*\*", lambda m: hold(r"\textbf{" + escape_tex(m.group(1)) + "}"), text)
    text = re.sub(r"`([^`]+)`", lambda m: hold(r"\texttt{" + escape_tex(m.group(1)) + "}"), text)
    text = escape_tex(text)
    for index, value in enumerate(tokens):
        text = text.replace(f"@@TOKEN{index}@@", value)
    return text


def table_tex(rows: list[list[str]]) -> str:
    if len(rows) < 2:
        return ""
    rows = [row for row in rows if not all(set(cell.replace(" ", "")) <= {"-", ":"} for cell in row)]
    columns = len(rows[0])
    spec = "@{}" + "Y" * columns + "@{}"
    output = [r"\begin{radartable}{" + spec + "}", r"\rowcolor{RadarBlueLight}"]
    for row_index, row in enumerate(rows):
        cells = [inline(cell) for cell in row]
        if row_index == 0:
            cells = [r"\textbf{" + cell + "}" for cell in cells]
        output.append(" & ".join(cells) + r" \\")
        if row_index == 0:
            output.append(r"\midrule")
        elif row_index < len(rows) - 1:
            output.append(r"\addlinespace[2pt]")
    output.append(r"\end{radartable}")
    return "\n".join(output)


def markdown_to_tex(markdown: str) -> str:
    output = []
    table_rows = []
    in_list = False
    paper_count = 0

    def close_list():
        nonlocal in_list
        if in_list:
            output.append(r"\end{itemize}")
            in_list = False

    def flush_table():
        nonlocal table_rows
        if table_rows:
            output.append(table_tex(table_rows))
            table_rows = []

    for raw in markdown.splitlines():
        line = raw.strip()
        if line.startswith("|") and line.endswith("|"):
            close_list()
            table_rows.append([cell.strip() for cell in line.strip("|").split("|")])
            continue
        flush_table()
        if not line:
            close_list()
            output.append(r"\par")
        elif line.startswith("# "):
            close_list()
            output.append(r"\RadarTitle{" + inline(line[2:]) + "}")
        elif line.startswith("## 0"):
            close_list()
            paper_count += 1
            output.append(r"\vspace{6mm}" if paper_count > 1 else r"\vspace{3mm}")
            output.append(r"\PaperTitle{" + inline(line[3:]) + "}")
        elif line.startswith("## "):
            close_list()
            output.append(r"\RadarSection{" + inline(line[3:]) + "}")
        elif line.startswith("### "):
            close_list()
            output.append(r"\RadarSubsection{" + inline(line[4:]) + "}")
        elif line.startswith("#### "):
            close_list()
            output.append(r"\EvidenceHeading{" + inline(line[5:]) + "}")
        elif line.startswith("> "):
            close_list()
            content = line[2:]
            kind = "CoreBox" if content.startswith("**核心贡献") else "BoundaryBox" if content.startswith("**证据边界") else "InfoBox"
            output.append(r"\begin{" + kind + "}" + inline(content) + r"\end{" + kind + "}")
        elif line == "---" or line == "<!-- pagebreak -->":
            close_list()
        elif re.match(r"^- ", line):
            if not in_list:
                output.append(r"\begin{itemize}")
                in_list = True
            output.append(r"\item " + inline(line[2:]))
        elif re.match(r"^\d+\. ", line):
            close_list()
            output.append(r"\noindent\textbf{" + line.split(".", 1)[0] + ".} " + inline(line.split(". ", 1)[1]) + r"\par")
        else:
            close_list()
            output.append(inline(line) + r"\par")
    flush_table()
    close_list()
    return "\n".join(output)


TEMPLATE = r"""\documentclass[11pt,a4paper]{article}
\usepackage[left=22mm,right=22mm,top=23mm,bottom=21mm]{geometry}
\usepackage{fontspec}
\usepackage{xeCJK}
\setmainfont{__LATIN_SERIF__}
\setsansfont{__LATIN_SANS__}
\setCJKmainfont{__CJK_SERIF__}
\setCJKsansfont{__CJK_SANS__}
\usepackage{xcolor,booktabs,tabularx,array,colortbl,tcolorbox,enumitem,hyperref,fancyhdr,titlesec,microtype,needspace}
\tcbuselibrary{skins,breakable}
\definecolor{RadarNavy}{HTML}{163A5F}
\definecolor{RadarBlue}{HTML}{2A6F97}
\definecolor{RadarBlueLight}{HTML}{F1F6F9}
\definecolor{RadarRule}{HTML}{CBD9E2}
\definecolor{RadarText}{HTML}{263238}
\definecolor{RadarMuted}{HTML}{647782}
\definecolor{RadarGreen}{HTML}{F2F8F3}
\definecolor{RadarGreenBorder}{HTML}{72A57B}
\definecolor{RadarOrange}{HTML}{FFF8ED}
\definecolor{RadarOrangeBorder}{HTML}{D69A45}
\color{RadarText}
\hypersetup{colorlinks=true,urlcolor=RadarBlue,linkcolor=RadarBlue,pdftitle={AI 论文精读 __DATE__},pdfauthor={Research Agent}}
\pagestyle{fancy}\fancyhf{}
\fancyhead[L]{\scriptsize\sffamily\color{RadarMuted} AI 论文精读}
\fancyhead[R]{\scriptsize\sffamily\color{RadarMuted} __DATE__}
\fancyfoot[C]{\scriptsize\sffamily\color{RadarMuted} \thepage}
\renewcommand{\headrulewidth}{0.35pt}\renewcommand{\headrule}{\hbox to\headwidth{\color{RadarRule}\leaders\hrule height \headrulewidth\hfill}}
\setlength{\parindent}{2em}\setlength{\parskip}{3pt}\linespread{1.20}
\setlist[itemize]{leftmargin=2em,itemsep=2.5pt,topsep=3.5pt,parsep=1pt}
\newcolumntype{Y}{>{\raggedright\arraybackslash}X}
\newenvironment{radartable}[1]{\par\vspace{3pt}\noindent\tabularx{\linewidth}{#1}\toprule}{\bottomrule\endtabularx\par\vspace{5pt}}
\newcommand{\RadarTitle}[1]{\begin{center}\vspace*{5mm}{\fontsize{24}{32}\selectfont\sffamily\bfseries\color{RadarNavy}#1}\par\vspace{2.5mm}{\color{RadarBlue}\rule{18mm}{1.1pt}}\end{center}\vspace{5mm}}
\newcommand{\PaperTitle}[1]{\Needspace{48mm}\vspace{7mm}\noindent\begin{minipage}{\linewidth}\color{RadarBlue}\rule{1.2mm}{12mm}\hspace{3mm}\parbox[b]{\dimexpr\linewidth-5mm\relax}{\Large\sffamily\bfseries\color{RadarNavy}#1}\end{minipage}\par\vspace{4mm}}
\newcommand{\RadarSection}[1]{\vspace{4mm}\noindent{\Large\sffamily\bfseries\color{RadarBlue}#1}\par\vspace{1.2mm}{\color{RadarRule}\rule{\linewidth}{0.45pt}}\vspace{2mm}}
\newcommand{\RadarSubsection}[1]{\vspace{3.5mm}\noindent{\large\sffamily\bfseries\color{RadarNavy}#1}\par\vspace{1.2mm}}
\newcommand{\EvidenceHeading}[1]{\vspace{2.5mm}\noindent{\normalsize\sffamily\bfseries\color{RadarBlue}#1}\par\vspace{.5mm}}
\newtcolorbox{CoreBox}{enhanced,breakable,colback=RadarGreen,colframe=RadarGreenBorder,boxrule=0pt,borderline west={1.2pt}{0pt}{RadarGreenBorder},arc=0mm,left=3.5mm,right=3mm,top=2.5mm,bottom=2.5mm,before skip=5pt,after skip=5pt}
\newtcolorbox{BoundaryBox}{enhanced,breakable,colback=RadarOrange,colframe=RadarOrangeBorder,boxrule=0pt,borderline west={1.2pt}{0pt}{RadarOrangeBorder},arc=0mm,left=3.5mm,right=3mm,top=2.5mm,bottom=2.5mm,before skip=5pt,after skip=5pt}
\newtcolorbox{InfoBox}{enhanced,breakable,colback=RadarBlueLight,colframe=RadarRule,boxrule=0pt,borderline west={1.2pt}{0pt}{RadarBlue},arc=0mm,left=3.5mm,right=3mm,top=2.5mm,bottom=2.5mm,before skip=5pt,after skip=5pt}
\begin{document}
__BODY__
\end{document}
"""


def build(markdown_path: Path, output_pdf: Path) -> None:
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    build_dir = output_pdf.parent / ".latex-build"
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir()
    tex_path = build_dir / "report.tex"
    report_date = output_pdf.parent.name if re.fullmatch(r"\d{4}-\d{2}-\d{2}", output_pdf.parent.name) else ""
    fonts = {
        "__LATIN_SERIF__": "Times New Roman" if os.name == "nt" else "Liberation Serif",
        "__LATIN_SANS__": "Arial" if os.name == "nt" else "Liberation Sans",
        "__CJK_SERIF__": "STSong" if os.name == "nt" else "Noto Serif CJK SC",
        "__CJK_SANS__": "Microsoft YaHei" if os.name == "nt" else "Noto Sans CJK SC",
    }
    document = TEMPLATE.replace("__DATE__", escape_tex(report_date)).replace("__BODY__", markdown_to_tex(markdown_path.read_text(encoding="utf-8")))
    for marker, font in fonts.items():
        document = document.replace(marker, font)
    tex_path.write_text(document, encoding="utf-8")
    try:
        result = subprocess.run([str(tectonic_path()), str(tex_path), "--outdir", str(build_dir)])
        if result.returncode:
            raise RuntimeError(f"LaTeX 编译失败，退出码 {result.returncode}")
        generated = build_dir / "report.pdf"
        if not generated.is_file():
            raise RuntimeError("LaTeX 编译未生成 report.pdf")
        shutil.copy2(generated, output_pdf)
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("markdown", type=Path)
    parser.add_argument("pdf", nargs="?", type=Path)
    args = parser.parse_args()
    build(args.markdown, args.pdf or args.markdown.with_suffix(".pdf"))
