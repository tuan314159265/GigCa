"""python -m experiments.synthetic --help"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from .generator import LOCAL, generate, write_dataset
from .personas import compatible_personas, ollama_personas, prompt_bundle, reference_personas


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline synthetic driver research; never imports to product DB.')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('prompt', 'personas'):
        p = sub.add_parser(name)
        p.add_argument('--count', type=int, default=12)
        p.add_argument('--output', type=Path, required=True)
        if name == 'personas':
            p.add_argument('--provider', choices=['reference', 'ollama', 'compatible'])
            p.add_argument('--env-file', type=Path, help='Default: repo root .env; only LLM settings are read.')
            p.add_argument('--model', help='Optional already-installed Ollama model; otherwise labeled reference design.')
            p.add_argument('--ollama-url', default='http://127.0.0.1:11434')
            p.add_argument('--seed', type=int, default=7)
    p = sub.add_parser('generate')
    p.add_argument('--personas', type=Path, help='Validated JSON from prompt/Ollama. Default: reference design.')
    p.add_argument('--drivers', type=int, default=12)
    p.add_argument('--zones', type=Path, help='Explicit expanded anchors.json; remaps home/preferred zones on a copy.')
    p.add_argument('--days', type=int, default=42)
    p.add_argument('--end-date', type=date.fromisoformat, default=datetime.now(LOCAL).date() - timedelta(days=1))
    p.add_argument('--seed', type=int, default=7)
    p.add_argument('--world', choices=['contextual', 'null', 'drift'], default='contextual')
    p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('evaluate')
    p.add_argument('dataset', type=Path)
    p.add_argument('--driver', help='Evaluate only this virtual driver, e.g. D02.')
    p = sub.add_parser('train-base')
    p.add_argument('dataset', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seed', type=int, default=7)
    p.add_argument('--plots', action='store_true', help='Export learning curves and final test figures (PNG/SVG/CSV).')
    p = sub.add_parser('search-params')
    p.add_argument('dataset', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seed', type=int, default=7)
    p.add_argument('--trials', type=int, choices=range(1, 101), default=30, metavar='1..100')
    p.add_argument('--plots', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command in ('prompt', 'personas'):
            if not 1 <= args.count <= 50:
                raise ValueError('count phải từ 1 đến 50.')
            if args.output.exists():
                raise ValueError('File output đã tồn tại; chọn file mới.')
            if args.command == 'prompt':
                result = prompt_bundle(args.count)
            elif args.provider == 'compatible':
                result = compatible_personas(args.count, args.model, args.env_file)
            elif args.provider == 'ollama' or (args.model and args.provider is None):
                if not args.model:
                    raise ValueError('Ollama cần --model.')
                result = ollama_personas(args.model, args.count, args.seed, args.ollama_url)
            else:
                result = reference_personas(args.count)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')
            print(args.output)
        elif args.command == 'generate':
            document = json.loads(args.personas.read_text(encoding='utf8')) if args.personas else reference_personas(args.drivers)
            zones = None
            if args.zones:
                from .geography import load_zone_catalog, remap_personas
                zones = load_zone_catalog(args.zones)
                document = remap_personas(document, zones)
            dataset = generate(document, end_date=args.end_date, days=args.days, seed=args.seed, world=args.world, zone_catalog=zones)
            if args.zones:
                import hashlib
                dataset['manifest']['geography_source'] = {'path':str(args.zones),
                    'sha256':hashlib.sha256(args.zones.read_bytes()).hexdigest(),
                    'destination_decay_km':5, 'note':'Distance weighting is a simulation assumption, not measured HCMC OD.'}

            target = write_dataset(dataset, args.output)
            reports = dataset['manifest']['validation']
            print(json.dumps({'output': str(target), 'kind': 'synthetic', 'drivers': len(reports),
                'trips': sum(r['trips'] for r in reports.values()),
                'wait_spells': sum(r['wait_spells'] for r in reports.values()),
                'all_timelines_valid': all(r['valid'] for r in reports.values())}, ensure_ascii=False))
        elif args.command in ('train-base', 'search-params'):
            from .train_base import train_base
            target, report = train_base(args.dataset, args.output, args.seed, plots=args.plots,
                                        search_trials=args.trials if args.command == 'search-params' else 0)
            print(json.dumps({'output': str(target), 'development_gate': report['development_gate'],
                              'production_enabled': False}, ensure_ascii=False))
        else:
            from .evaluate import evaluate_dataset
            target, result = evaluate_dataset(args.dataset, args.driver)
            print(json.dumps({'report': str(target), 'drivers_evaluated': len(result['reports']),
                              'kind': 'synthetic_research_only'}, ensure_ascii=False))
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        parser.exit(2, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
