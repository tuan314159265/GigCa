"""Optional ML layer (v5). Needs numpy + scikit-learn; the statistical engine works without it.

Everything here is trained ONLY on data the driver (or, for the community pool, many drivers) contributed, is seeded and
deterministic, and is always reported next to the statistical baseline so a model that does not beat it is not used.

There is NO synthetic training data and NO simulator in this package: a model is only fitted on the trip log / wait spells
supplied with the snapshot (real driver data). Below `ml.min_spells` / `ml.min_cycles` nothing is fitted and the engine
says so; above it, the model is used only if it beats the statistical baseline on a time-ordered hold-out.
"""
