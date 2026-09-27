"""Make static TrueType instances (Regular/Medium/SemiBold/Bold) from PretendardVariable.ttf.

Why: PowerPoint's PDF export does not embed CFF-flavoured OpenType (.otf) text; it converts it to
outlines, so the PDF has no extractable text. TrueType instances embed normally.

Usage:  .venv\\Scripts\\python portfolio\\make_static_ttf.py <PretendardVariable.ttf> <out_dir>
"""
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

src, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
for style, wght in [("Regular", 400), ("Medium", 500), ("SemiBold", 600), ("Bold", 700)]:
    vf = TTFont(src)
    st = instancer.instantiateVariableFont(vf, {"wght": wght}, updateFontNames=True)
    os2, head = st["OS/2"], st["head"]
    bold = style == "Bold"
    # RIBBI bits: fsSelection bit5 = BOLD, bit6 = REGULAR; macStyle bit0 = Bold
    os2.fsSelection = (os2.fsSelection & ~0b1100000) | (0b0100000 if bold else 0b1000000)
    head.macStyle = (head.macStyle & ~0b1) | (1 if bold else 0)
    os2.usWeightClass = wght
    # the variable font is named "Pretendard Variable"; the static instances should be plain "Pretendard"
    names = st["name"]
    for rec in names.names:
        s = rec.toUnicode()
        if "Pretendard Variable" in s or "PretendardVariable" in s:
            rec.string = s.replace("Pretendard Variable", "Pretendard").replace("PretendardVariable", "Pretendard")
    path = out / f"Pretendard-{style}.ttf"
    st.save(path)
    print(path.name, "| family:", names.getDebugName(1), "| subfamily:", names.getDebugName(2),
          "| typo:", names.getDebugName(16), names.getDebugName(17), "| fullname:", names.getDebugName(4),
          f"| weight {os2.usWeightClass} fsSelection {os2.fsSelection:#x} macStyle {head.macStyle}",
          f"| {path.stat().st_size / 1e6:.1f} MB")
