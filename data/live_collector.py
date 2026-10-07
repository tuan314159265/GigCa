"""Origin-scoped live snapshot. Never falls back to fixtures or synthesizes fares."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.parse import urlencode
import hashlib
import json
import math
import time
import threading
import uuid
from api.provider_proxy import tomtom_url, TOMTOM_POI, TOMTOM_ROUTE, TOMTOM_FLOW

_cache = {}
_lock = threading.Lock()

def fetch_json(url):
    try:
        with urlopen(Request(url,headers={'User-Agent':'GigCa/1.0'}),timeout=6) as response:
            result=json.load(response)
        if not isinstance(result,dict): raise ValueError()
        return result
    except Exception:
        # Do not expose provider URLs containing server keys.
        raise RuntimeError('Không lấy được dữ liệu từ nhà cung cấp.') from None

def cached(key,ttl,loader):
    with _lock:
        entry=_cache.get(key)
        if entry and entry[0]>time.monotonic(): return entry[1]
    result=loader()
    result={**result, '_fetched_at':datetime.now(timezone.utc).isoformat()}
    with _lock:
        if len(_cache)>512: _cache.clear()
        _cache[key]=(time.monotonic()+ttl,result)
    return result

def finite(value,low=0,high=float('inf')):
    return isinstance(value,(float,int)) and not isinstance(value,bool) and math.isfinite(value) and low<=value<=high

def collect_for_origin(lat,lng,horizon_min,radius_km):
    now=datetime.now(timezone.utc)
    statuses=[];limitations=[]
    point={'latitude':lat,'longitude':lng}
    # A single point sample is legitimate; it does not claim city-wide coverage.
    area={'area_id':'origin_'+str(uuid.uuid4()),'spatial_scope':'point_sample','representative_point':point,
          'weather':{'hourly':[]},'poi_counts_by_category':{},'waiting_location_candidates':[],'routing_samples':[]}
    snapshot={'schema_version':'0.1','snapshot_id':str(uuid.uuid4()),'generated_at':now.isoformat(),
              'source_dataset_ids':[],'data_status':statuses,'objective_readiness':[], 'areas':[area],
              'traffic':[],'limitations':limitations}
    def status(dataset,state,reason,source=None):
        row={'dataset':dataset,'status':state,'reason':reason}
        if source: row['source_dataset_id']=source;snapshot['source_dataset_ids'].append(source)
        statuses.append(row)
    def weather():
        return cached(('weather',lat,lng),600,lambda:fetch_json('https://api.open-meteo.com/v1/forecast?'+urlencode({
            'latitude':lat,'longitude':lng,'hourly':'precipitation,precipitation_probability','forecast_days':2,'timezone':'UTC'})))
    def pois():
        if radius_km==0:return {'results':[]}
        return cached(('poi',lat,lng,radius_km),300,lambda:fetch_json(tomtom_url(TOMTOM_POI+'/cafe.json',
            {'lat':lat,'lon':lng,'radius':int(min(radius_km*1000,5000)),'limit':3,'language':'vi-VN'})))
    def flow():
        return cached(('flow',lat,lng),45,lambda:fetch_json(tomtom_url(TOMTOM_FLOW,{'point':f'{lat},{lng}','unit':'KMPH'})))
    with ThreadPoolExecutor(max_workers=3) as pool:
        tasks={key:pool.submit(loader) for key,loader in [('weather',weather),('poi',pois),('traffic',flow)]}
        responses={}
        for key,future in tasks.items():
            try:responses[key]=future.result()
            except Exception:status(key,'missing',f'Không lấy được {key} tại tọa độ hiện tại.')
    raw=responses.get('weather')
    if raw:
        hourly=raw.get('hourly',{});times=hourly.get('time',[])
        mm=hourly.get('precipitation',[]);probs=hourly.get('precipitation_probability',[])
        for i,t in enumerate(times):
            try:valid=datetime.fromisoformat(t).replace(tzinfo=timezone.utc)-timedelta(hours=1)
            except (ValueError,TypeError):continue
            if valid+timedelta(hours=1)<=now or valid>=now+timedelta(minutes=horizon_min):continue
            m=mm[i] if i<len(mm) else None;p=probs[i] if i<len(probs) else None
            area['weather']['hourly'].append({'valid_time':valid.isoformat(),
                'precipitation_mm':m if finite(m) else None,'precipitation_probability_pct':p if finite(p,0,100) else None})
        if finite(raw.get('latitude'),-90,90) and finite(raw.get('longitude'),-180,180):
            area['weather']['provider_grid_location']={'latitude':raw['latitude'],'longitude':raw['longitude']}
        usable=any(r['precipitation_mm'] is not None or r['precipitation_probability_pct'] is not None for r in area['weather']['hourly'])
        status('weather','partial' if usable else 'missing','Dự báo tại lưới gần GPS; giá trị giờ trước của provider được gắn vào đầu cửa sổ giờ Engine.','open_meteo_live')
    raw=responses.get('poi')
    if raw is not None:
        for item in raw.get('results',[]):
            pos=item.get('position',{});pid=item.get('id')
            if not pid or not finite(pos.get('lat'),-90,90) or not finite(pos.get('lon'),-180,180):continue
            area['waiting_location_candidates'].append({'candidate_id':str(pid),'name':item.get('poi',{}).get('name') or str(pid),
                'source_provider':'TomTom','source_id':str(pid),'poi_type':'cafe','role':'waiting_location_candidate',
                'candidate_status':'unverified_candidate','permission_to_wait':'unknown',
                'latitude':pos['lat'],'longitude':pos['lon'],'point_method':'provider_position',
                'verification_needed':['parking','opening_hours','motorcycle_access']})
        status('poi','partial','Tối đa 3 quán cafe trong phạm vi tìm kiếm; chưa xác minh quyền đỗ xe.','tomtom_search_live')
    def route(poi):
        target=f"{poi['latitude']},{poi['longitude']}"
        return cached(('route',lat,lng,target),45,lambda:fetch_json(tomtom_url(f'{TOMTOM_ROUTE}/{lat},{lng}:{target}/json',
            {'travelMode':'motorcycle','traffic':'true','routeType':'fastest'})))
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures=[(poi,pool.submit(route,poi)) for poi in area['waiting_location_candidates']]
        for poi,future in futures:
            try:
                summary=future.result()['routes'][0]['summary']
                distance=summary.get('lengthInMeters');duration=summary.get('travelTimeInSeconds')
                if not finite(distance) or not finite(duration):continue
                if distance>radius_km*1000:continue
                area['routing_samples'].append({'destination_id':poi['candidate_id'],'profile':'motorcycle',
                    'route_distance_m':distance,'route_duration_s':duration})
            except Exception:continue
    status('routing','partial' if area['routing_samples'] else 'missing','Tuyến xe máy từ GPS tới ứng viên; tuyến lỗi hoặc vượt giới hạn không được dùng.','tomtom_route_live')
    raw=responses.get('traffic')
    if raw:
        flow=raw.get('flowSegmentData',{});current=flow.get('currentSpeed');free=flow.get('freeFlowSpeed')
        coords=flow.get('coordinates',{})
        if finite(current) and finite(free,0.001):
            edge='tomtom_'+hashlib.sha256(json.dumps(coords,sort_keys=True).encode()).hexdigest()[:16]
            snapshot['traffic']=[{'edge_id':edge,'current_speed_kmh':current,'free_flow_speed_kmh':free,'observed_at':raw.get('_fetched_at',now.isoformat())}]
        status('traffic','partial' if snapshot['traffic'] else 'missing','Chỉ segment provider gần GPS, không đại diện mọi đường xung quanh.','tomtom_flow_live')
    status('trip_value','missing','Chưa có nguồn giá trị chuyến thật.')
    status('booking_and_destinations','missing','Chưa có booking và phân bố điểm trả thật.')
    for objective in ('max_trip_value','maintain_position','rest_spot','safety_comfort'):
        enough=(objective=='rest_spot' and bool(area['routing_samples'])) or (objective=='safety_comfort' and (bool(snapshot['traffic']) or bool(area['weather']['hourly'])))
        blocking = [] if enough else {
            'max_trip_value':['trip_value'], 'maintain_position':['booking_and_destinations'],
            'rest_spot':['routing'], 'safety_comfort':['weather','traffic']
        }[objective]
        snapshot['objective_readiness'].append({'objective':objective,'status':'partial' if enough else 'insufficient_data',
            'blocking_datasets':blocking,
            'reason':'Đánh giá từ nguồn tại GPS, có giới hạn độ phủ.' if enough else 'Thiếu dữ liệu cần thiết.'})
    limitations.extend(['Không có dữ liệu cuốc/booking thật.','POI chưa xác minh quyền đỗ; traffic chỉ phủ segment được trả về.'])
    return snapshot
