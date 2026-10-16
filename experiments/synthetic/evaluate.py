"""Evaluate engine models offline: development gate and a separate final calendar holdout."""
from __future__ import annotations

import json
import math
import hashlib
from dataclasses import fields
from datetime import datetime
from pathlib import Path


def json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def evaluate_driver(log, manifest):
    # Lazy imports: generating data/persona JSON needs only the Python standard library.
    import numpy as np
    from engine.src.config import ML_CFG
    from engine.src.types import TripRecord, WaitSpell
    from engine.src.ml import wait_model as wm
    from engine.src.ml.cycle_model import CycleYieldModel, build_cycles, backtest_cycles

    if log.get('schema') != 'gigca_synthetic_driver_log_v1' or log.get('provenance', {}).get('kind') != 'synthetic':
        raise ValueError('Evaluator chỉ nhận nghiên cứu synthetic, không nhận lịch sử thật của tài xế.')
    def typed(cls, row):
        names = {f.name for f in fields(cls)}
        return cls(**{key: value for key, value in row.items() if key in names})
    trips = [typed(TripRecord, r) for r in log['trip_log']]
    spells = [typed(WaitSpell, r) for r in log['wait_spells']]
    splits = manifest['splits']
    dates = {key: set(value) for key, value in splits.items()}
    if dates['train'] & dates['calibration'] or dates['train'] & dates['test'] or dates['calibration'] & dates['test']:
        raise ValueError('Các tập ngày bị trùng nhau.')
    def day(value):
        return datetime.fromisoformat(value).date().isoformat()
    development = [w for w in spells if day(w.start) in dates['train'] | dates['calibration']]
    test_spells = [w for w in spells if day(w.start) in dates['test']]
    gate = wm.backtest_wait(development)
    report = {'kind': 'synthetic_research_only', 'driver_id': log['persona']['driver_id'],
              'ml_config': dict(ML_CFG),
              'wait_development_gate': gate, 'wait_final_holdout': {'status': 'insufficient'},
              'limitations': ['Metrics are for virtual drivers only; no real-world performance claim.',
                  'Existing engine wait model uses hour/weekend/rain/coordinates, not traffic directly.',
                  'Historical realized rain is synthetic; forecast error is not modeled in this version.']}
    model = wm.fit_wait_model(development)
    if model is not None and len(test_spells) >= int(ML_CFG['min_holdout_spells']):
        train_obs, test_obs = wm._observations(development), wm._observations(test_spells)
        b, nb = wm._bins(ML_CFG)
        hm, hb = model.hazards(test_obs), wm._baseline_hazards(train_obs, test_obs, b, nb)
        report['wait_final_holdout'] = {'status': 'ok', 'n_test': len(test_obs),
            'nll_candidate': wm._nll(hm, test_obs, b, nb), 'nll_km_baseline': wm._nll(hb, test_obs, b, nb),
            'candidate_enabled_by_development_gate': bool(gate.get('passes')),
            'note': 'Final test never used to decide the development gate or fit either candidate.'}
    fuel = log['driver_profile']['fuel_l_per_100km'] * log['driver_profile']['fuel_price_vnd_per_l'] / 100
    matching = {}
    cycles = build_cycles(trips, spells, fuel, matching_report=matching)
    grouped = {key: [c for c in cycles if c.start.date().isoformat() in value] for key, value in dates.items()}
    dev_cycles = grouped['train'] + grouped['calibration']
    observed_events = sum(w.ended_by == 'trip' for w in spells)
    report['cycle_matching'] = {'trips': len(trips), 'waits_ended_by_trip': observed_events,
        'policy': matching['policy'], 'counts': matching['counts'],
        'matched_cycles': len(cycles), 'unmatched_trips': len(trips) - len(cycles),
        'matched_fraction': len(cycles) / max(1, len(trips)),
        'note': 'Current engine requires a mutually unique causal pair, acceptance->pickup gap <=5min and distance <=500m. '
                'No timestamps or coordinates were changed to force a match; excluded long pickup legs bias the subset.'}
    report['cycle_development_backtest'] = backtest_cycles(dev_cycles)
    report['cycle_final_holdout'] = {'status': 'insufficient', 'split_counts': {k: len(v) for k, v in grouped.items()}}
    if len(dev_cycles) >= int(ML_CFG['min_cycles']) and len(grouped['train']) >= 30 and len(grouped['calibration']) >= 15 and grouped['test']:
        model = CycleYieldModel(float(ML_CFG['conformal_alpha']), int(ML_CFG['random_state'])).fit(
            grouped['train'], grouped['calibration'])
        from engine.src.ml.cycle_model import _features
        test = grouped['test']
        lo, md, hi = model.predict_many(_features(test, model.ref))
        y = np.asarray([c.yield_vnd_per_hour for c in test])
        avg = float(np.mean([c.yield_vnd_per_hour for c in grouped['train']]))
        report['cycle_final_holdout'] = {'status': 'ok', 'n_test': len(test),
            'nominal_coverage': 1 - float(ML_CFG['conformal_alpha']),
            'observed_coverage': float(np.mean((lo <= y) & (y <= hi))),
            'mean_interval_width_vnd_per_hour': float(np.mean(hi - lo)),
            'mae_candidate_vnd_per_hour': float(np.mean(np.abs(y - md))),
            'mae_train_mean_baseline_vnd_per_hour': float(np.mean(np.abs(y - avg))),
            'coverage_assessment': 'too_few_test_cycles' if len(test) < 30 else 'research_measurement_only',
            'note': 'Calendar train/calibration/test are disjoint; interval covers one selected wait+trip cycle, '
                    'not a whole shift and not guaranteed under drift.'}
    return json_safe(report)


def evaluate_dataset(folder, driver_id=None):
    folder = Path(folder)
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf8'))
    if manifest.get('kind') != 'synthetic':
        raise ValueError('Dataset không mang nhãn synthetic.')
    paths = sorted(folder.glob('D*/research_log.json'))
    if driver_id:
        paths = [p for p in paths if p.parent.name == driver_id]
    if not paths:
        raise ValueError('Không tìm thấy tài xế ảo cần đánh giá.')
    result = {'kind': 'synthetic_research_only', 'world': manifest['world'], 'seed': manifest['seed'],
              'reports': [evaluate_driver(json.loads(p.read_text(encoding='utf8')), manifest) for p in paths]}
    import numpy
    import sklearn
    root = Path(__file__).resolve().parents[2]
    result['versions'] = {'numpy': numpy.__version__, 'scikit_learn': sklearn.__version__,
        'engine_config_sha256': hashlib.sha256((root / 'config/engine_config.json').read_bytes()).hexdigest(),
        'engine_code_sha256': hashlib.sha256(b''.join(p.read_bytes() for p in sorted((root / 'engine/src').rglob('*.py')))).hexdigest()}
    target = folder / (f'evaluation_{driver_id}.json' if driver_id else 'evaluation.json')
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')
    lines = ['# Kết quả nghiên cứu dữ liệu tổng hợp', '',
        '**Không phải đánh giá trên tài xế thật. Không dùng kết quả này để bật model sản phẩm.**', '',
        f"World: `{manifest['world']}`; seed: `{manifest['seed']}`. Train/calibration/test theo ngày, test cuối độc lập.", '',
        '| Tài xế ảo | Cuốc | Chu kỳ ghép được | Gate chờ | NLL test ML / KM | MAE thu nhập ML / baseline (đ/h) | Độ phủ test |',
        '| --- | ---: | ---: | --- | --- | --- | --- |']
    for report in result['reports']:
        matched, wait, cycle = report['cycle_matching'], report['wait_final_holdout'], report['cycle_final_holdout']
        nll = f"{wait['nll_candidate']:.3f} / {wait['nll_km_baseline']:.3f}" if wait['status'] == 'ok' else 'Thiếu mẫu'
        mae = f"{cycle['mae_candidate_vnd_per_hour']:.0f} / {cycle['mae_train_mean_baseline_vnd_per_hour']:.0f}" if cycle['status'] == 'ok' else 'Thiếu mẫu'
        cover = f"{100 * cycle['observed_coverage']:.1f}% (n={cycle['n_test']})" if cycle['status'] == 'ok' else 'Thiếu mẫu'
        if cycle['status'] == 'ok' and cycle['n_test'] < 30:
            cover += ' — chưa đủ mẫu'
        gate = 'Đạt' if report['wait_development_gate'].get('passes') else 'Giữ baseline'
        lines.append(f"| {report['driver_id']} | {matched['trips']} | {matched['matched_cycles']} | {gate} | {nll} | {mae} | {cover} |")
    lines += ['', 'NLL/MAE thấp hơn là tốt hơn. Gate được quyết định trên development, không dựa test cuối.',
              'Độ phủ mục tiêu 80% chỉ là mức danh nghĩa; đo được trên synthetic không bảo đảm trên dữ liệu thật.',
              'Các chặng đi đón dài có thể bị engine loại khi ghép chu kỳ; xem cycle_matching trong JSON.',
              'Nhiên liệu/giá/cơ hội nhận cuốc/routing đều dựa giả thuyết đã ghi trong manifest.', '']
    target.with_suffix('.md').write_text('\n'.join(lines), encoding='utf8')
    return target, result
