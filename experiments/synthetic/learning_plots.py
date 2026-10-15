"""Offline report figures. Test scores never select an estimator or a boosting step."""
from __future__ import annotations

import csv
import json
from pathlib import Path


def write_learning_plots(output, obs, groups, wait, cycle, cfg, seed):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from sklearn.metrics import mean_pinball_loss
    from engine.src.ml import wait_model as wm
    from engine.src.ml.cycle_model import _features

    folder = Path(output) / 'plots'
    folder.mkdir()
    plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False,
                         'savefig.dpi': 200, 'figure.figsize': (8, 5)})
    tables = {}

    def save(fig, name):
        fig.text(0.5, 0.01, 'Synthetic data only — not evidence of real-world performance', ha='center', fontsize=8)
        fig.tight_layout(rect=(0, 0.04, 1, 1))
        fig.savefig(folder / f'{name}.png')
        fig.savefig(folder / f'{name}.svg')
        plt.close(fig)

    # These are independent fits at different sample sizes, not optimizer epochs.
    order = np.random.default_rng(seed).permutation(len(obs['train']))
    rows = []
    b, nb = wm._bins(cfg)
    for fraction in (0.2, 0.4, 0.6, 0.8, 1.0):
        subset = [obs['train'][i] for i in order[:max(30, int(len(order)*fraction))]]
        model = wait if fraction == 1.0 else wm.WaitHazardModel(cfg, regularization_c=getattr(wait, 'regularization_c', 0.5)).fit(subset)
        rows.append({'n_train_spells': len(subset),
                     'train_nll': wm._nll(model.hazards(subset), subset, b, nb),
                     'validation_nll': wm._nll(model.hazards(obs['validation']), obs['validation'], b, nb)})
    tables['wait_learning_curve'] = rows
    fig, ax = plt.subplots()
    for key, label in [('train_nll', 'Train'), ('validation_nll', 'Validation (unseen drivers)')]:
        ax.plot([r['n_train_spells'] for r in rows], [r[key] for r in rows], marker='o', label=label)
    ax.set(title='Wait hazard: learning curve by sample size', xlabel='Training wait spells', ylabel='Censored NLL (lower is better)')
    ax.legend()
    save(fig, 'wait_learning_curve')

    train, val = groups['train']['cycles'], groups['validation']['cycles']
    xt, xv = _features(train, cycle.ref), _features(val, cycle.ref)
    yt = np.array([c.yield_vnd_per_hour for c in train])
    yv = np.array([c.yield_vnd_per_hour for c in val])
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    for ax, (name, estimator, quantile) in zip(axes, [
        ('lower', cycle._lo, cycle.alpha/2), ('median', cycle._md, 0.5), ('upper', cycle._hi, 1-cycle.alpha/2)]):
        rows = [{'step': step, 'train_pinball_loss': float(mean_pinball_loss(yt, pt, alpha=quantile)),
                 'validation_pinball_loss': float(mean_pinball_loss(yv, pv, alpha=quantile))}
                for step, (pt, pv) in enumerate(zip(estimator.staged_predict(xt), estimator.staged_predict(xv)), 1)]
        tables[f'cycle_boosting_{name}'] = rows
        ax.plot([r['step'] for r in rows], [r['train_pinball_loss'] for r in rows], label='Train')
        ax.plot([r['step'] for r in rows], [r['validation_pinball_loss'] for r in rows], label='Validation')
        ax.set(title=f'Quantile {quantile:.0%}', xlabel='Boosting step', ylabel='Pinball loss (VND/hour)')
        ax.legend()
    save(fig, 'cycle_boosting_loss')

    # Censoring-aware observed probabilities via Kaplan–Meier, not naive event fractions.
    test_obs = obs['test']
    hazards = wait.hazards(test_obs)
    fig, ax = plt.subplots()
    for threshold in (10, 20):
        probabilities = np.array([wm._summarise(h, b, [threshold])['p_le'][str(threshold)] for h in hazards])
        rows = wm._calibration(probabilities, test_obs, threshold, groups=5)
        tables[f'wait_test_calibration_{threshold}min'] = rows
        ax.plot([r['predicted_pct'] for r in rows], [r['observed_pct'] for r in rows], marker='o', label=f'{threshold} minutes')
    ax.plot([0, 100], [0, 100], '--', color='gray', label='Ideal calibration')
    ax.set(title='Final test: wait probability calibration', xlabel='Mean predicted probability (%)',
           ylabel='Observed probability, Kaplan–Meier (%)', xlim=(0, 100), ylim=(0, 100))
    ax.legend()
    save(fig, 'wait_test_calibration')

    cs = groups['test']['cycles']
    lo, md, hi = cycle.predict_many(_features(cs, cycle.ref))
    actual = np.array([c.yield_vnd_per_hour for c in cs])
    idx = np.argsort(md, kind='stable')
    tables['cycle_test_predictions'] = [
        {'start': cs[i].start.isoformat(), 'lat': cs[i].lat, 'lng': cs[i].lng,
         'actual_vnd_per_hour': float(actual[i]), 'low': float(lo[i]), 'median': float(md[i]), 'high': float(hi[i])}
        for i in idx]
    fig, ax = plt.subplots()
    ax.fill_between(range(len(idx)), lo[idx], hi[idx], alpha=0.2, label='Calibrated nominal 80% interval')
    ax.plot(md[idx], label='Predicted median')
    ax.scatter(range(len(idx)), actual[idx], s=10, color='black', alpha=0.5, label='Observed synthetic cycle')
    coverage = float(np.mean((lo <= actual) & (actual <= hi)))
    ax.set(title=f'Final test: cycle intervals; coverage {coverage:.1%} (n={len(idx)})',
           xlabel='Cycles sorted by predicted median (not time)', ylabel='Cycle yield (VND/hour)')
    ax.legend()
    save(fig, 'cycle_test_intervals')

    for name, rows in tables.items():
        with (folder / f'{name}.csv').open('w', encoding='utf8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    (folder / 'curves.json').write_text(json.dumps(tables, indent=2, allow_nan=False), encoding='utf8')
    (folder / 'README.md').write_text(
        '# Learning figures\n\nPNG (200 dpi) and SVG for reports; CSV/JSON contain source values.\n\n'
        '- Wait curve: five independent fits, fixed seeded nested random subsets of training spells; not epochs. '
        'One seed only, no confidence bands; small differences are not significance tests.\n'
        '- Boosting curves: raw quantile pinball loss at each fitted stage; conformal correction is not applied. '
        'No early stopping or model selection from these plots.\n'
        '- Test calibration: five equal-count prediction groups, censoring-aware Kaplan–Meier estimates; '
        'no confidence bands and dependent synthetic observations.\n'
        '- Test intervals: all test cycles, sorted by median prediction; not a time series.\n'
        '- Test is used for final reporting only; never choose parameters by inspecting test plots.\n'
        '- All figures describe synthetic data, not performance on real drivers.\n', encoding='utf8')
    return {'directory': 'plots', 'matplotlib_version': matplotlib.__version__,
            'wait_learning_curve_fractions': [0.2, 0.4, 0.6, 0.8, 1.0],
            'learning_curve_seed': seed, 'test_used_for_selection': False}
