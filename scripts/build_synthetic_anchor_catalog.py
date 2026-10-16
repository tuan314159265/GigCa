"""Build a pre-merger HCMC anchor catalog from a versioned polygon and TomTom search.
No driver logs are generated and no model is trained. Public boundary is approximate,
not an official cadastral/legal boundary; geocoded POIs are not verified waiting places.
"""
import argparse
import hashlib
import json
import math
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from api.provider_proxy import tomtom_url

GEOMETRY_URL='https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/VNM/ADM1/geoBoundaries-VNM-ADM1.geojson'
QUERIES = [
 'Chợ Bến Thành','Chợ Tân Định','Bến xe Miền Đông cũ','Landmark 81',
 'Đại học Bách Khoa 268 Lý Thường Kiệt','Chợ Bà Chiểu','Chợ Bà Hoa','Chợ Tân Bình',
 'Sân bay Tân Sơn Nhất','Công viên Gia Định','Chợ Hạnh Thông Tây','Chợ Gò Vấp',
 'Công viên Lê Thị Riêng','Công viên Đầm Sen','Bến xe Miền Tây','Chợ Bình Tây',
 'Chợ An Đông','Đại học Y Dược','Cầu Chữ Y','Chợ Xóm Củi',
 'Crescent Mall','Khu chế xuất Tân Thuận','Đại học RMIT Nam Sài Gòn','Chợ Phước Kiển',
 'Thị trấn Nhà Bè','Khu công nghiệp Hiệp Phước','Thị trấn Tân Túc','Chợ Bình Chánh',
 'Khu công nghiệp Lê Minh Xuân','Khu công nghiệp Vĩnh Lộc','Bến xe An Sương','Chợ Thạnh Xuân',
 'Chợ Hóc Môn','Ngã ba Giồng','Thị trấn Củ Chi','Khu công nghiệp Tây Bắc Củ Chi',
 'Chợ Phú Hòa Đông','Chợ An Nhơn Tây','Địa đạo Bến Dược',
 'Chợ Thủ Đức','Vincom Thủ Đức','Chợ Linh Xuân','Đại học Nông Lâm Thành phố Hồ Chí Minh',
 'Khu Công nghệ cao Thành phố Hồ Chí Minh','Vincom Mega Mall Thảo Điền',
 'Chợ Cát Lái','Chợ Long Trường','Chợ Long Phước','Chợ Bình Khánh Cần Giờ',
 'Chợ An Thới Đông','Chợ Cần Thạnh','Chợ Hàng Dương Cần Giờ',
 'Chợ Vàm Sát','Chợ Hòa Hiệp Cần Giờ','Agribank Bình Khánh Cần Giờ',
]

def fetch(url):
    with urlopen(Request(url,headers={'User-Agent':'GigCa-Research/1.0'}),timeout=20) as r:
        return json.load(r)

def norm(s):
    return ''.join(c for c in unicodedata.normalize('NFD',s.lower()).replace('đ','d') if unicodedata.category(c)!='Mn')

def inside_ring(x,y,ring):
    inside=False
    for a,b in zip(ring,ring[1:]+ring[:1]):
        if (a[1]>y)!=(b[1]>y) and x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]: inside=not inside
    return inside

def inside(lng,lat,geometry):
    polygons=geometry['coordinates'] if geometry['type']=='MultiPolygon' else [geometry['coordinates']]
    return any(inside_ring(lng,lat,p[0]) and not any(inside_ring(lng,lat,h) for h in p[1:]) for p in polygons)

def prepare_boundary(raw):
    features=[f for f in raw['features'] if norm(f['properties'].get('shapeName',f['properties'].get('NAME_1',''))) in ('ho chi minh','ho chi minh city','tp. ho chi minh','hochiminh')]
    if len(features)!=1: raise ValueError('Boundary must have exactly one pre-merger Ho Chi Minh feature.')
    feature=features[0];geom=feature['geometry']
    polygons=geom['coordinates'] if geom['type']=='MultiPolygon' else [geom['coordinates']]
    points=[point for p in polygons for ring in p for point in ring]
    extrema={label:{'lat':p[1],'lng':p[0]} for label,p in (
        ('north',max(points,key=lambda p:p[1])),('south',min(points,key=lambda p:p[1])),
        ('east',max(points,key=lambda p:p[0])),('west',min(points,key=lambda p:p[0])))}
    # Detect wrong province / newly merged boundary instead of silently using it.
    if not (11<extrema['north']['lat']<11.3 and 10.2<extrema['south']['lat']<10.6 and extrema['east']['lng']<107.1):
        raise ValueError('Boundary does not match expected pre-merger mainland HCMC extent.')
    return feature,extrema

def expected_region(query,point):
    q=norm(query);lat=point['lat'];lng=point['lon']
    if any(t in q for t in ('can gio','can thanh','an thoi dong','vam sat')): return lat < 10.7 and lng > 106.7
    if q=='cho binh chanh' or 'tan tuc' in q: return lat < 10.79 and lng < 106.65
    if any(t in q for t in ('cu chi','an nhon tay','ben duoc','phu hoa dong')): return lat > 10.92 and lng < 106.65
    if 'hoc mon' in q or 'nga ba giong' in q: return lat > 10.82 and lng < 106.65
    if 'nha be' in q or 'hiep phuoc' in q: return lat < 10.76 and lng > 106.64
    return True

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--boundary',type=Path,help='Local historical polygon, e.g. GADM 4.1; obey its license.')
    args=parser.parse_args()
    if args.output.exists() and not args.resume: parser.error('Output exists; use a new path or --resume.')
    args.output.mkdir(parents=True,exist_ok=args.resume)
    boundary_path=args.boundary or args.output/'boundary.geojson'
    if boundary_path.exists():
        feature=json.loads(boundary_path.read_text(encoding='utf8'));_,extrema=prepare_boundary({'features':[feature]})
    else:
        feature,extrema=prepare_boundary(fetch(GEOMETRY_URL))
        boundary_path.write_text(json.dumps(feature,ensure_ascii=False),encoding='utf8')
    checkpoint=args.output/'geocoding-pois.json'
    results=json.loads(checkpoint.read_text(encoding='utf8')) if checkpoint.exists() else {}
    zones={};rejected=[]
    for i,name in enumerate(QUERIES,1):
        if name not in results:
            try:
                local = {'lat':10.45,'lon':106.9} if any(t in norm(name) for t in ('can gio','can thanh','an thoi dong','vam sat')) else {'lat':10.7769,'lon':106.7009}
                url=tomtom_url('https://api.tomtom.com/search/2/poiSearch/'+quote(name,safe='')+'.json',
                               {'countrySet':'VN','limit':10,'language':'vi-VN',**local,'radius':100000})
                results[name]=fetch(url).get('results',[])
                checkpoint.write_text(json.dumps(results,ensure_ascii=False),encoding='utf8')
            except Exception:
                rejected.append({'query':name,'reason':'provider_unavailable'});continue
        candidates=[r for r in results[name] if r.get('poi',{}).get('name') and isinstance(r.get('position',{}).get('lat'),(int,float))
                    and isinstance(r.get('position',{}).get('lon'),(int,float))
                    and inside(r['position']['lon'],r['position']['lat'],feature['geometry'])
                    and expected_region(name,r['position'])]
        if not candidates:
            rejected.append({'query':name,'reason':'no_result_inside_pre_merger_boundary'});continue
        tokens=set(re.findall(r'\w+',norm(name).replace('can gio','')))-{'thi','tran','thanh','pho','ho','chi','minh','cu'}
        def relevance(r):
            words=set(re.findall(r'\w+',norm(r.get('poi',{}).get('name','')+' '+r.get('address',{}).get('freeformAddress',''))))
            return len(tokens & words)/max(1,len(tokens))
        candidates.sort(key=relevance,reverse=True)
        if relevance(candidates[0]) < .85:
            rejected.append({'query':name,'reason':'weak_name_match'});continue
        row=candidates[0];point=row['position']
        if any(math.hypot((a['lat']-point['lat'])*111320,(a['lng']-point['lon'])*109300)<250 for a in zones.values()):
            rejected.append({'query':name,'reason':'duplicate_nearby_anchor'});continue
        zones[f'HCM{i:03}']={'name':row['poi']['name'],'query':name,'lat':point['lat'],'lng':point['lon'],
            'matched_name':row.get('poi',{}).get('name'), 'provider_id':row.get('id'),
            'address':row.get('address',{}).get('freeformAddress'),'source':'TomTom Search API',
            'waiting_permission':'unknown'}
        print(f'{i}/{len(QUERIES)} anchors={len(zones)}',flush=True)
    document={'schema':'gigca_geographic_anchors_v1','scope':'hcmc_pre_2025_no_di_an',
        'fetched_at':datetime.now(timezone.utc).isoformat(), 'zones':zones,'rejected':rejected,
        'boundary':{'source_url':('https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_VNM_1.json.zip' if 'NAME_1' in feature['properties'] else GEOMETRY_URL),
            'version':('GADM 4.1, pre-2025' if 'NAME_1' in feature['properties'] else 'geoBoundaries 2008'),
            'license':('GADM academic/non-commercial; no redistribution without permission' if 'NAME_1' in feature['properties'] else 'Public Domain (geoBoundaries metadata)'),
            'sha256':hashlib.sha256(boundary_path.read_bytes()).hexdigest(),'extrema':extrema,
            'note':'Approximate dataset polygon extrema; not officially surveyed city extremities.'},
        'limitations':['Geocoded anchors are not verified legal waiting places.',
            'Sparse anchors do not establish continuous coverage between them.',
            'Dĩ An and Bình Dương are excluded by the historical polygon.',
            'No measured demand, fares or trip logs are provided by this catalog.']}
    (args.output/'anchors.json').write_text(json.dumps(document,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'anchors':len(zones),'rejected':len(rejected),'extrema':extrema},ensure_ascii=False))
if __name__=='__main__': main()
