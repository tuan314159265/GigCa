"""Export the portal's published camera catalog; never bypass authentication.

Python standard library only. A successful HTTP response is not enough: the
portal may return an authentication error inside JSON with status 200.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import HTTPCookieProcessor, Request, build_opener

BASE = "https://giaothong.hochiminhcity.gov.vn"
ENDPOINT = BASE + "/ajaxpro/VDMS.Web.Library.AJAX.FolderAjax,VDMS.Web.Library.ashx"
FIELDS = ["CamId", "Code", "Location", "SnapshotUrl", "CamType", "Disctrict",
          "Publish", "ManagementUnit", "CamStatus", "PTZ", "Angle"]


def parse_ajaxpro(text):
    # Translate known data constructors only, outside strings. Never eval JS.
    output, stack = [], []
    i, quoted, escaped = 0, False, False
    constructors = {"new Ajax.Web.DataTable(": "__ajaxpro_table",
                    "new Ajax.Web.DataSet(": "__ajaxpro_dataset", "new Date(": "__ajaxpro_date"}
    while i < len(text):
        character = text[i]
        if quoted:
            output.append(character)
            if escaped: escaped = False
            elif character == "\\": escaped = True
            elif character == '"': quoted = False
            i += 1
            continue
        if character == '"':
            quoted = True
        matched = next((prefix for prefix in constructors if text.startswith(prefix, i)), None)
        if matched:
            output.append('{"' + constructors[matched] + '":[')
            stack.append(matched)
            i += len(matched)
            continue
        if character == ")" and stack:
            stack.pop()
            output.append("]}")
        else:
            output.append(character)
        i += 1
    if stack: raise ValueError("AjaxPro constructor không kết thúc hợp lệ")
    return json.loads("".join(output))


def camera_rows(value):
    if isinstance(value, dict):
        if "__ajaxpro_table" in value:
            columns, rows = value["__ajaxpro_table"][:2]
            names = [column[0] if isinstance(column, list) else column for column in columns]
            for row in rows:
                yield from camera_rows(dict(zip(names, row)))
            return
        if "CamId" in value:
            yield value
        else:
            for child in value.values():
                yield from camera_rows(child)
    elif isinstance(value, list):
        for child in value:
            yield from camera_rows(child)


def coordinates(row):
    # Do not guess coordinates from a place name or projected geometry.
    lat = row.get("Latitude", row.get("latitude"))
    lng = row.get("Longitude", row.get("longitude"))
    if lat is None or lng is None:
        shape = row.get("Shape")
        location = row.get("Location")
        if shape is None and isinstance(location, dict) and "__ajaxpro_table" in location:
            columns, rows = location["__ajaxpro_table"][:2]
            if rows:
                geometry = dict(zip([c[0] if isinstance(c, list) else c for c in columns], rows[0]))
                shape = geometry.get("Shape")
        match = re.fullmatch(r"\s*POINT\s*\(\s*([-+\d.eE]+)\s+([-+\d.eE]+)\s*\)\s*", str(shape), re.I)
        if match:
            lng, lat = match.groups()
    try:
        lat, lng = float(lat), float(lng)
        if math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180:
            return lat, lng
    except (TypeError, ValueError):
        pass
    return None, None


def fetch_catalog():
    opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
    headers = {"User-Agent": "GigCa-camera-catalog-prototype/1.0",
               "Referer": BASE + "/Map.aspx"}
    # Only normal anonymous page cookies; no credentials or private tokens.
    with opener.open(Request(BASE + "/Map.aspx", headers=headers), timeout=30) as response:
        response.read()
    payload = {"path": "/root/vdms/tangthu/data/layerdata/camera", "isInTree": False,
               "searchKey": "", "layer": ["CAMERA"], "detail": True, "page": 0,
               "limit": -1, "filterQuery": ["Publish:true"], "sortby": None,
               "returnFields": FIELDS}
    request = Request(ENDPOINT, data=json.dumps(payload).encode("utf-8"),
                      headers={**headers, "Content-Type": "application/json",
                               "X-AjaxPro-Method": "SearchQuery"}, method="POST")
    with opener.open(request, timeout=30) as response:
        body = parse_ajaxpro(response.read().decode("utf-8-sig"))
    if not isinstance(body, dict):
        raise RuntimeError("Response không đúng cấu trúc JSON đã dự kiến.")
    if body.get("error"):
        error = body["error"]
        message = error.get("Message", "Nguồn từ chối request") if isinstance(error, dict) else str(error)
        raise RuntimeError(f"Cổng thành phố: {message}. Cần nguồn API/export được cấp quyền; không thử vượt xác thực.")
    rows = list(camera_rows(body.get("value")))
    if not rows:
        raise RuntimeError("Không đọc được bản ghi camera; không ghi đè file dữ liệu hiện có.")
    cameras = {}
    for row in rows:
        identifier = row.get("NodeId") or row.get("Id") or row.get("CamId")
        if not identifier:
            continue
        lat, lng = coordinates(row)
        cameras[str(identifier)] = {
            "id": str(identifier), "camera_id": row.get("CamId"),
            "name": row.get("DisplayName") or row.get("Title") or row.get("Code"),
            "node_id": row.get("NodeId"), "data_id": row.get("DataId"),
            "latitude": lat, "longitude": lng,
            "reported_status": row.get("CamStatus"),
            "image_status": "unchecked", "raw": row,
        }
    if not cameras:
        raise RuntimeError("Không có ID camera hợp lệ; không ghi file.")
    return {"source_page": BASE + "/Map.aspx", "fetched_at": datetime.now(timezone.utc).isoformat(),
            "scope": "published cameras returned by SearchQuery", "completeness": "unverified",
            "count": len(cameras),
            "reported_up_count": sum(c["reported_status"] == "UP" for c in cameras.values()),
            "with_coordinates": sum(c["latitude"] is not None for c in cameras.values()),
            "images_checked": False, "cameras": list(cameras.values())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/raw/cameras/hcmc-public-cameras.json"))
    args = parser.parse_args()
    try:
        catalog = fetch_catalog()
    except Exception as error:
        parser.exit(1, f"Không xuất dữ liệu: {error}\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(args.output)
    print(f"Đã xuất {catalog['count']} camera; {catalog['with_coordinates']} có tọa độ. Chưa xác nhận đầy đủ hoặc ảnh hoạt động.")
    print(args.output)


if __name__ == "__main__":
    main()
