"""Bounded live destination discovery; training anchors only define model support."""
import hashlib
import math
from concurrent.futures import ThreadPoolExecutor

from engine.src.geo import haversine_m
from engine.src.scorers._common import reposition_for


def discover(ctx, anchors, *, prefer_landmarks=True):
    from api.llm_explanations import cached, fetch_nearby, poi_group, normalized
    from api.provider_proxy import tomtom_url

    if ctx.max_reposition_km <= 0:
        return [], {'status': 'current_only', 'source': 'TomTom Nearby Search'}
    # Routing is resolved after ranking; enforce the engine's distance budget too.
    radius = min(3000, int(ctx.max_reposition_km * 1000))
    # Nearby Search is nearest-first: one request in a dense city may only cover
    # the first block, even with a large radius. Probe four surrounding sectors.
    probes = [(ctx.current_lat, ctx.current_lng, radius, 100)]
    supported_radius = min(radius, radius / max(1, reposition_for(1000).km))
    if supported_radius >= 400:
        offset = supported_radius * .65
        dy = offset / 111320
        dx = dy / max(.01, math.cos(math.radians(ctx.current_lat)))
        probes += [(ctx.current_lat+y, ctx.current_lng+x,
                    min(600, max(150, int(supported_radius*.4))), 25)
                   for y, x in ((dy, 0), (-dy, 0), (0, dx), (0, -dx))]

    def fetch(probe):
        lat, lng, search_radius, limit = probe
        try:
            params = {
                'lat': lat, 'lon': lng, 'radius': search_radius, 'limit': limit,
                'language': 'vi-VN', 'countrySet': 'VN'}
            if prefer_landmarks:
                # Provider taxonomy IDs, not a fixed list of destination names.
                params['categorySet'] = '7377,7373,7332003,7321,9382,9383'
            endpoint = 'categorySearch' if prefer_landmarks else 'nearbySearch'
            url = tomtom_url(f'https://api.tomtom.com/search/2/{endpoint}/.json', params)
            raw = cached(('live_destinations_landmarks_v1', prefer_landmarks, lat, lng, search_radius, limit),
                         300, lambda: fetch_nearby(url))
            rows = raw.get('results')
            return rows if isinstance(rows, list) else None
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        batches = list(pool.map(fetch, probes))
    if all(batch is None for batch in batches):
        raise ValueError('live_destinations_unavailable')
    results = [row for batch in batches if batch is not None for row in batch]
    candidates = []
    seen = set()
    for item in results:
        pos = item.get('position', {})
        poi = item.get('poi', {})
        lat, lng, name = pos.get('lat'), pos.get('lon'), poi.get('name')
        if not isinstance(name, str) or not name.strip():
            continue
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                   and math.isfinite(v) for v in (lat, lng)):
            continue
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            continue
        distance = haversine_m(ctx.current_lat, ctx.current_lng, lat, lng)
        if distance < 80 or distance > radius or reposition_for(distance, {'at_area_radius_m': 0}).km > ctx.max_reposition_km:
            continue
        if min(haversine_m(lat, lng, a['lat'], a['lng']) for a in anchors) > 2000:
            continue
        identity = str(item.get('id') or f'{name.strip().casefold()}:{lat:.5f}:{lng:.5f}')
        coordinate = (round(lat, 4), round(lng, 4))
        if identity in seen or coordinate in seen:
            continue
        seen.update((identity, coordinate))
        category, _ = poi_group(poi)
        if prefer_landmarks:
            codes = {c.get('code') for c in poi.get('classifications', []) if isinstance(c, dict)}
            labels = normalized(' '.join(v for v in poi.get('categories', []) if isinstance(v, str)))
            large_facility = bool(codes & {'COLLEGE_UNIVERSITY', 'COMMERCIAL_BUILDING',
                'INDUSTRIAL_BUILDING', 'SHOPPING_CENTER', 'HOSPITAL', 'HEALTH_CARE_SERVICE', 'MARKET'})
            large_facility = large_facility or any(term in labels for term in (
                'university', 'college', 'commercial building', 'office building',
                'industrial building', 'industrial park', 'shopping center', 'shopping centre',
                'shopping mall', 'public market', 'hospital'))
            if not large_facility or any(term in labels for term in ('clinic', 'dental', 'pharmacy')):
                continue
            # Some storefronts are incorrectly tagged as malls/buildings. Require
            # a facility-style name as well for those ambiguous provider classes.
            title = normalized(name)
            commercial = 'COMMERCIAL_BUILDING' in codes or any(t in labels for t in ('commercial building', 'office building'))
            shopping = 'SHOPPING_CENTER' in codes or any(t in labels for t in ('shopping center', 'shopping centre', 'shopping mall'))
            if (commercial or shopping) and not any(t in title for t in (
                    'building', 'tower', 'toa nha', 'cao oc', 'center', 'centre',
                    'plaza', 'mall', 'trung tam thuong mai', 'tttm', 'complex')):
                continue
            if commercial:
                category = 'office'
        # Category does not add any ranking bonus. Spatial round-robin avoids a
        # single cluster of shops filling the entire bounded inference budget.
        bearing = math.atan2((lng-ctx.current_lng)*math.cos(math.radians(ctx.current_lat)),
                             lat-ctx.current_lat)
        sector = int((bearing + math.pi) / (2*math.pi) * 8) % 8
        band = min(2, int(distance / max(100, supported_radius / 3)))
        candidates.append(((sector, band), distance, {
            'id': 'live_' + hashlib.sha256(identity.encode()).hexdigest()[:20],
            'name': name.strip()[:120], 'lat': lat, 'lng': lng,
            'candidate_source': 'tomtom_live', 'category': category,
            'destination_tier': 'landmark_type' if prefer_landmarks else 'local_fallback',
            'parking_verified': False}))
    if not candidates and prefer_landmarks:
        local, meta = discover(ctx, anchors, prefer_landmarks=False)
        return local, {**meta, 'preferred_status': 'no_supported_landmarks',
                       'destination_tier': 'local_fallback', 'landmark_probe_count': len(probes)}
    buckets = {}
    for sector, distance, area in sorted(candidates, key=lambda r: (r[1], r[2]['id'])):
        buckets.setdefault(sector, []).append(area)
    selected = []
    for index in range(24):
        for sector in sorted(buckets):
            if index < len(buckets[sector]):
                selected.append(buckets[sector][index])
            if len(selected) == 24:
                break
        if len(selected) == 24:
            break
    return selected, {'status': 'ok' if selected else 'no_supported_candidates',
                      'source': 'TomTom Category Search' if prefer_landmarks else 'TomTom Nearby Search', 'radius_m': radius,
                      'destination_tier': 'landmark_type' if prefer_landmarks else 'local_fallback',
                      'provider_records': len(results), 'eligible_records': len(candidates),
                      'selected': len(selected), 'cache_seconds': 300,
                      'probe_count': len(probes),
                      'successful_probes': sum(b is not None for b in batches),
                      'partial': any(b is None for b in batches),
                      'not_measured_demand': True}
