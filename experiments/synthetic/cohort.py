"""Stratified hypothetical personas. Inspired by papers, not their reproduction."""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

from .personas import PERSONA_SCHEMA, ZONES, compatible_personas, validate_personas

VERSION = 'gigca-stratified-personas-v2'
REFERENCES = [
    'https://arxiv.org/html/2402.14744v3',
    'https://arxiv.org/html/2304.03442v2',
    'https://arxiv.org/html/2406.14541v3',
]


def design(replicates=2):
    if replicates not in (1, 2, 3):
        raise ValueError('replicates must be 1, 2 or 3 (16, 32 or 48 personas).')
    slots = []
    cells = itertools.product(('morning', 'afternoon'), ('part_time', 'full_time'),
                              ('patient', 'relocator'), ('rain_averse', 'rain_tolerant'))
    for cell, (shift, work, strategy, rain) in enumerate(cells, 1):
        for replicate in range(1, replicates + 1):
            index = len(slots)
            slots.append({'driver_id': f'D{index + 1:03}', 'cell': f'C{cell:02}',
                'replicate': replicate, 'shift': shift, 'work': work, 'strategy': strategy,
                'rain': rain, 'home_zone': list(ZONES)[index % len(ZONES)],
                'bounds': {
                    'start_hour': [6, 8] if shift == 'morning' else [13, 15],
                    'shift_hours': [3, 4.5] if work == 'part_time' else [7, 8],
                    'work_probability': [.45, .75] if work == 'part_time' else [.8, .95],
                    'patience_min': [25, 45] if strategy == 'patient' else [7, 15],
                    'move_probability': [.15, .35] if strategy == 'patient' else [.65, .85],
                    'rain_tolerance_mm': [.4, 1.5] if rain == 'rain_averse' else [4, 8],
                    'pickup_radius_m': [[100, 300], [350, 650], [750, 1100]][index % 3],
                }})
    return slots


def cohort_prompt(slots, zone_catalog=None):
    zones = ZONES if zone_catalog is None else zone_catalog
    schema = json.loads(json.dumps(PERSONA_SCHEMA))
    props = schema['properties']['personas']['items']['properties']
    props['home_zone']['enum'] = list(zones)
    props['preferred_zones']['items']['enum'] = list(zones)
    from .generator import distance_km
    required_preferences = {}
    for slot in slots:
        home = slot['home_zone']
        nearest = min((z for z in zones if z != home), key=lambda z: distance_km(
            (zones[home]['lat'], zones[home]['lng']), (zones[z]['lat'], zones[z]['lng'])))
        required_preferences[slot['driver_id']] = [home, nearest]
    return {'schema': schema,
        'system': (
            'You design hypothetical motorcycle ride-hailing driver personas for controlled research. '
            'Return one JSON object matching the supplied schema, without Markdown or commentary. '
            'Distinguish habitual routines and preferences from situational motivations. '
            'No observed driver histories or measured population statistics are available. '
            'Never invent empirical evidence, real identities, or claim statistical representativeness. '
            'The design bounds are experimental assumptions, not results established by the cited papers.'),
        'prompt': (
            f'Create exactly {len(slots)} personas, one for each prescribed slot in the given order. '
            'Use its exact driver_id and home_zone. Satisfy every slot-specific numeric bound. '
            'Choose remaining numeric values within the JSON schema. start_hour + shift_hours <= 23. '
            'Use preferred_zones containing the home_zone and at least one other supplied zone. '
            'Write each description in English (max 500 characters): state its habitual routine, '
            'a plausible work motivation, waiting/relocation policy and rain response; '
            'the description must agree with the numeric fields. Do not add new fields. '
            'Vary values within each cell; two replicates must not be numeric clones. '
            'Do not conflate rain tolerance with willingness to accept distant pickups. '
            'These are research design cells, not discovered driver categories. '
            'Do not generate trip rows, fares, weather, demand probabilities or GPS trajectories; '
            'the sequential simulator calculates dependent event fields. '
            'Do not optimize personas to make a predictive model outperform a baseline. '
            'Before returning, silently check completeness, unique IDs, all bounds and cross-field consistency. '
            'This is inspired by LLMob routine/persona conditioning and Generative Agents planning concepts; '
            'it does not implement their historical retrieval, reflection or empirical alignment. '
            'Dependency validation is inspired by warnings about table generation; this is not PAFT fine-tuning. '
            'IMPORTANT: copy preferred_zones EXACTLY from this driver-specific mapping. '
            'Do not substitute HCM001/HCM002 as defaults. The first entry MUST equal that driver home_zone. '
            f'Required preferred_zones mapping: {json.dumps(required_preferences)}\n'
            f'Prescribed slots: {json.dumps(slots)}\n'
            f'Geographic anchors (hypothetical, not verified pickup sites): {json.dumps(zones)}\n'
            f'Output schema: {json.dumps(schema)}')}


def validate_slots(document, slots, zone_catalog=None):
    rows = validate_personas(document, zone_catalog)
    if [r['driver_id'] for r in rows] != [s['driver_id'] for s in slots]:
        raise ValueError('Persona IDs/order do not match prescribed slots.')
    for row, slot in zip(rows, slots):
        if row['home_zone'] != slot['home_zone']:
            raise ValueError(f"{slot['driver_id']}: home_zone differs from design.")
        if row['home_zone'] not in row['preferred_zones'] or len(row['preferred_zones']) < 2:
            raise ValueError(f"{slot['driver_id']}: preferred_zones must include home and another zone.")
        for key, (low, high) in slot['bounds'].items():
            if not low <= row[key] <= high:
                raise ValueError(f"{slot['driver_id']}: {key} outside prescribed cell.")
    by_cell = {}
    for row, slot in zip(rows, slots):
        signature = tuple(row[k] for k in slot['bounds'])
        if signature in by_cell.setdefault(slot['cell'], set()):
            raise ValueError(f"{slot['cell']}: replicated numeric clone.")
        by_cell[slot['cell']].add(signature)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--replicates', type=int, default=2)
    parser.add_argument('--zones', type=Path, help='Expanded anchors used in persona prompt and schema.')
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--plan-only', action='store_true')
    parser.add_argument('--resume', action='store_true', help='Reuse valid batches; request invalid/missing batches again.')
    args = parser.parse_args()
    try:
        if args.output.exists() and not args.resume:
            raise ValueError('Output folder already exists; select a new path.')
        slots = design(args.replicates)
        zones = None
        if args.zones:
            from .geography import load_zone_catalog
            zones = load_zone_catalog(args.zones)
            ids = list(zones)
            for i, slot in enumerate(slots):
                slot['home_zone'] = ids[i*len(ids)//len(slots)]
        args.output.mkdir(parents=True, exist_ok=args.resume)
        plan = {'version': VERSION, 'kind': 'synthetic', 'slots': slots, 'references': REFERENCES,
                'note': 'Balanced experimental coverage; not population sampling or a power calculation.'}
        if zones is not None: plan['zone_catalog'] = zones
        plan_path = args.output / 'design.json'
        if args.resume and (not plan_path.exists() or json.loads(plan_path.read_text(encoding='utf8')) != plan):
            raise ValueError('Resume design differs; choose original replicates or a new folder.')
        plan_path.write_text(json.dumps(plan, indent=2), encoding='utf8')
        all_rows, batches = [], []
        for offset in range(0, len(slots), 4):
            batch_slots = slots[offset:offset + 4]
            bundle = cohort_prompt(batch_slots, zones)
            prefix = args.output / f'batch-{offset // 4 + 1:02}'
            saved = prefix.with_suffix('.response.json')
            if args.resume and saved.exists():
                prior = json.loads(saved.read_text(encoding='utf8'))
                try:
                    validate_slots(prior, batch_slots, zones)
                except ValueError as exc:
                    bundle['prompt'] += ('\nPrevious response failed deterministic validation: ' + str(exc)
                        + '. Generate a fresh complete batch respecting ALL bounds. Previous response: '
                        + json.dumps({'personas': prior['personas']}))
                    attempt = 1
                    archive = prefix.with_suffix(f'.rejected-{attempt}.json')
                    while archive.exists():
                        attempt += 1
                        archive = prefix.with_suffix(f'.rejected-{attempt}.json')
                    saved.rename(archive)
                    prior_prompt = prefix.with_suffix('.prompt.json')
                    if prior_prompt.exists():
                        prior_prompt.rename(prefix.with_suffix(f'.rejected-{attempt}.prompt.json'))
                else:
                    all_rows.extend(prior['personas'])
                    batches.append(prior['provenance'])
                    print(f'Batch {offset // 4 + 1}: reused validated batch', flush=True)
                    continue
            prefix.with_suffix('.prompt.json').write_text(json.dumps(bundle, indent=2), encoding='utf8')
            if args.plan_only:
                continue
            document = compatible_personas(len(batch_slots), env_file=args.env_file, bundle=bundle, zone_catalog=zones)
            # Preserve valid-schema output for audit even if design-cell validation fails.
            prefix.with_suffix('.response.json').write_text(json.dumps(document, indent=2), encoding='utf8')
            validate_slots(document, batch_slots, zones)
            all_rows.extend(document['personas'])
            batches.append(document['provenance'])
            print(f'Batch {offset // 4 + 1}: {len(all_rows)}/{len(slots)} validated', flush=True)
        if not args.plan_only:
            result = {'personas': all_rows, 'provenance': {'kind': 'synthetic',
                'persona_source': 'llm_stratified_design', 'version': VERSION,
                'design': plan, 'batches': batches, 'references': REFERENCES}}
            validate_slots(result, slots, zones)
            (args.output / 'personas.json').write_text(json.dumps(result, indent=2), encoding='utf8')
        print(args.output)
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(2, f'Error: {exc}\nCompleted batches remain on disk; no automatic paid retry.\n')


if __name__ == '__main__':
    main()
