"""Lightweight point containment for local historical study polygons (GeoJSON lon/lat)."""
def ring_contains(point,ring):
    lat,lng=point;value=False
    for a,b in zip(ring,ring[1:]+ring[:1]):
        if (a[1]>lat)!=(b[1]>lat) and lng < (b[0]-a[0])*(lat-a[1])/(b[1]-a[1])+a[0]: value=not value
    return value

def contains(point,geometry):
    polys=geometry['coordinates'] if geometry['type']=='MultiPolygon' else [geometry['coordinates']]
    return any(ring_contains(point,p[0]) and not any(ring_contains(point,h) for h in p[1:]) for p in polys)
