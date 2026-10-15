"""Explicit, reproducible expanded geography without changing legacy ZONES."""
import copy
import json
import math
from pathlib import Path
from .personas import validate_personas
from .generator import distance_km

def load_zone_catalog(path):
    doc=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    zones=doc.get('zones')
    if doc.get('scope')!='hcmc_pre_2025_no_di_an' or not isinstance(zones,dict) or len(zones)<6:
        raise ValueError('Need a pre-merger HCMC catalog with at least 6 anchors.')
    for key,row in zones.items():
        if not isinstance(key,str) or not isinstance(row,dict) or not isinstance(row.get('name'),str):
            raise ValueError('Invalid zone metadata.')
        for field,low,high in (('lat',-90,90),('lng',-180,180)):
            value=row.get(field)
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:
                raise ValueError('Invalid zone coordinate.')
    return zones

def remap_personas(document,zones):
    if all(row.get('home_zone') in zones for row in document.get('personas', [])):
        validate_personas(document,zones)
        return copy.deepcopy(document)
    original=validate_personas(document)
    result=copy.deepcopy(document);ids=list(zones)
    for i,row in enumerate(result['personas']):
        home=ids[i*len(ids)//len(original)]
        row['home_zone']=home
        point=(zones[home]['lat'],zones[home]['lng'])
        row['preferred_zones']=sorted(ids,key=lambda z:distance_km(point,(zones[z]['lat'],zones[z]['lng'])))[:6]
    result.setdefault('provenance',{})['geographic_remap']={
        'method':'balanced_home_spread_nearest_six_preferences',
        'original_assignments':[{k:r[k] for k in ('driver_id','home_zone','preferred_zones')} for r in original],
        'note':'Geographic assignment is a simulation design, not an LLM observation.'}
    validate_personas(result,zones)
    return result
