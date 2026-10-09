"""Number guard for generated explanations: every number in a text must be traceable to the engine output.

An LLM may phrase the recommendation in natural Vietnamese, but it must not introduce figures. `verify_numbers` extracts the
numbers of a text and checks each against the numbers present anywhere in the engine output (within rounding);
`grounded_explanation` calls an optional LLM, verifies the answer and falls back to the engine's own summary when the text
contains an unsupported figure. No LLM is required: without one the template text is returned.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any, Callable

_NUM = re.compile(r"(\d{1,3}(?:[.,]\d{3})+(?!\d)|\d+(?:[.,]\d+)?)(?:\s*(k|nghìn|ngàn|triệu|tr)\b)?")
_SCALE = {"k": 1_000, "nghìn": 1_000, "ngàn": 1_000, "triệu": 1_000_000, "tr": 1_000_000}
_TIME = re.compile(r"\b\d{1,2}:\d{2}\b")


def _to_number(raw: str) -> float:
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", raw):
        return float(re.sub(r"[.,]", "", raw))
    return float(raw.replace(",", "."))


def _items(text: str) -> list[tuple[float, float]]:
    """(value, tolerance) per number. Exact figures get ~0.1% (rounding noise); "74 nghìn"/"2k" are rounded to their unit."""
    out = []
    for raw, unit in _NUM.findall(_TIME.sub(" ", text or "")):
        v = _to_number(raw)
        if unit:
            out.append((v * _SCALE[unit], 0.5 * _SCALE[unit] if v == int(v) else 0.05 * _SCALE[unit]))
        else:
            out.append((v, 0.51 if v < 100 else 0.001 * v))
    return out


def numbers_in(text: str) -> list[float]:
    return [v for v, _ in _items(text)]


def _walk(x: Any, acc: list[float]) -> None:
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        for f in dataclasses.fields(x):
            _walk(getattr(x, f.name), acc)
    elif isinstance(x, dict):
        for k, v in x.items():
            _walk(v, acc)
            if isinstance(k, str):
                acc.extend(numbers_in(k))
    elif isinstance(x, (list, tuple, set)):
        for v in x:
            _walk(v, acc)
    elif isinstance(x, bool) or x is None:
        return
    elif isinstance(x, (int, float)):
        acc.append(float(x))
    elif isinstance(x, str):
        acc.extend(numbers_in(x))


def allowed_numbers(output: Any) -> list[float]:
    acc: list[float] = []
    _walk(output, acc)
    return acc


def verify_numbers(text: str, output: Any) -> list[float]:
    """Numbers of `text` that cannot be traced to `output` (empty list = fully grounded).

    Necessary, not sufficient: it proves no figure was invented, not that the sentence uses a true figure correctly."""
    allowed = allowed_numbers(output)
    bad = []
    for v, tol in _items(text):
        if not any(abs(v - a) <= max(tol, 0.001 * abs(a) if abs(a) >= 100 else 0.0) for a in allowed):
            bad.append(v)
    return bad


def template_text(output: Any) -> str:
    """The engine's own wording: the summaries of the available plans."""
    parts = []
    for res in getattr(output, "objectives", {}).values():
        if getattr(res, "plan", None) is not None:
            parts.append(f"{res.plan.direction_title}: {res.plan.summary}")
    return "\n".join(parts) if parts else "Chưa đủ dữ liệu để đưa ra khuyến nghị."


def grounded_explanation(output: Any, call_llm: Callable[[str], str] | None = None) -> dict[str, Any]:
    base = template_text(output)
    if call_llm is None:
        return {"text": base, "source": "template", "unsupported_numbers": []}
    prompt = (
        "Viết lại khuyến nghị sau bằng tiếng Việt tự nhiên, ngắn gọn cho tài xế xe máy. "
        "TUYỆT ĐỐI không thêm, làm tròn lại hay suy ra con số nào ngoài các số đã có; không hứa hẹn có cuốc.\n\n" + base
    )
    try:
        text = str(call_llm(prompt)).strip()
    except Exception:  # noqa: BLE001 — a failing LLM must never break the explanation
        return {"text": base, "source": "template", "unsupported_numbers": [], "note": "LLM lỗi, dùng văn bản của engine"}
    bad = verify_numbers(text, output)
    if not text or bad:
        return {"text": base, "source": "template", "unsupported_numbers": bad,
                "note": "văn bản do LLM tạo chứa số không có trong kết quả engine nên bị loại"}
    return {"text": text, "source": "llm", "unsupported_numbers": []}
