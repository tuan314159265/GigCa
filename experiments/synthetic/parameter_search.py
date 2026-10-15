"""Bounded search on the existing unseen-driver validation split only."""
import random


def configurations(trials, seed):
    if not 1 <= trials <= 100:
        raise ValueError('trials phải từ 1 đến 100.')
    rng = random.Random(seed)
    baseline = dict(learning_rate=0.06, max_depth=2, min_samples_leaf=8, subsample=0.8)
    result = [baseline]
    while len(result) < trials:
        item = dict(learning_rate=rng.choice([0.02, 0.05, 0.1]), max_depth=rng.choice([1, 2, 3]),
                    min_samples_leaf=rng.choice([8, 20, 40]), subsample=rng.choice([0.7, 0.9, 1.0]))
        if item not in result:
            result.append(item)
    return result


def search_parameters(train_obs, validation_obs, train_cycles, validation_cycles, cfg, seed, trials):
    import numpy as np
    from sklearn.metrics import mean_pinball_loss
    from engine.src.ml import wait_model as wm
    from engine.src.ml.cycle_model import _features, _qreg

    wait_rows = []
    b, nb = wm._bins(cfg)
    for use_context in (True, False):
        for c in (0.01, 0.1, 0.5, 1.0, 5.0):
            model = wm.WaitHazardModel(cfg, use_context=use_context, regularization_c=c).fit(train_obs)
            score = wm._nll(model.hazards(validation_obs), validation_obs, b, nb)
            wait_rows.append({'use_context': use_context, 'C': c, 'validation_nll': score})
            print(f'[wait] context={use_context} C={c:g} validation NLL={score:.6f}', flush=True)
    best_wait = min((r for r in wait_rows if r['use_context']), key=lambda r:r['validation_nll'])
    best_plain = min((r for r in wait_rows if not r['use_context']), key=lambda r:r['validation_nll'])
    ref = (float(np.mean([c.lat for c in train_cycles])), float(np.mean([c.lng for c in train_cycles])))
    xt, xv = _features(train_cycles, ref), _features(validation_cycles, ref)
    yt = np.array([c.yield_vnd_per_hour for c in train_cycles])
    yv = np.array([c.yield_vnd_per_hour for c in validation_cycles])
    cycle_rows, selected = [], {}
    candidates = configurations(trials, seed)
    for name, q in [('lower', float(cfg['conformal_alpha'])/2), ('median', 0.5), ('upper', 1-float(cfg['conformal_alpha'])/2)]:
        best = None
        for index, params in enumerate(candidates, 1):
            model = _qreg(q, seed, {**params, 'n_estimators': 200}).fit(xt, yt)
            for step, prediction in enumerate(model.staged_predict(xv), 1):
                if step not in (40, 80, 120, 160, 200):
                    continue
                score = float(mean_pinball_loss(yv, prediction, alpha=q))
                row = {'quantile': name, 'trial': index, 'params': {**params, 'n_estimators': step},
                       'validation_pinball_loss': score}
                cycle_rows.append(row)
                if best is None or score < best['validation_pinball_loss']:
                    best = row
            print(f'[cycle {name}] trial {index}/{trials}; best validation loss={best["validation_pinball_loss"]:.3f}', flush=True)
        selected[name] = best['params']
    return {'wait_C': best_wait['C'], 'no_context_C': best_plain['C'], 'quantile_params': selected}, {
        'method': 'seeded_random_search_plus_fixed_boosting_checkpoints', 'selection_split': 'validation',
        'trials_per_quantile': trials, 'seed': seed, 'test_used_for_selection': False,
        'calibration_used_for_selection': False, 'wait_trials': wait_rows, 'cycle_trials': cycle_rows,
        'limitations': ['Single validation split; this is not nested cross-validation.',
                        'Best means best among searched candidates, not a global optimum.',
                        'Existing test has already been inspected in earlier experiments.']}
