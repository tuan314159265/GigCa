# Expanded geography — TP.HCM before the 2025 merger

Scope requested: historical HCMC only. Dĩ An, Bình Dương and Bà Rịa–Vũng Tàu excluded.
No production model or historical synthetic dataset was overwritten.

## Local artifacts

- `.cache/geography/hcmc-pre-merger/anchors.json`: 47 geocoded anchors.
- `anchors-preview.html`: standalone hoverable SVG preview (not navigation or model coverage).
- `geocoding-pois.json`: raw POI search responses for reproducibility.
- `boundary-gadm41.geojson`: local GADM 4.1 polygon; do not commit or redistribute.

GADM source: https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_VNM_1.json.zip
License: https://gadm.org/license.html — academic/non-commercial use; redistribution requires permission.
Polygon extrema are approximate dataset vertices, NOT official surveyed extremities:

| Direction | Latitude | Longitude |
|---|---:|---:|
| North | 11.1603 | 106.4561 |
| South | 10.3542 | 106.8346 |
| East | 10.5421 | 107.0273 |
| West | 10.9916 | 106.3567 |

The initial geoBoundaries 2008 polygon excluded some coastal POIs; it remains local for
comparison but is not the final catalog boundary. Use the explicit GADM boundary when refreshing.
TomTom search returns geocoded positions, not verified parking/road access. Name, district
hints and polygon inclusion are checked; this is not independent on-site verification.
No matching POI is invented to fill rejected searches. Raw results/reasons remain auditable.

## Code

`scripts/build_synthetic_anchor_catalog.py` queries named locations, rejects generic city
centroids, weak name matches, out-of-boundary locations and near-duplicates.

```powershell
.\.venv\Scripts\python.exe -m scripts.build_synthetic_anchor_catalog --output .cache/geography/hcmc-pre-merger --resume --boundary .cache/geography/hcmc-pre-merger/boundary-gadm41.geojson
```

`generate --zones` explicitly loads the new catalog and remaps home zones evenly across
personas, with six nearest preferred zones. Existing persona files are not rewritten;
original zone assignments are retained in output provenance. The old six-zone default remains.
Expanded destinations use distance weights exp(-distance_km/5), a declared simulation
hypothesis rather than measured OD probabilities. Legacy sampling remains unchanged.
The new manifest stores its zone catalog and source hash. `export_catalog` reads those
anchors instead of incorrectly attaching the old six anchors to a newly trained artifact.

## Historical generation example (superseded by completed cohort below)

```powershell
.\.venv\Scripts\python.exe -m experiments.synthetic generate --personas .cache/synthetic/gigca-drivers-32-v2/personas.json --zones .cache/geography/hcmc-pre-merger/anchors.json --days 42 --seed 7 --output .cache/synthetic/hcmc-expanded-32/contextual-seed7
```

Before training/activation, audit per-region and time-bin sample counts, matched cycles,
trip distances and geographic holdouts. Sparse anchors do not imply continuous city coverage.
The current model's 2 km admission rule is unchanged. Jitter around an anchor and approximate
straight-line travel are not guaranteed to remain inside an administrative polygon or on roads;
strict point/path clipping or real routing remains necessary before claiming that stronger property.
This section describes the pre-training geography stage; see the release status below.


## Completed API-generated cohort — 15 October 2026

Canonical dataset: `.cache/synthetic/hcmc-expanded-32/contextual-seed7/`.
32 new ShopAIKey personas, 16 behavior cells x 2 replicas, 47 TomTom anchors.
8 validated API batches; rejected responses retained, no numeric autofill substituted.
120 simulated days end on 14 October 2026. Balanced planned shifts cover every anchor
in all four ML slices, with complete additional histories retained outside those slices.
2,794 active shifts include 1,318 outside the four ML slices.

25,235 raw trips; 37,098 waits; 18,510 engine-matched cycles across full histories.
Every split covers all 47 anchors with at least 5 waits and 3 matched cycles per anchor.
Zero event endpoints outside the polygon; zero inferred pairs inconsistent with simulator links.
Read back all JSON logs and CSV counts; verified SHA256 for 102 new files and 35 unchanged
original artifacts (including the approved model). All 19 synthetic unit tests passed.
Training and activation subsequently completed: `.cache/models/logistic-hazard-quantile-gb-hcmc`.
The committed archives restore this dataset and model; see root README and `artifacts/research/manifest.json`.

These checks establish internal consistency and designed coverage, not statistical sufficiency
or real-world calibration. Labels/weather/fares remain synthetic. No per-trip routing API calls
were made. Sparse anchors do not establish continuous city coverage.
Use canonical `contextual-seed7/`; `audit-split-schedule-seed7/` is an intermediate audit only.
See the local cohort README and `coverage.csv`, `coverage.json`, `READY.json`, `checksums.json`.

Reproduce from saved API personas into a NEW output:

```powershell
.\.venv\Scripts\python.exe -m experiments.synthetic.expanded_dataset --personas .cache/synthetic/hcmc-expanded-32/personas.json --zones .cache/geography/hcmc-pre-merger/anchors.json --boundary .cache/geography/hcmc-pre-merger/boundary-gadm41.geojson --days 120 --end-date 2026-10-14 --seed 7 --output .cache/synthetic/hcmc-expanded-32-rerun/contextual-seed7
```
