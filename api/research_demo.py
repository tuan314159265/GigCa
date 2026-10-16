"""Explicit synthetic demo, separate from real account records and provider data."""
import json
import os
import re
from dataclasses import asdict, fields
from datetime import date, datetime, timedelta
from pathlib import Path

from api.errors import ApiError
from api.provider_proxy import ROOT


def dataset_path():
    if os.environ.get('GIGCA_RESEARCH_DEMO', '').lower() != 'true':
        raise ApiError(404, 'demo_disabled', 'Demo nghiên cứu chưa được bật trên backend.')
    return Path(os.environ.get('GIGCA_RESEARCH_DATASET', str(
        ROOT / '.cache/synthetic/gigca-drivers-32-v2/contextual-seed7'))).resolve()


def catalog():
    root = dataset_path()
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf8'))
    if manifest.get('kind') != 'synthetic':
        raise ApiError(422, 'invalid_demo', 'Dataset không có nhãn synthetic.')
    result = []
    for folder in sorted(root.glob('D*')):
        if not re.fullmatch(r'D\d{2,3}', folder.name):
            continue
        log = json.loads((folder / 'research_log.json').read_text(encoding='utf8'))
        p = log['persona']
        from experiments.synthetic.personas import ZONES
        zone = ZONES[p['home_zone']]
        result.append({'id': p['driver_id'], 'description': p['description'],
                       'trips': len(log['trip_log']), 'waits': len(log['wait_spells']),
                       'lat': zone['lat'], 'lng': zone['lng']})
    return {'kind': 'synthetic', 'drivers': result}


def recommend_demo(payload):
    from engine.src.types import DriverContext, DriverPreferences, DriverProfile, EngineInput, TripRecord, WaitSpell, WeatherHour
    from engine.src.engine import run_driver_engine
    from engine.src.personal_model import build_personal_model
    from experiments.synthetic.generator import LOCAL, environment
    from experiments.synthetic.evaluate import json_safe

    did = payload.get('driver_id')
    if not isinstance(did, str) or not re.fullmatch(r'D\d{2,3}', did):
        raise ApiError(422, 'invalid_driver', 'Chọn tài xế mô phỏng hợp lệ.')
    root = dataset_path()
    file = root / did / 'research_log.json'
    if not file.is_file():
        raise ApiError(404, 'driver_not_found', 'Không có tài xế mô phỏng này.')
    log = json.loads(file.read_text(encoding='utf8'))
    if log.get('schema') != 'gigca_synthetic_driver_log_v1' or log.get('provenance', {}).get('kind') != 'synthetic':
        raise ApiError(422, 'invalid_demo', 'Dataset không có nhãn synthetic.')
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf8'))
    persona = log['persona']
    # Replay after all historical records, never fit on records later than replay time.
    last = max(datetime.fromisoformat(w['end']) for w in log['wait_spells'])
    replay_day = max(last.date(), date.fromisoformat(manifest['end_date'])) + timedelta(days=1)
    now = datetime.combine(replay_day, datetime.min.time(), tzinfo=LOCAL)
    now += timedelta(hours=persona['start_hour'] + 1)
    def typed(cls, row):
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in row.items() if k in names})
    # Reuse regular context/range validation without loading providers or real history.
    raw = payload.get('context', {})
    if not isinstance(raw, dict):
        raise ApiError(422, 'invalid_context', 'Ngữ cảnh không hợp lệ.')
    allowed = {'current_lat': (-90, 90), 'current_lng': (-180, 180), 'idle_duration_min': (0, 1440),
               'horizon_min': (1, 480), 'max_reposition_km': (0, 50)}
    import math
    if set(raw) - set(allowed):
        raise ApiError(422, 'invalid_context', 'Ngữ cảnh có trường không hỗ trợ.')
    for key, value in raw.items():
        low, high = allowed[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ApiError(422, 'invalid_context', f'{key} không hợp lệ.')
        if key in ('idle_duration_min', 'horizon_min') and int(value) != value:
            raise ApiError(422, 'invalid_context', f'{key} phải là số nguyên.')
    from experiments.synthetic.personas import ZONES
    zone = ZONES[persona['home_zone']]
    ctx = DriverContext(**{'current_lat': zone['lat'], 'current_lng': zone['lng'],
                           'idle_duration_min': 15, 'horizon_min': 180, 'max_reposition_km': 3, **raw})
    tolerance = payload.get('rain_tolerance_level', 'medium')
    if tolerance not in ('low', 'medium', 'high'):
        raise ApiError(422, 'invalid_context', 'Mức chịu mưa không hợp lệ.')
    hours = []
    for i in range(math.ceil(ctx.horizon_min / 60) + 1):
        at = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=i)
        rain = environment(manifest['seed'], at, persona['home_zone'])['rain_mm']
        # Realized synthetic rain does not supply a calibrated precipitation probability.
        hours.append(WeatherHour(at.isoformat(), rain, None))
    trips = [typed(TripRecord, r) for r in log['trip_log']]
    waits = [typed(WaitSpell, r) for r in log['wait_spells']]
    profile = typed(DriverProfile, log['driver_profile'])
    inp = EngineInput(weather_hourly=hours, areas=[], traffic=[],
        data_status={'weather': 'partial', 'traffic': 'missing', 'poi': 'missing',
                     'trip_value': 'missing', 'booking_and_destinations': 'missing', 'routing': 'missing'},
        objective_readiness={}, generated_at=now.isoformat(), snapshot_id=f'synthetic-{did}',
        data_label='synthetic_research_only', is_demo=True, trip_log=trips, wait_spells=waits, driver_profile=profile)
    result = asdict(run_driver_engine(inp, ctx, DriverPreferences(rain_tolerance_level=tolerance)))
    pm = build_personal_model(trips, now.replace(tzinfo=None), profile=profile, spells=waits)
    limits = ['Lịch sử và mưa mô phỏng; không phải dữ liệu tài xế thật.',
              'Tái hiện bối cảnh sau ngày cuối dataset; không dùng thời tiết/giao thông trực tiếp.',
              'Không có POI đã xác minh hoặc tuyến routing; model có thể giữ baseline hoặc thiếu dữ liệu.']
    return json_safe({**result, 'snapshot': {'id': inp.snapshot_id, 'mode': 'research', 'as_of': now.isoformat(),
        'sources': [{'dataset': 'driver_history', 'status': 'partial', 'reason': f'Synthetic {did}: {len(trips)} chuyến, {len(waits)} đợt chờ'}],
        'limitations': limits}, 'weather': [asdict(h) for h in hours], 'places': [],
        'areas': [{'id': a.area_id, 'name': a.area_name or a.area_id,
                   'lat': a.representative_point['latitude'], 'lng': a.representative_point['longitude']} for a in pm.areas],
        'origin_used': {'lat': ctx.current_lat, 'lng': ctx.current_lng}, 'is_demo': True,
        'research_driver_id': did, 'input_used': asdict(ctx)})
