"""Bounded nearby flow samples; not a route or exhaustive road coverage."""
import hashlib
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from api.errors import ApiError
from api.provider_proxy import TOMTOM_FLOW, cached, tomtom_url
from api.llm_explanations import request_json
from engine.src.geo import haversine_m


def nearby_traffic(lat, lng):
    try:lat,lng=float(lat),float(lng)
    except (ValueError,TypeError):raise ApiError(422,'invalid_coordinates','Tọa độ không hợp lệ.')
    if not math.isfinite(lat) or not math.isfinite(lng) or not -90<=lat<=90 or not -180<=lng<=180:
        raise ApiError(422,'invalid_coordinates','Tọa độ không hợp lệ.')
    def load():
        dy=200/111000;dx=dy/max(.2,math.cos(math.radians(lat)))
        points=[(lat,lng),(lat+dy,lng),(lat-dy,lng),(lat,lng+dx),(lat,lng-dx)]
        def sample(point):
            try:
                flow=request_json(tomtom_url(TOMTOM_FLOW,{'point':f'{point[0]},{point[1]}','unit':'KMPH','openLr':'true'})).get('flowSegmentData',{})
                coords=flow.get('coordinates',{}).get('coordinate',[])
                coords=[p for p in coords if all(isinstance(p.get(k),(int,float)) and math.isfinite(p[k]) for k in ('latitude','longitude'))]
                if not coords:return None
                snapped=min(coords,key=lambda p:haversine_m(lat,lng,p['latitude'],p['longitude']))
                if haversine_m(lat,lng,snapped['latitude'],snapped['longitude'])>500:return None
                identity=flow.get('openlr') or repr(sorted((round(p['latitude'],5),round(p['longitude'],5)) for p in coords))
                name='Đoạn đường chưa có tên'
                try:
                    address=cached('nearby_road_name:'+str(identity),86400,lambda:request_json(tomtom_url(
                        f"https://api.tomtom.com/search/2/reverseGeocode/{snapped['latitude']},{snapped['longitude']}.json",
                        {'radius':30,'language':'vi-VN','returnSpeedLimit':'false'})))
                    name=next((r['address']['streetName'] for r in address.get('addresses',[]) if r.get('address',{}).get('streetName')),name)
                except Exception:pass
                speed=flow.get('currentSpeed');free=flow.get('freeFlowSpeed')
                valid=lambda x:isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) and x>=0
                ratio=speed/free if valid(speed) and valid(free) and free>0 else None
                status='unknown' if ratio is None else 'smooth' if ratio>=.8 else 'congested' if ratio<.5 else 'moderate'
                return {'id':'nearby:'+hashlib.sha256(str(identity).encode()).hexdigest()[:16], 'name':name,
                        'speed':speed if valid(speed) else None,'delay':None,'status':status}
            except Exception:return None
        with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(sample,points))
        roads={r['id']:r for r in rows if r}
        return {'roads':list(roads.values()),'source':'TomTom Flow + Reverse Geocoding',
                'fetched_at':datetime.now(timezone.utc).isoformat(),'scope':'nearby_point_samples',
                'radius_m':500,'partial':len(roads)<len(points)}
    return cached(f'nearby_traffic:{lat:.5f}:{lng:.5f}',30,load)
