"""Offline pooled synthetic models; artifacts are candidates, never auto-enabled."""
from __future__ import annotations

import hashlib
import json
import platform
import random
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path

from .evaluate import json_safe


def driver_split(ids, slots, seed):
    """One replica of every design cell in train; unseen replicas in holdouts."""
    rng = random.Random(seed)
    cells = {}
    for slot in slots:
        if slot['driver_id'] in ids:
            cells.setdefault(slot['cell'], []).append(slot['driver_id'])
    if not cells or set(ids) != {i for group in cells.values() for i in group}:
        raise ValueError('Cần manifest có design slots phủ đúng tất cả tài xế.')
    train, held = [], []
    for cell in sorted(cells):
        group = sorted(cells[cell])
        if len(group) < 2:
            raise ValueError('Mỗi type cần ít nhất hai tài xế để kiểm tra cold-start.')
        rng.shuffle(group)
        train.append(group[0])
        held.extend(group[1:])
    rng.shuffle(held)
    if len(held) < 4:
        raise ValueError('Không đủ tài xế holdout.')
    middle = len(held) // 2
    return {'train': sorted(train), 'validation': sorted(held[:middle]), 'test': sorted(held[middle:])}


def train_base(dataset, output, seed=7, plots=False, search_trials=0):
    import joblib
    import numpy as np
    import sklearn
    from engine.src.config import ML_CFG
    from engine.src.types import TripRecord, WaitSpell
    from engine.src.ml import wait_model as wm
    from engine.src.ml.cycle_model import CycleYieldModel, build_cycles, _features

    dataset, output = Path(dataset), Path(output)
    if output.exists():
        raise ValueError('Output đã tồn tại; chọn thư mục phiên bản mới để giữ kết quả cũ.')
    if plots:
        try:
            import matplotlib
        except ImportError as exc:
            raise ValueError(
                f'Không import được matplotlib: {exc}. '
                'Nếu pip báo đã cài, hãy cài lại bằng đúng Python đang chạy: '
                'python -m pip install --force-reinstall --no-cache-dir --no-deps "matplotlib>=3.8,<4"'
            ) from None
    manifest_path = dataset / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf8'))
    if manifest.get('kind') != 'synthetic':
        raise ValueError('Chỉ nhận dataset synthetic có provenance.')
    paths = sorted(dataset.glob('D*/research_log.json'))
    slots = manifest.get('persona_provenance', {}).get('design', {}).get('slots', [])
    split = driver_split([p.parent.name for p in paths], slots, seed)
    dates = {k: set(v) for k, v in manifest['splits'].items()}
    if any(dates[a] & dates[b] for a, b in [('train', 'calibration'), ('train', 'test'), ('calibration', 'test')]):
        raise ValueError('Ngày train/calibration/test bị trùng.')
    if not all(dates.values()) or not max(dates['train']) < min(dates['calibration']) <= max(dates['calibration']) < min(dates['test']):
        raise ValueError('Các tập ngày phải có thứ tự thời gian và không rỗng.')
    groups = {k: {'waits': [], 'cycles': [], 'rows': []} for k in ('train', 'validation', 'calibration', 'test')}
    hashes = {'manifest.json': hashlib.sha256(manifest_path.read_bytes()).hexdigest()}
    matching_reports = {}
    def typed(cls, row):
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in row.items() if k in names})
    for path in paths:
        log = json.loads(path.read_text(encoding='utf8'))
        if log.get('schema') != 'gigca_synthetic_driver_log_v1' or log.get('provenance', {}).get('kind') != 'synthetic':
            raise ValueError(f'Log không hợp lệ: {path.parent.name}')
        did = path.parent.name
        if log['persona']['driver_id'] != did:
            raise ValueError('Driver ID không khớp thư mục.')
        hashes[str(path.relative_to(dataset))] = hashlib.sha256(path.read_bytes()).hexdigest()
        waits = [typed(WaitSpell, r) for r in log['wait_spells']]
        trips = [typed(TripRecord, r) for r in log['trip_log']]
        profile = log['driver_profile']
        fuel = profile['fuel_l_per_100km'] * profile['fuel_price_vnd_per_l'] / 100
        matching = {}
        cycles = build_cycles(trips, waits, fuel, matching_report=matching)
        matching_reports[did] = matching
        for name, group in groups.items():
            drivers = split['validation'] if name == 'calibration' else split[name]
            days = dates['calibration'] if name == 'calibration' else dates['test'] if name == 'test' else dates['train']
            if did not in drivers:
                continue
            selected = [w for w in waits if datetime.fromisoformat(w.start).date().isoformat() in days
                        and datetime.fromisoformat(w.end).date().isoformat() in days]
            group['waits'].extend(selected)
            group['cycles'].extend(c for c in cycles if c.start.date().isoformat() in days)
            group['rows'].extend({'driver_id': did, 'spell_id': w.spell_id, 'start': w.start} for w in selected)
    if any(len(g['waits']) < 30 or len(g['cycles']) < 30 for g in groups.values()):
        raise ValueError('Mỗi split cần ít nhất 30 waits và 30 cycles.')
    obs = {k: wm._observations(g['waits']) for k, g in groups.items()}
    cfg = dict(ML_CFG)
    params = {'wait_C': 0.5, 'no_context_C': 0.5, 'quantile_params': {}}
    search_report = None
    if search_trials:
        from .parameter_search import search_parameters
        params, search_report = search_parameters(obs['train'], obs['validation'], groups['train']['cycles'],
                                                  groups['validation']['cycles'], cfg, seed, search_trials)
    wait = wm.WaitHazardModel(cfg, regularization_c=params['wait_C']).fit(obs['train'])
    plain = wm.WaitHazardModel(cfg, use_context=False, regularization_c=params['no_context_C']).fit(obs['train'])
    cycle = CycleYieldModel(float(cfg['conformal_alpha']), seed, params['quantile_params']).fit(groups['train']['cycles'], groups['calibration']['cycles'])
    b, nb = wm._bins(cfg)
    mean = float(np.mean([c.yield_vnd_per_hour for c in groups['train']['cycles']]))
    def metrics(name):
        test = obs[name]
        cs = groups[name]['cycles']
        lo, md, hi = cycle.predict_many(_features(cs, cycle.ref))
        y = np.array([c.yield_vnd_per_hour for c in cs])
        return {'wait_nll': wm._nll(wait.hazards(test), test, b, nb),
                'wait_km_nll': wm._nll(wm._baseline_hazards(obs['train'], test, b, nb), test, b, nb),
                'wait_no_context_nll': wm._nll(plain.hazards(test), test, b, nb),
                'cycle_mae_vnd_per_hour': float(np.mean(abs(y-md))),
                'cycle_mean_baseline_mae': float(np.mean(abs(y-mean))),
                'cycle_coverage': float(np.mean((lo <= y) & (y <= hi))),
                'cycle_mean_interval_width': float(np.mean(hi-lo))}
    validation = metrics('validation')
    # Calibration days follow validation days: never use that interval to validate
    # earlier outcomes. Median MAE is independent of the conformal correction.
    validation.pop('cycle_coverage')
    validation.pop('cycle_mean_interval_width')
    gain = float(cfg['min_gain_nll'])
    gate = {'wait': validation['wait_km_nll'] - validation['wait_nll'] >= gain
                    and validation['wait_no_context_nll'] - validation['wait_nll'] >= gain,
            'cycle': validation['cycle_mae_vnd_per_hour'] < validation['cycle_mean_baseline_mae']}
    # Only measure test after the development decisions; do not tune on its scores.
    final_test = metrics('test')
    root = Path(__file__).resolve().parents[2]
    report = {'schema': 'gigca_pooled_model_v1', 'kind': 'synthetic_research_only',
              'created_at': datetime.now(timezone.utc).isoformat(), 'seed': seed,
              'production_enabled': False, 'development_gate': gate,
              'model_name': 'logistic-hazard-quantile-gb', 'selected_parameters': params,
              'hyperparameter_search': search_report is not None,
              'cycle_matching': {did: {k: v for k, v in value.items() if k != 'rows'}
                                 for did, value in matching_reports.items()},
              'validation': validation, 'test': final_test,
              'counts': {k: {'waits': len(g['waits']), 'cycles': len(g['cycles'])} for k, g in groups.items()},
              'driver_splits': split, 'date_splits': manifest['splits'], 'config': cfg,
              'versions': {'python': platform.python_version(), 'numpy': np.__version__, 'sklearn': sklearn.__version__, 'joblib': joblib.__version__},
              'input_sha256': hashes,
              'engine_sha256': hashlib.sha256(b''.join(p.read_bytes() for p in sorted((root/'engine/src').rglob('*.py')))).hexdigest(),
              'limitations': ['Synthetic only; no evidence of real-world accuracy.',
                  'Train: one driver per type, early days; validation: unseen drivers, early days.',
                  'Calibration: validation drivers on later calibration days; test: different unseen drivers on final days.',
                  'Holdout drivers share a synthetic world; this does not establish transfer to real drivers.',
                  'Conservative 5min/500m matching excludes distant/ambiguous pickups; target excludes pickup/reposition/offline costs.',
                  'Missing rain is interpreted as dry by existing engine features.',
                  'Artifacts are not automatically connected to dashboard; load only trusted local joblib files.']}
    output.mkdir(parents=True)
    (output/'best_params.json').write_text(json.dumps(params, indent=2), encoding='utf8')
    if search_report is not None:
        (output/'search_results.json').write_text(json.dumps(search_report, indent=2, allow_nan=False), encoding='utf8')
    (output/'matching.json').write_text(json.dumps(matching_reports, ensure_ascii=False, indent=2), encoding='utf8')
    joblib.dump({'schema': report['schema'], 'kind': report['kind'], 'wait_model': wait, 'cycle_model': cycle,
                 'config': cfg, 'selected_parameters': params, 'development_gate': gate}, output/'models.joblib', compress=3)
    # Round-trip proves fitted parameters and predictions survive serialization.
    restored = joblib.load(output/'models.joblib')
    np.testing.assert_allclose(wait.hazards(obs['test'][:2]), restored['wait_model'].hazards(obs['test'][:2]))
    for expected, actual in zip(cycle.predict_many(_features(groups['test']['cycles'][:2], cycle.ref)),
                                restored['cycle_model'].predict_many(_features(groups['test']['cycles'][:2], cycle.ref))):
        np.testing.assert_allclose(expected, actual)
    report['artifact_sha256'] = hashlib.sha256((output/'models.joblib').read_bytes()).hexdigest()
    if plots:
        from .learning_plots import write_learning_plots
        report['learning_plots'] = write_learning_plots(output, obs, groups, wait, cycle, cfg, seed)
    (output/'report.json').write_text(json.dumps(json_safe(report), ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')
    (output/'splits.json').write_text(json.dumps({k: g['rows'] for k, g in groups.items()}, indent=2), encoding='utf8')
    return output, report
