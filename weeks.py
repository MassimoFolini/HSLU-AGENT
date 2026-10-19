"""Ordnet Dateien einer Schulwoche (SW) zu. Semesterstart HS26: Montag, 14.09.2026 = SW01."""
import os
import re
from datetime import date, datetime

SEMESTER_START = date(2026, 9, 14)
_PATTERNS = (
    re.compile(r"(?<![A-Za-z])SW\s*0*(\d{1,2})(?!\d)", re.I),     # SW03, SW 3, SW03-final
    re.compile(r"(?<![A-Za-z])Week\s*0*(\d{1,2})(?!\d)", re.I),   # Week 4, Week8
)


def week_of_text(text):
    """Schulwoche aus einem Pfad oder Namen, sonst None."""
    for pat in _PATTERNS:
        m = pat.search(text)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 20:
                return n
    return None


def week_of_date(d):
    """Schulwoche aus einem Datum (Semesterwochen ab SEMESTER_START)."""
    if isinstance(d, datetime):
        d = d.date()
    n = (d - SEMESTER_START).days // 7 + 1
    return n if 1 <= n <= 20 else None


def week_of_file(path):
    """Schulwoche einer Datei: zuerst aus Pfad/Name, sonst aus Datum im Namen (YYYY-MM-DD), sonst None."""
    w = week_of_text(path.replace("\\", "/"))
    if w:
        return w
    m = re.search(r"(20\d\d)-(\d\d)-(\d\d)", os.path.basename(path))
    if m:
        try:
            return week_of_date(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            return None
    return None


def label(week):
    """Sortierbares Praefix: SW00 = allgemeine Unterlagen ohne Wochenbezug."""
    return f"SW{(week or 0):02d}"
