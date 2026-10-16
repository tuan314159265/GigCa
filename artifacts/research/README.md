# Approved expanded synthetic snapshot

Research/demo only. Restore with `python scripts/restore_release.py` from repository root.
Archives contain the approved 32 simulated drivers, accepted LLM persona prompts/responses,
47-anchor expanded dataset, and the trained Logistic Hazard + quantile Gradient Boosting model.
No personal account database, credentials, rejected attempts, intermediate datasets, old models,
raw camera snapshots, raw provider responses, or GADM polygon are included.

SHA256 and every member hash are recorded in manifest.json. Original dataset checksums and
training report remain unchanged. Model joblib SHA256:
`2804e216dda2a421f73bfe282ad65b06a3c028cd119b9afaafcfd7ee855716f0`.
Only load trusted joblib files. Use pinned runtime versions from api/model-requirements.txt.

Generated movement, wait, fare and weather values are simulation assumptions, not measurements.
The LLM generated behavioral personas; the numerical event simulator generated histories.
Source coordinates: TomTom Search; underlying coordinates remain subject to provider terms.
Boundary provenance: GADM 4.1 (academic/noncommercial; polygon excluded from redistribution).
This snapshot grants no additional rights to third-party geographic data.
