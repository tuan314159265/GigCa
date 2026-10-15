"""Public city-camera catalog and bounded snapshot proxy. No arbitrary URL input."""
from __future__ import annotations

import json
import math
import os
import re
import threading
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

from api.errors import ApiError
from engine.src.geo import haversine_m

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PAGE = 'https://giaothong.hochiminhcity.gov.vn/Map.aspx'
_cache = {}
_lock = threading.Lock()
_limit = threading.BoundedSemaphore(3)
MAX_BYTES = 3 * 1024 * 1024


@lru_cache(maxsize=2)
def _read_catalog(path, modified):
    data = json.loads(Path(path).read_text(encoding='utf8'))
    rows = {}
    for row in data.get('cameras', []):
        lat, lng = row.get('latitude'), row.get('longitude')
        if (isinstance(lat, (int,float)) and isinstance(lng, (int,float))
                and math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180
                and re.fullmatch(r'[\w-]{1,80}', str(row.get('id','')))):
            rows[row['id']] = row
    return data, rows


def catalog():
    path = Path(os.environ.get('GIGCA_CAMERA_CATALOG', ROOT/'data/raw/cameras/hcmc-public-cameras.json'))
    try:
        return _read_catalog(str(path.resolve()), path.stat().st_mtime_ns)
    except (OSError, ValueError):
        raise ApiError(503,'camera_catalog_unavailable','Chưa có danh sách camera thành phố.') from None


def distance_to_segment(lat, lng, a, b):
    # Local metric projection for HCMC-scale camera-to-road distance.
    scale = 111320
    cosine = math.cos(math.radians(lat))
    ax, ay = (a[1]-lng)*scale*cosine, (a[0]-lat)*scale
    bx, by = (b[1]-lng)*scale*cosine, (b[0]-lat)*scale
    dx, dy = bx-ax, by-ay
    t = max(0, min(1, -(ax*dx+ay*dy)/(dx*dx+dy*dy))) if dx*dx+dy*dy else 0
    return math.hypot(ax+t*dx, ay+t*dy)


def near_route(payload):
    lines = payload.get('lines')
    radius = payload.get('radius_m',300)
    if (not isinstance(lines,list) or not 1 <= len(lines) <= 40 or
            isinstance(radius,bool) or not isinstance(radius,(int,float)) or not math.isfinite(radius) or not 50 <= radius <= 1000):
        raise ApiError(422,'invalid_route','Cần các đoạn tọa độ và bán kính 50–1000 m.')
    count = 0
    for line in lines:
        if not isinstance(line,list) or not 1 <= len(line) <= 500:
            raise ApiError(422,'invalid_route','Đoạn tuyến không hợp lệ.')
        count += len(line)
        for pt in line:
            if (not isinstance(pt,list) or len(pt)!=2 or
                    any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in pt) or
                    not -90 <= pt[0] <= 90 or not -180 <= pt[1] <= 180):
                raise ApiError(422,'invalid_route','Tọa độ không hợp lệ.')
    if count > 500:
        raise ApiError(422,'invalid_route','Tối đa 500 điểm cho một yêu cầu camera.')
    metadata, cameras = catalog()
    candidates = []
    for camera in cameras.values():
        # Declared offline cameras are not candidates. UP does not prove image freshness.
        if str(camera.get('reported_status','')).upper() not in ('UP','UNKNOWN','NONE',''):
            continue
        lat,lng=camera['latitude'],camera['longitude']
        distance=min(min(distance_to_segment(lat,lng,a,b) for a,b in zip(line,line[1:]))
                     if len(line)>1 else haversine_m(lat,lng,*line[0]) for line in lines)
        if distance <= radius:
            candidates.append({'id':camera['id'], 'name':camera.get('name') or 'Camera giao thông',
                'camera_id':camera.get('camera_id'),
                'lat':lat,'lng':lng,'distance_to_route_m':round(distance),
                'image_status':'unchecked', 'image_url':f"/api/v1/cameras/{camera['id']}/image"})
    candidates.sort(key=lambda c:(c['distance_to_route_m'],c['id']))
    return {'cameras':candidates[:3], 'radius_m':radius, 'source_page':SOURCE_PAGE,
            'catalog_fetched_at':metadata.get('fetched_at'), 'captured_at':None,
            'match_basis':'distance_to_selected_route_segments_not_viewing_direction'}


def allowed_image_url(url):
    try:
        parsed=urlsplit(url)
        port=parsed.port
    except ValueError:
        return False
    if parsed.username or parsed.password or parsed.fragment:
        return False
    return ((parsed.scheme in ('http','https') and parsed.hostname=='camera.thongtingiaothong.vn'
             and port in (None,80,443) and re.fullmatch(r'/api/snapshot/[a-fA-F0-9]{24}',parsed.path) is not None)
            or (parsed.scheme=='https' and parsed.hostname=='giaothong.hochiminhcity.gov.vn'
                and ((port in (None,443) and parsed.path=='/Render/ImageHandler.ashx')
                     or (port==8007 and parsed.path=='/Render/CameraHandler.ashx'))))


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed_image_url(newurl):
            raise RuntimeError('Nguồn ảnh chuyển tới địa chỉ không được phép.')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def download_image(url):
    if not allowed_image_url(url):
        raise RuntimeError('Nguồn ảnh không hợp lệ.')
    request=Request(url,headers={'User-Agent':'GigCa-public-camera/1.0', 'Referer':SOURCE_PAGE,
                                 'Accept':'image/jpeg,image/png,image/webp'})
    with build_opener(SafeRedirect()).open(request,timeout=8) as response:
        body=response.read(MAX_BYTES+1)
        content_type=response.headers.get_content_type()
    signatures = {'image/jpeg':body.startswith(b'\xff\xd8\xff'),
                  'image/png':body.startswith(b'\x89PNG\r\n\x1a\n'),
                  'image/webp':body.startswith(b'RIFF') and body[8:12]==b'WEBP'}
    if len(body)>MAX_BYTES or not signatures.get(content_type,False):
        raise RuntimeError('Nguồn không trả ảnh hợp lệ.')
    return body,content_type


def camera_image(identifier):
    _, cameras=catalog()
    camera=cameras.get(identifier)
    if camera is None:
        raise ApiError(404,'camera_not_found','Camera không có trong danh sách công khai.')
    now=time.monotonic()
    with _lock:
        entry=_cache.get(identifier)
        if entry and now < entry[0]:
            if entry[1] is None:
                raise ApiError(503,'camera_image_unavailable','Camera hiện không tải được ảnh. Hãy thử camera khác.')
            return entry[1]
    if not _limit.acquire(blocking=False):
        raise ApiError(429,'camera_busy','Đang tải nhiều camera. Thử lại sau ít giây.')
    try:
        urls=[]
        camid=str(camera.get('camera_id') or '')
        if re.fullmatch(r'[a-fA-F0-9]{24}',camid):
            urls.append('https://giaothong.hochiminhcity.gov.vn/Render/ImageHandler.ashx?'+urlencode({'id':camid}))
        snapshot=(camera.get('raw') or {}).get('SnapshotUrl')
        if isinstance(snapshot,str) and allowed_image_url(snapshot):
            urls.append(snapshot)
        if re.fullmatch(r'[a-fA-F0-9]{24}',camid):
            urls.append('https://giaothong.hochiminhcity.gov.vn:8007/Render/CameraHandler.ashx?'+urlencode({'id':camid}))
        for url in urls:
            try:
                body,kind=download_image(url)
                value=(body,kind,datetime.now(timezone.utc).isoformat())
                with _lock:
                    # Bound memory, including large image responses.
                    if len(_cache)>=16: _cache.pop(next(iter(_cache)))
                    _cache[identifier]=(time.monotonic()+20,value)
                return value
            except (OSError,RuntimeError,HTTPError,URLError,ValueError):
                continue
        with _lock:
            if len(_cache)>=16: _cache.pop(next(iter(_cache)))
            _cache[identifier]=(time.monotonic()+20,None)
        raise ApiError(503,'camera_image_unavailable','Camera hiện không tải được ảnh. Hãy thử camera khác.')
    finally:
        _limit.release()
