"""Generate expanded logs only after balanced spatial planning; never fit a model."""
import argparse
import csv
import hashlib
import json
import random
from collections import Counter
from dataclasses import fields
from datetime import date,datetime,timedelta
from pathlib import Path
from .generator import generate,calendar_splits,stable_seed,write_dataset
from .geography import load_zone_catalog
from .personas import validate_personas
from .spatial import contains
from .train_base import driver_split

GROUPS=('train','validation','calibration','test')

def balanced_plan(document,zones,end_date,days,seed):
    slots=document['provenance']['design']['slots']
    people={p['driver_id']:p for p in document['personas']}
    split=driver_split(sorted(people),slots,seed)
    dates=calendar_splits(end_date,days)
    plan={};stats={}
    for group in GROUPS:
        drivers=split['validation'] if group=='calibration' else split[group]
        calendar=dates['train'] if group=='validation' else dates[group]
        active=[]
        for did in drivers:
            for day in calendar:
                if random.Random(stable_seed(seed,did,day,'expanded_workday')).random() < people[did]['work_probability']:
                    active.append((did,day))
        if len(active)<2*len(zones):
            raise ValueError(f'{group}: only {len(active)} active shifts, need {2*len(zones)} for two planned visits/zone.')
        rng=random.Random(stable_seed(seed,group,'balanced_spatial_design'))
        rng.shuffle(active);ids=list(zones);rng.shuffle(ids)
        for i,key in enumerate(active):plan[key]=ids[i%len(ids)]
        stats[group]={'shifts':len(active),'minimum_shifts_per_zone':len(active)//len(ids)}
    # Keep complete histories, including dates not selected for a driver's ML split.
    extra=[]
    calendar=sorted(set(day for values in dates.values() for day in values))
    for did in sorted(people):
        for day in calendar:
            key=(did,day)
            if key not in plan and random.Random(stable_seed(seed,did,day,'expanded_workday')).random() < people[did]['work_probability']:
                extra.append(key)
    rng=random.Random(stable_seed(seed,'additional_history'));rng.shuffle(extra)
    ids=list(zones);rng.shuffle(ids)
    for i,key in enumerate(extra):plan[key]=ids[i%len(ids)]
    return plan,split,dates,stats

def audit(dataset,split,dates,zones,geometry):
    from engine.src.types import TripRecord,WaitSpell
    from engine.src.ml.cycle_model import build_cycles
    report={k:{z:{'waits':0,'trips':0,'matched_cycles':0,'drivers':set()} for z in zones} for k in GROUPS}
    total=Counter();missing=[];matching={};outside=0;wrong_matches=0
    def typed(cls,row):return cls(**{f.name:row[f.name] for f in fields(cls) if f.name in row})
    for log in dataset['drivers']:
        did=log['persona']['driver_id'];events=log['events']
        waits={w['spell_id']:w for w in log['wait_spells']}
        wait_events={e['spell_id']:e for e in events if e['type']=='wait'}
        paid={e['trip_id']:e for e in events if e['type']=='paid_trip'}
        total.update(trips=len(log['trip_log']),waits=len(waits))
        for event in events:
            for point in (event['start_point'],event['end_point']):
                if not contains(point,geometry):outside+=1
        m={};profile=log['driver_profile']
        build_cycles([typed(TripRecord,t) for t in log['trip_log']], [typed(WaitSpell,w) for w in waits.values()],
                     profile['fuel_l_per_100km']*profile['fuel_price_vnd_per_l']/100, matching_report=m)
        matching[did]=m['counts'];inferred={r['trip_id']:r for r in m['rows'] if r['status']=='inferred'}
        for tid,row in inferred.items():
            if paid[tid]['spell_id'] != row['spell_id']:wrong_matches+=1
        total.update(matched_cycles=len(inferred))
        for group in GROUPS:
            drivers=split['validation'] if group=='calibration' else split[group]
            if did not in drivers:continue
            calendar=set(dates['train'] if group=='validation' else dates[group])
            for w in waits.values():
                if datetime.fromisoformat(w['start']).date().isoformat() not in calendar:continue
                if datetime.fromisoformat(w['end']).date().isoformat() not in calendar:continue
                row=report[group][wait_events[w['spell_id']]['zone_id']]
                row['waits']+=1;row['drivers'].add(did)
            for tid,event in paid.items():
                if datetime.fromisoformat(event['start']).date().isoformat() in calendar:
                    report[group][event['zone_id']]['trips']+=1
            for tid,pair in inferred.items():
                w=waits[pair['spell_id']]
                if datetime.fromisoformat(w['start']).date().isoformat() in calendar:
                    report[group][wait_events[w['spell_id']]['zone_id']]['matched_cycles']+=1
    for group in GROUPS:
        for z,row in report[group].items():
            row['driver_count']=len(row.pop('drivers'))
            if row['waits']<5 or row['matched_cycles']<3: missing.append({'group':group,'zone':z,**row})
    return {'all_zones_pass':not missing and outside==0 and wrong_matches==0,
            'minimum_required_per_zone_per_split':{'waits':5,'matched_cycles':3},
            'zones':report,'below_minimum':missing,'outside_boundary_event_points':outside,
            'wrong_inferred_matches_against_simulator':wrong_matches,'matching':matching,'totals':dict(total),
            'note':'Coverage thresholds are design checks, not statistical sufficiency or real-world accuracy.'}

def fingerprints(folder):
    return {str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.rglob('*')) if p.is_file()}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--personas',type=Path,required=True);p.add_argument('--zones',type=Path,required=True)
    p.add_argument('--boundary',type=Path,required=True);p.add_argument('--days',type=int,default=120)
    p.add_argument('--end-date',type=date.fromisoformat,default=date(2026,10,14));p.add_argument('--seed',type=int,default=7)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if args.output.exists():p.error('Output exists; choose a new output. No records overwritten.')
    document=json.loads(args.personas.read_text(encoding='utf8'));zones=load_zone_catalog(args.zones)
    people=validate_personas(document,zones)
    if len(people)!=32:p.error('This expanded design requires exactly 32 personas.')
    geometry=json.loads(args.boundary.read_text(encoding='utf8'))['geometry']
    catalog=json.loads(args.zones.read_text(encoding='utf8'))
    if hashlib.sha256(args.boundary.read_bytes()).hexdigest()!=catalog['boundary']['sha256']:
        p.error('Boundary hash differs from anchor catalog.')
    if not all(contains((a['lat'],a['lng']),geometry) for a in zones.values()):p.error('Anchor outside study area.')
    plan,split,dates,stats=balanced_plan(document,zones,args.end_date,args.days,args.seed)
    print(json.dumps({'planned_groups':stats,'drivers':32,'zones':len(zones),'days':args.days}),flush=True)
    dataset=generate(document,end_date=args.end_date,days=args.days,seed=args.seed,world='contextual',
        zone_catalog=zones,shift_plan=plan,point_allowed=lambda pt:contains(pt,geometry))
    coverage=audit(dataset,split,dates,zones,geometry)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if not coverage['all_zones_pass']:
        failure=args.output.parent/(args.output.name+'-coverage-failed.json')
        failure.write_text(json.dumps(coverage,ensure_ascii=False,indent=2),encoding='utf8')
        audit_folder=args.output.parent/(args.output.name+'-audit-incomplete')
        if not audit_folder.exists():
            write_dataset(dataset,audit_folder)
            (audit_folder/'coverage.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2),encoding='utf8')
        raise ValueError(f'Coverage/matching audit failed; no dataset exported. Inspect {failure}')
    manifest=dataset['manifest'];manifest['geographic_design']={'method':'balanced_active_shifts_per_split',
        'seed':args.seed,'plan_stats':stats,'driver_split':split,
        'zone_catalog_sha256':hashlib.sha256(args.zones.read_bytes()).hexdigest(),
        'boundary_sha256':hashlib.sha256(args.boundary.read_bytes()).hexdigest(),
        'destination_decay_km':5,'maximum_destination_straight_km':20,
        'complete_history_active_shifts':len(plan),
        'additional_history_shifts_not_used_by_the_four_ml_slices':len(plan)-sum(x['shifts'] for x in stats.values()),
        'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'note':'Artificial balanced exposure, not natural driver geographic preferences or measured OD.'}
    manifest['coverage_summary']={k:v for k,v in coverage.items() if k not in ('zones','matching')}
    write_dataset(dataset,args.output)
    (args.output/'coverage.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2),encoding='utf8')
    (args.output/'personas.json').write_text(json.dumps(document,ensure_ascii=False,indent=2),encoding='utf8')
    (args.output/'anchors.json').write_bytes(args.zones.read_bytes())
    (args.output/'shift-plan.json').write_text(json.dumps([{'driver_id':did,'date':day,'zone_id':z} for (did,day),z in sorted(plan.items())],indent=2),encoding='utf8')
    with (args.output/'coverage.csv').open('w',encoding='utf8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['split','zone_id','name','waits','trips','matched_cycles','driver_count']);writer.writeheader()
        for group in GROUPS:
            for z,row in coverage['zones'][group].items():writer.writerow({'split':group,'zone_id':z,'name':zones[z]['name'],**row})
    # Read back every CSV and JSON log; verify counts and matching hashes.
    for log in dataset['drivers']:
        folder=args.output/log['persona']['driver_id'];stored=json.loads((folder/'research_log.json').read_text(encoding='utf8'))
        if stored!=log:raise ValueError('JSON read-back mismatch.')
        for name,key in (('trips.csv','trip_log'),('waits.csv','wait_spells')):
            with (folder/name).open(encoding='utf8',newline='') as stream:
                if sum(1 for _ in csv.DictReader(stream))!=len(log[key]):raise ValueError('CSV read-back count mismatch.')
    index=fingerprints(args.output)
    (args.output/'checksums.json').write_text(json.dumps(index,indent=2),encoding='utf8')
    (args.output/'READY.json').write_text(json.dumps({'status':'validated_synthetic_dataset','files_hashed':len(index),'totals':coverage['totals'],
        'zones':len(zones),'drivers':32,'all_four_splits_cover_every_zone':True,'trained':False},indent=2),encoding='utf8')
    print(json.dumps({'output':str(args.output),'ready':True,**coverage['totals']},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
