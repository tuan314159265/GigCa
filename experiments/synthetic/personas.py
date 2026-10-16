"""Validated persona contract, reference design and optional local Ollama generation."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

# Geographic anchors only, NOT verified pickup/parking places or a demand dataset.
ZONES = {
    'Z1': {'name': 'Trung tâm - điểm neo giả định', 'lat': 10.773, 'lng': 106.699},
    'Z2': {'name': 'Phía bắc trung tâm - điểm neo giả định', 'lat': 10.788, 'lng': 106.694},
    'Z3': {'name': 'Phía tây trung tâm - điểm neo giả định', 'lat': 10.777, 'lng': 106.680},
    'Z4': {'name': 'Phía đông bắc - điểm neo giả định', 'lat': 10.802, 'lng': 106.712},
    'Z5': {'name': 'Phía tây - điểm neo giả định', 'lat': 10.790, 'lng': 106.665},
    'Z6': {'name': 'Phía nam - điểm neo giả định', 'lat': 10.760, 'lng': 106.704},
}

RANGES = {
    'start_hour': (5, 18), 'shift_hours': (2, 10), 'work_probability': (.25, 1),
    'patience_min': (5, 60), 'move_probability': (.1, .95), 'pickup_radius_m': (50, 1200),
    'rain_tolerance_mm': (.2, 10), 'driver_share': (.5, .9),
    'fuel_l_per_100km': (1.2, 4), 'fuel_price_vnd_per_l': (15000, 35000),
}

PERSONA_SCHEMA = {
    'type': 'object', 'additionalProperties': False, 'required': ['personas'],
    'properties': {'personas': {'type': 'array', 'minItems': 1, 'maxItems': 50, 'items': {
        'type': 'object', 'additionalProperties': False,
        'required': ['driver_id', 'description', 'home_zone', 'preferred_zones', *RANGES],
        'properties': {
            'driver_id': {'type': 'string', 'pattern': '^D[0-9]{2,3}$'},
            'description': {'type': 'string', 'minLength': 1, 'maxLength': 500},
            'home_zone': {'type': 'string', 'enum': list(ZONES)},
            'preferred_zones': {'type': 'array', 'minItems': 1, 'maxItems': 6, 'uniqueItems': True,
                                'items': {'type': 'string', 'enum': list(ZONES)}},
            **{key: {'type': 'number', 'minimum': low, 'maximum': high}
               for key, (low, high) in RANGES.items()},
        },
    }}},
}


def validate_personas(document, zone_catalog=None):
    catalog = ZONES if zone_catalog is None else zone_catalog
    if not isinstance(document, dict) or not isinstance(document.get('personas'), list):
        raise ValueError('Cần object có personas[].')
    rows = document['personas']
    if not 1 <= len(rows) <= 50:
        raise ValueError('Cần 1–50 persona.')
    seen = set()
    required = {'driver_id', 'description', 'home_zone', 'preferred_zones', *RANGES}
    for row in rows:
        if not isinstance(row, dict) or set(row) != required:
            raise ValueError('Persona thiếu trường hoặc có trường không hỗ trợ.')
        did = row['driver_id']
        if not isinstance(did, str) or not re.fullmatch(r'D\d{2,3}', did) or did in seen:
            raise ValueError('driver_id phải duy nhất, dạng D01.')
        seen.add(did)
        if not isinstance(row['description'], str) or not 1 <= len(row['description']) <= 500:
            raise ValueError('description không hợp lệ.')
        zones = row['preferred_zones']
        if not isinstance(row['home_zone'], str) or row['home_zone'] not in catalog or not isinstance(zones, list) or not zones or len(zones) > 6:
            raise ValueError('Vùng hoạt động không hợp lệ.')
        if any(not isinstance(z, str) or z not in catalog for z in zones) or len(set(zones)) != len(zones):
            raise ValueError('preferred_zones phải là các zone_id duy nhất.')
        for key, (low, high) in RANGES.items():
            value = row[key]
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f'{did}.{key} ngoài miền hợp lệ.')
        if row['start_hour'] + row['shift_hours'] > 23:
            raise ValueError('Ca phải kết thúc trước 23h (có thể tăng ca do chuyến cuối).')
    return rows


def reference_personas(count=12):
    if not 1 <= count <= 50:
        raise ValueError('Cần 1–50 persona.')
    rows = []
    for i in range(count):
        home = list(ZONES)[i % len(ZONES)]
        morning, part_time = i % 2 == 0, i % 3 == 0
        rows.append({
            'driver_id': f'D{i + 1:02}',
            'description': f'Tài xế ảo {"bán thời gian" if part_time else "toàn thời gian"}, '
                           f'ca {"sáng" if morning else "chiều"}; thiết kế tham chiếu, không phải người thật.',
            'home_zone': home, 'preferred_zones': [home, list(ZONES)[(i + 1) % len(ZONES)]],
            'start_hour': 7 if morning else 14, 'shift_hours': 4 if part_time else 8,
            'work_probability': .7 if part_time else .85, 'patience_min': 12 + (i % 4) * 7,
            'move_probability': .35 + (i % 3) * .2, 'pickup_radius_m': [150, 400, 900][i % 3],
            'rain_tolerance_mm': [1, 3, 7][i % 3], 'driver_share': .65 + (i % 3) * .05,
            'fuel_l_per_100km': 1.8 + (i % 4) * .25, 'fuel_price_vnd_per_l': 22000,
        })
    document = {'personas': rows, 'provenance': {'kind': 'synthetic', 'persona_source': 'reference_design',
        'note': 'Các tham số là giả thuyết nghiên cứu; không phải phân bố tài xế TP.HCM đã đo.'}}
    validate_personas(document)
    return document


def prompt_bundle(count):
    return {
        'schema': PERSONA_SCHEMA,
        'system': 'Bạn thiết kế persona tổng hợp cho nghiên cứu. Không tạo dữ liệu người thật, không khẳng định '
                  'giả thuyết là thống kê thực. Chỉ trả JSON theo schema, không Markdown.',
        'prompt': f'Tạo đúng {count} persona tài xế xe máy ảo đa dạng. Dùng các zone_id này: '
                  f'{json.dumps(ZONES, ensure_ascii=False)}. Các điểm chỉ là neo giả định. '
                  'Đa dạng ca sáng/chiều, toàn/bán thời gian, kiên nhẫn, chuyển vùng, bán kính đón và chịu mưa. '
                  'start_hour + shift_hours <= 23. Các giá trị trong RANGES là giả thuyết; '
                  'không chọn tham số nhằm bảo đảm ML thắng baseline. Không sinh giá cuốc/thời gian chờ thực tế. '
                  f'Schema: {json.dumps(PERSONA_SCHEMA)}',
    }


def ollama_personas(model, count, seed=7, base_url='http://127.0.0.1:11434'):
    parsed = urlsplit(base_url)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.query or parsed.fragment:
        raise ValueError('Ollama base URL không hợp lệ; không đặt secret trong URL.')
    bundle = prompt_bundle(count)
    body = {'model': model, 'stream': False, 'format': bundle['schema'],
            'messages': [{'role': 'system', 'content': bundle['system']}, {'role': 'user', 'content': bundle['prompt']}],
            'options': {'seed': seed, 'temperature': .4}}
    try:
        request = Request(base_url.rstrip('/') + '/api/chat', json.dumps(body).encode(),
                          {'Content-Type': 'application/json'})
        with urlopen(request, timeout=180) as response:
            result = json.load(response)
        document = json.loads(result['message']['content'])
    except Exception:
        raise RuntimeError('Không lấy được persona JSON từ Ollama. Kiểm tra server/model; không tự tải model.') from None
    rows = validate_personas(document)
    if len(rows) != count:
        raise ValueError('LLM không trả đúng số persona; không tự sửa hoặc bổ sung hồ sơ.')
    document['provenance'] = {'kind': 'synthetic', 'persona_source': 'ollama', 'model': model, 'seed': seed,
        'prompt_sha256': hashlib.sha256(json.dumps(bundle, sort_keys=True).encode()).hexdigest()}
    return document


def compatible_personas(count, model=None, env_file=None, *, bundle=None, zone_catalog=None):
    """Cloud persona generation; dotenv values never appear in output/errors."""
    settings = {}
    path = Path(env_file) if env_file else Path(__file__).resolve().parents[2] / '.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            key, sep, value = line.strip().partition('=')
            if sep and key in ('GIGCA_LLM_BASE_URL', 'GIGCA_LLM_API_KEY', 'GIGCA_LLM_MODEL'):
                settings[key] = value.strip().strip('\"\'')
    for key in ('GIGCA_LLM_BASE_URL', 'GIGCA_LLM_API_KEY', 'GIGCA_LLM_MODEL'):
        if key in os.environ:
            settings[key] = os.environ[key]
    base = settings.get('GIGCA_LLM_BASE_URL', 'https://api.shopaikey.com/v1').rstrip('/')
    model = model or settings.get('GIGCA_LLM_MODEL')
    key = settings.get('GIGCA_LLM_API_KEY')
    parsed = urlsplit(base)
    if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.query or parsed.fragment:
        raise ValueError('LLM base URL phải là HTTPS, không chứa secret/query.')
    if not key or not model:
        raise ValueError('Điền GIGCA_LLM_API_KEY và GIGCA_LLM_MODEL trong .env hoặc biến môi trường.')
    bundle = bundle or prompt_bundle(count)
    body = {'model': model, 'stream': False,
            'messages': [{'role': 'system', 'content': bundle['system']},
                         {'role': 'user', 'content': bundle['prompt']}]}
    try:
        request = Request(base + '/chat/completions', json.dumps(body).encode('utf8'),
                          {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        with urlopen(request, timeout=180) as response:
            result = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f'LLM HTTP {exc.code}; kiểm tra key, model, hạn mức. Không tự gọi lại.') from None
    except Exception:
        raise RuntimeError('Không kết nối được LLM; kiểm tra mạng/chứng chỉ. Không tự gọi lại.') from None
    try:
        choice = result['choices'][0]
        reason = choice.get('finish_reason')
        content = choice['message']['content']
    except (KeyError, IndexError, TypeError):
        raise RuntimeError('Provider thiếu choices[0].message.content trong response chat.') from None
    if reason != 'stop':
        label = reason if reason in ('length', 'content_filter', 'tool_calls', None) else 'unknown'
        raise RuntimeError(f'LLM chưa hoàn tất văn bản: finish_reason={label}. Không lưu đầu ra bị cắt.')
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError('LLM trả content rỗng hoặc không phải chuỗi văn bản.')
    content = content.strip()
    # Accept presentation-only fences; never extract arbitrary JSON from prose.
    fenced = re.fullmatch(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL | re.IGNORECASE)
    if fenced:
        content = fenced.group(1).strip()
    try:
        document = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'LLM trả văn bản không phải JSON: dòng {exc.lineno}, cột {exc.colno}. '
                           'Không lưu dữ liệu; thử model hỗ trợ sinh JSON tốt hơn.') from None
    try:
        rows = validate_personas(document, zone_catalog)
        if len(rows) != count:
            raise ValueError(f'Yêu cầu {count} persona nhưng nhận {len(rows)}.')
    except ValueError as exc:
        # Validator errors contain fixed messages and model-authored IDs only.
        detail = str(exc)
        if key in detail:
            detail = detail.replace(key, '[redacted]')
        raise RuntimeError(f'JSON persona không đạt schema: {detail}') from None
    document['provenance'] = {'kind': 'synthetic', 'persona_source': 'openai_compatible',
        'provider': parsed.hostname, 'model': model, 'usage': result.get('usage'),
        'prompt_sha256': hashlib.sha256(json.dumps(bundle, sort_keys=True).encode()).hexdigest()}
    return document
