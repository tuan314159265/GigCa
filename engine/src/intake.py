"""Vietnamese intake: free text -> driver profile / preferences / context, with every field range-checked.

Deterministic rules (no network, no hallucination) do the parsing; an LLM can be plugged in through `llm_extract`, but its
answer goes through the SAME validation and is rejected field by field if the number does not occur in the user's text.
The result is a PROPOSAL the UI must show for confirmation — the driver stays in control of what the engine uses.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable

# field -> (min, max, unit) plausible range; anything outside is reported, never silently clamped
RANGES: dict[str, tuple[float, float]] = {
    "fare_base_vnd": (0, 100_000), "fare_per_km_vnd": (1_000, 30_000), "fuel_l_per_100km": (0.5, 10.0),
    "fuel_price_vnd_per_l": (10_000, 60_000), "target_vnd_per_hour": (10_000, 500_000),
    "fare_base_km": (0.5, 5.0), "fare_per_min_vnd": (0, 5_000), "driver_share": (0.3, 1.0),
    "max_reposition_km": (0.3, 30.0), "idle_duration_min": (0, 480),
}
PROFILE_FIELDS = ("fare_base_vnd", "fare_per_km_vnd", "fuel_l_per_100km", "fuel_price_vnd_per_l", "target_vnd_per_hour",
                  "fare_base_km", "fare_per_min_vnd", "driver_share")
CONTEXT_FIELDS = ("max_reposition_km", "idle_duration_min")
_NUM = r"(\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)"
_UNIT = r"\s*(k|nghìn|nghin|ngàn|ngan|tr|triệu|trieu|đ|d|vnd|đồng|dong)?"


@dataclass
class IntakeResult:
    profile: dict[str, float] = field(default_factory=dict)
    preferences: dict[str, str] = field(default_factory=dict)
    context: dict[str, float] = field(default_factory=dict)
    understood: list[dict[str, Any]] = field(default_factory=list)  # {"field","value","from"} — shown to the driver
    rejected: list[dict[str, Any]] = field(default_factory=list)  # parsed but out of range / not grounded
    unparsed: list[str] = field(default_factory=list)  # clauses with numbers nothing could explain
    needs_confirmation: bool = True


def _fold(s: str) -> str:
    return unicodedata.normalize("NFC", s.lower())


def _to_number(raw: str) -> float:
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", raw):
        return float(re.sub(r"[.,]", "", raw))
    return float(raw.replace(",", "."))


def _money(num: str, unit: str | None) -> float:
    v = _to_number(num)
    u = (unit or "").lower()
    if u in ("k", "nghìn", "nghin", "ngàn", "ngan"):
        return v * 1_000
    if u in ("tr", "triệu", "trieu"):
        return v * 1_000_000
    return v


def _check(res: IntakeResult, name: str, value: float, src: str) -> bool:
    lo, hi = RANGES[name]
    if not (lo <= value <= hi):
        res.rejected.append({"field": name, "value": value, "from": src, "reason": f"ngoài khoảng hợp lý [{lo:g}, {hi:g}]"})
        return False
    res.understood.append({"field": name, "value": value, "from": src})
    return True


def parse_intake_vi(text: str) -> IntakeResult:
    t = _fold(text)
    res = IntakeResult()
    consumed: list[tuple[int, int]] = []

    def take(pattern: str, name: str, scale: Callable[[re.Match], float], bucket: dict[str, float]) -> None:
        m = re.search(pattern, t)
        if not m or name in bucket:
            return
        val = scale(m)
        consumed.append(m.span())
        if _check(res, name, val, m.group(0).strip()):
            bucket[name] = val

    # opening fare for the first N km: "2 km đầu: 12.500 đồng"
    m_open = re.search(r"(\d+(?:[.,]\d+)?)\s*km\s*đầu\D{0,12}" + _NUM + _UNIT, t)
    if m_open:
        consumed.append(m_open.span())
        if _check(res, "fare_base_km", _to_number(m_open.group(1)), m_open.group(0).strip()):
            res.profile["fare_base_km"] = _to_number(m_open.group(1))
        val = _money(m_open.group(2), m_open.group(3))
        if _check(res, "fare_base_vnd", val, m_open.group(0).strip()):
            res.profile["fare_base_vnd"] = val
    # per-km tariff ("4.800đ/km" or "mỗi km tiếp theo: 4.300 đồng") and opening fare ("giá mở cửa 12k")
    take(_NUM + _UNIT + r"\s*(?:/|một|mỗi|mot|moi|trên|tren)\s*km", "fare_per_km_vnd", lambda m: _money(m.group(1), m.group(2)), res.profile)
    take(r"(?:mỗi|một|moi|mot)\s*km(?:\s*tiếp theo|\s*tiep theo|\s*sau|\s*kế tiếp)?\W{0,6}" + _NUM + _UNIT, "fare_per_km_vnd",
         lambda m: _money(m.group(1), m.group(2)), res.profile)
    take(r"(?:giá mở cửa|mở cửa|cước mở|giá khởi điểm|khởi điểm)\D{0,12}" + _NUM + _UNIT, "fare_base_vnd", lambda m: _money(m.group(1), m.group(2)), res.profile)
    # per-minute charge ("350 đồng/phút", "350đ mỗi phút") and the driver's share ("tài xế nhận 75%")
    take(_NUM + _UNIT + r"\s*(?:/|một|mỗi|mot|moi)\s*(?:phút|phut)", "fare_per_min_vnd", lambda m: _money(m.group(1), m.group(2)), res.profile)
    take(r"(?:nhận|hưởng|được|nhan|huong)\D{0,10}(\d{1,3}(?:[.,]\d+)?)\s*%", "driver_share", lambda m: _to_number(m.group(1)) / 100.0, res.profile)
    # fuel use and price
    take(_NUM + r"\s*(?:lít|lit|l)\s*(?:/|trên|tren)\s*100\s*km", "fuel_l_per_100km", lambda m: _to_number(m.group(1)), res.profile)
    take(r"(?:giá xăng|xăng)\D{0,12}" + _NUM + _UNIT, "fuel_price_vnd_per_l", lambda m: _money(m.group(1), m.group(2)), res.profile)
    # hourly goal
    take(_NUM + _UNIT + r"\s*(?:/|một|mỗi|mot|moi|trên|tren)\s*(?:giờ|gio|h|tiếng|tieng)\b", "target_vnd_per_hour", lambda m: _money(m.group(1), m.group(2)), res.profile)
    # context: radius and idle time
    take(r"(?:không đi quá|không chạy quá|tối đa|xa nhất|bán kính|trong vòng)\D{0,12}" + _NUM + r"\s*km", "max_reposition_km", lambda m: _to_number(m.group(1)), res.context)
    take(r"(?:đang rảnh|rảnh|chờ|đứng chờ|đã chờ)\D{0,10}" + _NUM + r"\s*(?:phút|phut|p\b)", "idle_duration_min", lambda m: _to_number(m.group(1)), res.context)

    # rain tolerance (order matters: negations first)
    rain_rules = (
        (r"không ngại mưa|không sợ mưa|mưa vẫn chạy|chạy mưa được|đi mưa thoải mái", "high"),
        (r"mưa nhỏ.{0,12}(?:vẫn )?(?:chạy|đi)|chịu được mưa vừa", "medium"),
        (r"mưa là nghỉ|ngại mưa|sợ mưa|không chạy (?:khi|lúc|trời) mưa|tránh mưa|mưa thì nghỉ", "low"),
    )
    for pat, level in rain_rules:
        m = re.search(pat, t)
        if m:
            res.preferences["rain_tolerance_level"] = level
            res.understood.append({"field": "rain_tolerance_level", "value": level, "from": m.group(0)})
            consumed.append(m.span())
            break

    # clauses with a number nothing explained: tell the driver instead of guessing
    pos = 0
    for clause in re.split(r"[.;\n]|,(?=\s)", t):
        start = t.find(clause, pos)
        pos = start + len(clause)
        if re.search(r"\d", clause) and not any(start <= a and b <= start + len(clause) + 1 for a, b in consumed):
            if not any(a < start + len(clause) and b > start for a, b in consumed):
                res.unparsed.append(clause.strip())
    return res


def validate_extraction(text: str, fields: dict[str, Any]) -> IntakeResult:
    """Check an externally produced (e.g. LLM) extraction: known field, in range, and the number must occur in the text."""
    res = IntakeResult()
    nums = {_to_number(m) for m in re.findall(_NUM, _fold(text))}
    expanded = set(nums) | {n * 1_000 for n in nums} | {n * 1_000_000 for n in nums} | {n / 100.0 for n in nums}  # 75% -> 0.75
    for name, value in fields.items():
        if name == "rain_tolerance_level":
            if value in ("low", "medium", "high"):
                res.preferences[name] = value
                res.understood.append({"field": name, "value": value, "from": "llm"})
            else:
                res.rejected.append({"field": name, "value": value, "from": "llm", "reason": "giá trị không hợp lệ"})
            continue
        if name not in RANGES:
            res.rejected.append({"field": name, "value": value, "from": "llm", "reason": "trường không được hỗ trợ"})
            continue
        try:
            v = float(value)
        except (TypeError, ValueError):
            res.rejected.append({"field": name, "value": value, "from": "llm", "reason": "không phải số"})
            continue
        if not any(abs(v - n) <= 1e-9 * max(1.0, abs(v)) for n in expanded):
            res.rejected.append({"field": name, "value": v, "from": "llm", "reason": "con số không có trong câu của bạn"})
            continue
        if _check(res, name, v, "llm"):
            (res.profile if name in PROFILE_FIELDS else res.context)[name] = v
    return res


def llm_extract(text: str, call_llm: Callable[[str], str]) -> IntakeResult:
    """Ask an LLM (any callable str -> str) for JSON, validate it, and fall back to the rules for whatever it got wrong."""
    prompt = (
        "Trích các trường từ câu của tài xế, chỉ trả JSON thuần, không giải thích. Chỉ dùng số xuất hiện trong câu. "
        f"Trường hợp lệ: {', '.join(list(RANGES) + ['rain_tolerance_level (low|medium|high)'])}. "
        "driver_share là phân số (75% -> 0.75).\nCâu: {text}"
    )
    try:
        data = json.loads(call_llm(prompt))
        if not isinstance(data, dict):
            raise ValueError("not an object")
    except Exception:  # noqa: BLE001 — any LLM/transport/JSON failure must degrade to the rules, never break the flow
        return parse_intake_vi(text)
    got = validate_extraction(text, data)
    rules = parse_intake_vi(text)
    for name, v in rules.profile.items():
        got.profile.setdefault(name, v)
    for name, v in rules.context.items():
        got.context.setdefault(name, v)
    for name, v in rules.preferences.items():
        got.preferences.setdefault(name, v)
    got.unparsed = rules.unparsed
    return got


def apply_to_payload(payload: dict[str, Any], res: IntakeResult) -> dict[str, Any]:
    """Merge a CONFIRMED intake into a snapshot payload (driver_profile only; context/preferences are runtime inputs)."""
    out = dict(payload)
    if res.profile:
        out["driver_profile"] = {**(payload.get("driver_profile") or {}), **res.profile}
    return out
