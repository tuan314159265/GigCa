"""Read-only synthetic matching audit using event links as evaluation ground truth."""
import bisect
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np


def distance(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371000*2*math.asin(min(1, math.sqrt(h)))


def audit(folder):
    logs = [json.loads(p.read_text(encoding='utf8')) for p in sorted(Path(folder).glob('D*/research_log.json'))]
    gaps, meters, truth, data = [], [], {}, []
    for log in logs:
        waits = sorted((w for w in log['wait_spells'] if w['ended_by'] == 'trip'), key=lambda w:w['end'])
        times = [datetime.fromisoformat(w['end']).timestamp() for w in waits]
        by_id = {w['spell_id']:w for w in waits}
        for event in log['events']:
            if event['type'] == 'paid_trip':
                truth[event['trip_id']] = event['spell_id']
        trips = sorted(log['trip_log'], key=lambda t:(t['started_at'],t['trip_id']))
        for t in trips:
            w = by_id[truth[t['trip_id']]]
            gaps.append((datetime.fromisoformat(t['started_at'])-datetime.fromisoformat(w['end'])).total_seconds()/60)
            meters.append(distance((w['lat'],w['lng']),(t['pickup_lat'],t['pickup_lng'])))
        data.append((waits,times,trips))
    results=[]
    for minutes, radius in [(2, None)] + [(m,r) for m in (3,5,7,8,10,15) for r in (300,500,800,1000,1200)]:
        correct=wrong=matched=ambiguous=0
        for waits,times,trips in data:
            used=set()
            for t in trips:
                stamp=datetime.fromisoformat(t['started_at']).timestamp()
                # Legacy permits reversed times; proposed matcher requires acceptance <= pickup.
                left=bisect.bisect_left(times,stamp-minutes*60)
                right=bisect.bisect_right(times,stamp+(120 if radius is None else 0))
                candidates=[]
                for i in range(left,right):
                    w=waits[i]
                    if w['spell_id'] in used: continue
                    spatial=(abs(w['lat']-t['pickup_lat'])<=.003 and abs(w['lng']-t['pickup_lng'])<=.003) if radius is None else distance((w['lat'],w['lng']),(t['pickup_lat'],t['pickup_lng']))<=radius
                    if spatial: candidates.append((abs(stamp-times[i]),w['spell_id']))
                if len(candidates)>1: ambiguous+=1
                if candidates:
                    _,sid=min(candidates)
                    used.add(sid); matched+=1
                    if truth[t['trip_id']]==sid: correct+=1
                    else: wrong+=1
        results.append({'max_minutes':minutes,'radius_m':radius,'matched':matched,'correct':correct,'wrong':wrong,'ambiguous':ambiguous,'recall_pct':round(100*correct/len(gaps),2)})
    return {'trips':len(gaps),'quantiles':{str(q):{'pickup_gap_min':round(float(np.percentile(gaps,q)),3),'straight_distance_m':round(float(np.percentile(meters,q)),1)} for q in (50,75,90,95,99,100)},'thresholds':results,
            'note':'Synthetic event IDs used only to score correctness, never as matcher input. Legacy approximation uses +/-120s and per-axis .003deg; proposals use causal time and haversine distance. Synthetic results do not establish real-data precision.'}


if __name__ == '__main__':
    import sys
    print(json.dumps(audit(sys.argv[1]),ensure_ascii=False,indent=2))
