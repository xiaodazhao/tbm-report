import math
import re
from typing import Any, Optional


MILEAGE_PATTERN = re.compile(r"(?:D?Y?K|DK|DYK|YDK)?\s*(\d+)\s*\+\s*(\d+(?:\.\d+)?)", re.I)


def normalize_chainage_text(value: Any) -> str:
    """Normalize mileage text spacing/prefix for regex parsing."""
    if value is None:
        return ""
    text = str(value).strip()
    text = text.replace("＋", "+").replace("﹢", "+")
    text = re.sub(r"\s+", "", text)
    return text


def mileage_to_num(mileage: str) -> Optional[float]:
    """Convert mileage text like DyK1014+616 or DK1014+616 to numeric chainage."""
    text = normalize_chainage_text(mileage)
    if not text:
        return None
    match = MILEAGE_PATTERN.search(text)
    if not match:
        return None
    return float(match.group(1)) * 1000 + float(match.group(2))


def num_to_mileage(num: float, prefix: str = "DyK") -> str:
    """Convert numeric chainage back into mileage text."""
    try:
        x = float(num)
    except Exception:
        return "未知里程"
    if not math.isfinite(x):
        return "未知里程"
    km = int(math.floor(x / 1000))
    meter = x - km * 1000
    return f"{prefix}{km}+{meter:.1f}"


def safe_float(value: Any):
    """Safely cast a value to float or return None."""
    try:
        x = float(value)
    except Exception:
        return None
    return x if math.isfinite(x) else None


def compact_text(text: str) -> str:
    """Remove whitespace from text for compact matching."""
    return re.sub(r"\s+", "", text or "")


def format_chainage_dk(value, unknown="未知里程", prefix="DK"):
    """Format TBM chainage as DKxxxx+xxx.

    Supports both meter-style values such as 1014616 and kilometer-decimal
    values such as 1014.616.
    """
    try:
        if value is None:
            return unknown
        x = float(value)
    except (TypeError, ValueError):
        return unknown

    if not math.isfinite(x):
        return unknown

    if abs(x) >= 100000:
        km = int(math.floor(x / 1000))
        meter = int(round(x - km * 1000))
    else:
        km = int(math.floor(x))
        meter = int(round((x - km) * 1000))

    if meter >= 1000:
        km += meter // 1000
        meter = meter % 1000

    return f"{prefix}{km}+{meter:03d}"


def format_chainage_range_dk(start, end, separator="~"):
    """Format chainage range dk."""
    return f"{format_chainage_dk(start)}{separator}{format_chainage_dk(end)}"