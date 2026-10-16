"""Sequential synthetic shifts with shared environment and explicit hypothesis metadata."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .personas import ZONES, validate_personas

LOCAL = timezone(timedelta(hours=7))
VERSION = 'gigca-synthetic-v1'
ROOT = Path(__file__).resolve().parents[2]
TRIP_COLUMNS = ['trip_id', 'started_at', 'pickup_lat', 'pickup_lng', 'net_vnd', 'duration_min',
                'dropoff_lat', 'dropoff_lng', 'distance_km', 'source_kind']
WAIT_COLUMNS = ['spell_id', 'start', 'end', 'lat', 'lng', 'ended_by', 'rain_mm', 'source_kind']
HYPOTHESES = {'wait_scale_min': 11, 'wait_weibull_shape': 1.25, 'route_detour': 1.3,
    'paid_duration_noise_sigma': .12, 'fare_noise_sigma': .04,
    'note': 'Design parameters, not estimated HCMC market statistics. No live API is called.'}


def stable_seed(*parts):
    return int.from_bytes(hashlib.sha256('|'.join(map(str, parts)).encode()).digest()[:8], 'big')


def distance_km(a, b):
    la, lb = math.radians(a[0]), math.radians(b[0])
    dlat, dlng = lb - la, math.radians(b[1] - a[1])
    h = math.sin(dlat / 2) ** 2 + math.cos(la) * math.cos(lb) * math.sin(dlng / 2) ** 2
    return 6371 * 2 * math.asin(min(1, math.sqrt(h)))


def near(point, radius_m, rng):
    radius, angle = math.sqrt(rng.random()) * radius_m / 1000, rng.uniform(0, 2 * math.pi)
    return (point[0] + radius * math.sin(angle) / 111.32,
            point[1] + radius * math.cos(angle) / (111.32 * math.cos(math.radians(point[0]))))


def environment(seed, at, zone):
    # Shared weather by date/hour, spatially modulated. Independent of driver RNG/order.
    common = random.Random(stable_seed(seed, at.date(), at.hour, 'weather'))
    wet = common.random() < (.35 if 13 <= at.hour <= 20 else .12)
    rain = common.uniform(.3, 7) if wet else 0
    local = random.Random(stable_seed(seed, zone, 'environment'))
    rain *= local.uniform(.8, 1.2)
    rush = 7 <= at.hour <= 9 or 16 <= at.hour <= 19
    speed = max(8, 28 * (.65 if rush else 1) * (1 / (1 + rain * .06)) * local.uniform(.9, 1.1))
    return {'rain_mm': round(rain, 3), 'speed_kmh': round(speed, 3), 'source_kind': 'synthetic'}


def wait_time(rng, world, day_index, days, at, zone, env, seed):
    scale = HYPOTHESES['wait_scale_min']
    if world != 'null':
        effect = random.Random(stable_seed(seed, zone, 'opportunity')).uniform(-.45, .45)
        if world == 'drift' and day_index >= int(days * .8):
            effect = -effect
        hour_effect = .3 * math.sin(2 * math.pi * (at.hour - 9) / 24)
        rain_effect = -.04 * env['rain_mm']
        if world == 'drift' and day_index >= int(days * .8):
            rain_effect = .08 * env['rain_mm']
        scale *= math.exp(effect + hour_effect + rain_effect + (.1 if at.weekday() >= 5 else 0))
    return max(.2, rng.weibullvariate(scale, HYPOTHESES['wait_weibull_shape']))


def route(a, b, speed, rng, *, noisy=False):
    km = max(.01, distance_km(a, b) * HYPOTHESES['route_detour'])
    duration = km / speed * 60
    if noisy:
        duration *= rng.lognormvariate(0, HYPOTHESES['paid_duration_noise_sigma'])
    return round(km, 4), max(.1, duration)


def fare(km, duration, persona, tariff, rng):
    billable = max(0, km - tariff['fare_base_km'])
    gross = tariff['fare_base_vnd'] + billable * tariff['fare_per_km_vnd']
    gross += duration * billable / km * tariff['fare_per_min_vnd']
    gross *= rng.lognormvariate(0, HYPOTHESES['fare_noise_sigma'])
    return round(gross), round(gross * persona['driver_share'])


def iso(at):
    return at.isoformat(timespec='seconds')


def run_driver(persona, end_date, days, seed, world, tariff, zone_catalog=None, shift_plan=None, point_allowed=None):
    zones = ZONES if zone_catalog is None else zone_catalog
    rng = random.Random(stable_seed(seed, persona['driver_id'], world))
    trips, waits, events = [], [], []
    previous_end, position = None, None
    start_date = end_date - timedelta(days=days - 1)
    def sample(point, radius):
        if point_allowed is None: return near(point,radius,rng)
        for _ in range(100):
            candidate=near(point,radius,rng)
            if point_allowed(candidate): return candidate
        if point_allowed(point): return point
        raise ValueError('No sample inside study boundary.')

    def event(kind, at, duration, a, b=None, **extra):
        end = at + timedelta(seconds=max(1, round(duration * 60)))
        point = b or a
        events.append({'type': kind, 'start': iso(at), 'end': iso(end),
            'start_point': list(a), 'end_point': list(point), 'source_kind': 'synthetic', **extra})
        return end

    for day_index in range(days):
        day = start_date + timedelta(days=day_index)
        scheduled = shift_plan.get((persona['driver_id'], day.isoformat())) if shift_plan is not None else None
        if shift_plan is not None:
            if scheduled is None: continue
        elif rng.random() > persona['work_probability']:
            continue
        at = datetime.combine(day, datetime.min.time(), LOCAL) + timedelta(hours=persona['start_hour'], minutes=rng.randint(0, 20))
        shift_end = at + timedelta(hours=persona['shift_hours'])
        zone = scheduled if shift_plan is not None else persona['home_zone']
        preferred = persona['preferred_zones'] if shift_plan is None else sorted(zones,
            key=lambda z:distance_km((zones[zone]['lat'],zones[zone]['lng']), (zones[z]['lat'],zones[z]['lng'])))[:6]
        home = sample((zones[zone]['lat'], zones[zone]['lng']), 50)
        if previous_end is not None:
            # Off-app travel/rest explains the next day's new position, not a teleported active trip.
            at = event('off_shift', previous_end, (at - previous_end).total_seconds() / 60, position, home,
                       route_method='unobserved_off_shift')
        position = home
        while at < shift_end:
            env = environment(seed, at, zone)
            trip_wait = wait_time(rng, world, day_index, days, at, zone, env, seed)
            leave = max(2, persona['patience_min'] * rng.uniform(.7, 1.3))
            if env['rain_mm'] > persona['rain_tolerance_mm']:
                leave *= .6
            remaining = (shift_end - at).total_seconds() / 60
            observed = min(trip_wait, leave, remaining)
            ended = 'trip' if trip_wait < min(leave, remaining) else (
                'moved' if leave < remaining and rng.random() < persona['move_probability'] else 'offline')
            sid = f"{persona['driver_id']}_W{len(waits) + 1:05}"
            start = at
            at = event('wait', at, observed, position, spell_id=sid, ended_by=ended, zone_id=zone, **env)
            waits.append({'spell_id': sid, 'start': iso(start), 'end': iso(at),
                          'lat': position[0], 'lng': position[1], 'ended_by': ended,
                          'rain_mm': env['rain_mm'], 'source_kind': 'synthetic'})
            if ended == 'trip':
                accepted_at = at
                pickup = sample(position, persona['pickup_radius_m'])
                pickup_km, pickup_min = route(position, pickup, env['speed_kmh'], rng)
                at = event('pickup_travel', at, pickup_min + .5, position, pickup,
                           distance_km=pickup_km, route_method='straight_line_detour_assumption', spell_id=sid)
                pickup_at = at
                if zone_catalog is not None and zone_catalog != ZONES:
                    ids = list(zones)
                    weights = [math.exp(-distance_km(position, (zones[z]['lat'], zones[z]['lng'])) / 5) if distance_km(position,(zones[z]['lat'], zones[z]['lng'])) <= 20 else 0 for z in ids]
                    destination_zone = rng.choices(ids, weights=weights, k=1)[0]
                else:
                    destination_zone = rng.choice(list(zones))
                anchor = (zones[destination_zone]['lat'], zones[destination_zone]['lng'])
                target = sample(anchor, 300)
                km, paid_min = route(pickup, target, env['speed_kmh'], rng, noisy=True)
                tid = f"{persona['driver_id']}_T{len(trips) + 1:05}"
                at = event('paid_trip', at, paid_min, pickup, target, trip_id=tid, spell_id=sid,
                           request_accepted_at=iso(accepted_at), distance_km=km, zone_id=zone,
                           destination_zone=destination_zone, route_method='straight_line_detour_assumption')
                duration = (at - pickup_at).total_seconds() / 60
                gross, net = fare(km, duration, persona, tariff, rng)
                events[-1].update({'gross_vnd': gross, 'net_vnd': net, 'pickup_travel_km': pickup_km,
                                  'pickup_travel_min': (pickup_at - accepted_at).total_seconds() / 60})
                trips.append({'trip_id': tid, 'started_at': iso(pickup_at), 'pickup_lat': pickup[0],
                    'pickup_lng': pickup[1], 'net_vnd': net, 'duration_min': duration,
                    'dropoff_lat': target[0], 'dropoff_lng': target[1], 'distance_km': km, 'source_kind': 'synthetic'})
                position, zone = target, destination_zone
            elif ended == 'moved':
                choices = preferred
                if shift_plan is not None:
                    choices = [z for z in zones if distance_km(position,(zones[z]['lat'],zones[z]['lng'])) <= 10]
                    if not choices: choices=[zone]
                zone = rng.choice(choices)
                target = sample((zones[zone]['lat'], zones[zone]['lng']), 50)
                km, duration = route(position, target, env['speed_kmh'], rng)
                at = event('reposition', at, duration, position, target, distance_km=km,
                           route_method='straight_line_detour_assumption')
                position = target
            elif at < shift_end:
                at = event('rest', at, rng.uniform(10, 25), position)
        previous_end = at
    profile = {key: persona[key] for key in ('driver_share', 'fuel_l_per_100km', 'fuel_price_vnd_per_l')}
    profile.update({key: tariff[key] for key in ('fare_base_vnd', 'fare_base_km', 'fare_per_km_vnd', 'fare_per_min_vnd')})
    return {'schema': 'gigca_synthetic_driver_log_v1', 'provenance': {'kind': 'synthetic',
            'generator': VERSION, 'driver_id': persona['driver_id'], 'world': world, 'seed': seed,
            'not_for_production': True}, 'persona': persona, 'driver_profile': profile,
            'trip_log': trips, 'wait_spells': waits, 'events': events}


def validate_log(log):
    errors, previous = [], None
    if log.get('provenance', {}).get('kind') != 'synthetic':
        errors.append('missing synthetic provenance')
    for event in log['events']:
        start, end = datetime.fromisoformat(event['start']), datetime.fromisoformat(event['end'])
        if end <= start:
            errors.append('non-positive event duration')
        if previous and (start != previous[0] or distance_km(previous[1], event['start_point']) > .001):
            errors.append('timeline overlap/gap or position discontinuity')
        if 'distance_km' in event:
            direct = distance_km(event['start_point'], event['end_point'])
            if event['distance_km'] + .001 < direct:
                errors.append('route shorter than straight line')
            speed = event['distance_km'] / ((end - start).total_seconds() / 3600)
            if speed > 80:
                errors.append('implausible speed >80 km/h in designed scenario')
        previous = (end, event['end_point'])
    for key, id_key in (('trip_log', 'trip_id'), ('wait_spells', 'spell_id')):
        if len({r[id_key] for r in log[key]}) != len(log[key]):
            errors.append('duplicate record ID')
        if any(r.get('source_kind') != 'synthetic' for r in log[key]):
            errors.append('untagged record')
    paid = {e['trip_id']: e for e in log['events'] if e['type'] == 'paid_trip'}
    spells = {w['spell_id']: w for w in log['wait_spells']}
    for trip in log['trip_log']:
        event = paid.get(trip['trip_id'])
        if event is None or event['start'] != trip['started_at']:
            errors.append('trip missing its linked paid event')
            continue
        duration = (datetime.fromisoformat(event['end']) - datetime.fromisoformat(event['start'])).total_seconds() / 60
        if abs(duration - trip['duration_min']) > .001 or event['net_vnd'] != trip['net_vnd']:
            errors.append('trip time/fare inconsistent with timeline')
        if trip['net_vnd'] <= 0 or trip['net_vnd'] > event['gross_vnd']:
            errors.append('invalid net/gross fare')
        wait = spells.get(event['spell_id'])
        if not wait or wait['ended_by'] != 'trip' or wait['end'] != event['request_accepted_at']:
            errors.append('trip missing its linked acceptance/wait')
    return {'valid': not errors, 'errors': sorted(set(errors)),
            'trips': len(log['trip_log']), 'wait_spells': len(log['wait_spells']),
            'censored': sum(w['ended_by'] != 'trip' for w in log['wait_spells'])}


def calendar_splits(end_date, days):
    dates = [(end_date - timedelta(days=days - 1 - i)).isoformat() for i in range(days)]
    a, b = max(1, int(days * .55)), max(2, int(days * .8))
    return {'train': dates[:a], 'calibration': dates[a:b], 'test': dates[b:]}


def generate(document, *, end_date, days=42, seed=7, world='contextual', zone_catalog=None, shift_plan=None, point_allowed=None):
    zones = ZONES if zone_catalog is None else zone_catalog
    if world not in ('contextual', 'null', 'drift') or not 7 <= days <= 180:
        raise ValueError('world=contextual/null/drift; days=7–180.')
    personas = validate_personas(document, zones)
    tariff = json.loads((ROOT / 'config/engine_config.json').read_text(encoding='utf8'))['tariff']
    logs = [run_driver(p, end_date, days, seed, world, tariff, zones, shift_plan, point_allowed) for p in personas]
    reports = {log['persona']['driver_id']: validate_log(log) for log in logs}
    if any(not r['valid'] for r in reports.values()):
        raise ValueError(f'Invalid generated timeline: {reports}')
    return {'manifest': {'schema': VERSION, 'kind': 'synthetic', 'not_for_production': True,
        'seed': seed, 'world': world, 'days': days, 'end_date': end_date.isoformat(),
        'persona_provenance': document.get('provenance', {'persona_source': 'external_unverified'}),
        'personas_sha256': hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest(),
        'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'hypotheses': HYPOTHESES, 'tariff': tariff,
        'zone_catalog': zones,
        'splits': calendar_splits(end_date, days), 'validation': reports,
        'limitations': ['No actual driver, booking or demand observations.',
            'Geographic anchors are not verified road/parking coordinates. Routing is a declared approximation.',
            'started_at is pickup time; wait ends at acceptance. Engine matching may exclude long pickup legs.',
            'No guarantees of real-world accuracy or 80% interval coverage.']}, 'drivers': logs}


def write_dataset(dataset, output):
    output = Path(output)
    if output.exists():
        raise ValueError('Output đã tồn tại; chọn thư mục mới để không ghi đè nghiên cứu cũ.')
    output.mkdir(parents=True)
    for log in dataset['drivers']:
        folder = output / log['persona']['driver_id']
        folder.mkdir()
        (folder / 'research_log.json').write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding='utf8')
        for filename, key, columns in (('trips.csv', 'trip_log', TRIP_COLUMNS), ('waits.csv', 'wait_spells', WAIT_COLUMNS)):
            with (folder / filename).open('w', encoding='utf8', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=columns)
                writer.writeheader()
                writer.writerows(log[key])
    (output / 'manifest.json').write_text(json.dumps(dataset['manifest'], ensure_ascii=False, indent=2), encoding='utf8')
    return output
