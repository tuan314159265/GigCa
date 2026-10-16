"""Experimental POI/time reranker. Never modifies ML probabilities or money predictions."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from functools import lru_cache
import json
import hashlib
import math
from pathlib import Path

from engine.src.geo import haversine_m
from engine.src.scorers._common import reposition_for


@lru_cache(maxsize=1)
def policy():
    return json.loads((Path(__file__).resolve().parents[1]/'config/poi_time_policy.json').read_text(encoding='utf8'))


def opportunity(groups, arrival):
    cfg = policy(); components = []; total = 0.0
    available = bool(groups) and all(g.get('fetch_status',g.get('status')) != 'unavailable' for g in groups)
    if not available:
        return {'available':False, 'score':None, 'components':[], 'groups':groups}
    for group in groups:
        rule = cfg['groups'].get(group['category'])
        if not rule or not group['pois']:continue
        activity = next((v for a,b,v in rule['windows'] if a<=arrival.hour+arrival.minute/60<b),rule['otherwise'])
        if arrival.weekday()>=5:activity*=rule['weekend_factor']
        # At most six observed records per type; distance attenuation and saturation
        # keep dense/truncated provider samples from growing without bound.
        places=sorted(group['pois'],key=lambda p:p['distance_m'])[:6]
        exposure=sum(math.exp(-p['distance_m']/350) for p in places)
        value=rule['weight']*activity*math.log1p(exposure)
        total+=value
        components.append({'category':group['category'],'label':group['label'], 'observed_count':len(group['pois']),
                           'names':[p['name'] for p in places[:2]], 'contribution':round(value,3)})
    return {'available':True,'score':round(100*(1-math.exp(-total/8)),2),
            'components':sorted(components,key=lambda c:-c['contribution']), 'groups':groups,
            'arrival_local':arrival.isoformat(), 'policy_version':cfg['version'],
            'not_measured_demand':True,
            'reference_commute_window':arrival.weekday()<5 and any(a<=arrival.hour+arrival.minute/60<b for a,b in cfg['reference_commute_windows'])}


def build_contexts(areas, ctx, now, anchors):
    from api.llm_explanations import poi_context
    origin=areas[0]
    initial=poi_context(origin['lat'],origin['lng'],selection_limit=100)
    # Only inspect the existing ML shortlist. Do not add destinations or remove
    # candidates from the main engine; POIs are a secondary preference only.
    eligible=areas[:policy()['max_areas']]
    def collect(area):
        rep=reposition_for(haversine_m(ctx.current_lat,ctx.current_lng,area['lat'],area['lng']),
            {'at_area_radius_m':0} if area.get('candidate_source')=='tomtom_live' else None)
        groups=initial if area['id']=='model_current' else poi_context(area['lat'],area['lng'],selection_limit=100)
        return area['id'],opportunity(groups,now+timedelta(minutes=rep.minutes))
    with ThreadPoolExecutor(max_workers=4) as pool:contexts=dict(pool.map(collect,eligible))
    # Failure to observe a region is not evidence that it has no opportunity.
    complete=all(v['available'] for v in contexts.values())
    return eligible,contexts,complete


def rank_values(yield_vnd, position_score, rep, context, origin_context, horizon):
    remaining=max(0,horizon-rep.minutes)
    horizon_net=yield_vnd*remaining/60-rep.cost_vnd
    effective=horizon_net*60/horizon
    delta=context['score']-origin_context['score']
    return {'position':max(0,min(100,position_score+policy()['position_bonus_points']*delta/100)),
            'income':yield_vnd+yield_vnd*policy()['income_context_fraction']*delta/100,
            'horizon_net_vnd':round(horizon_net), 'effective_yield_vnd_per_hour':round(effective),
            'poi_delta_points':round(delta,2)}
