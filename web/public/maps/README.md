# Offline GigCa map preview

This small geographic snapshot covers central Ho Chi Minh City at zoom 14.
The UI uses local tiles only in preview mode. No traffic data or routing geometry
is inferred from these images. It is a fixed basemap, not a live map service.

Source: Esri ArcGIS Canvas World Light Gray Base and World Light Gray Reference.

- https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer
- https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer

Attribution: Esri, HERE, Garmin, OpenStreetMap contributors, and the GIS user community.
Downloaded 2026-10-07 for this local prototype. Tiles x=13046..13050,
y=7696..7700. Attribution remains visible on the map.

Live mode uses the existing GigCa TomTom proxy, or OpenStreetMap if TomTom is
not configured. Provider terms and API configuration apply when deploying.
