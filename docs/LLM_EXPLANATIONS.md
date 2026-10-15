# LLM explanations

The engine still owns ranking, targets, metrics and model inference. `api/llm_explanations.py`
composes the displayed plan summary after `api/dashboard.py` builds its result.

Enable in the root `.env`:

```dotenv
GIGCA_LLM_EXPLANATIONS=true
GIGCA_LLM_BASE_URL=https://api.shopaikey.com/v1
GIGCA_LLM_API_KEY=
GIGCA_LLM_MODEL=
```

The existing compatible-provider credentials can be reused. They stay on the backend.
Compose explicitly passes these variables; rebuild/recreate the backend after changes.
Without credentials, when disabled, busy, timed out or invalid, the original engine summary remains.

## Grounding and prompt

`SYSTEM_PROMPT` (driver-natural-poi-v4) asks for a natural Vietnamese paragraph,
2–3 sentences, roughly 45–85 words, with supporting evidence IDs. The LLM writes new
wording instead of selecting prewritten sentences. Exact numbers stay in the metric cards;
paragraphs with digits, unsupported POI groups, schedules or guarantees are rejected.
These checks reduce obvious unsupported claims; they are not a proof of semantic truth.
Each objective falls back independently when its paragraph fails validation.
Engine ranking, target and numerical fields are never modified.

## POI context

In live mode, fetch one Nearby Search page of up to 100 POIs within 600 m,
without a category filter. Deduplicate and validate coordinates, then retain at most
10 places TOTAL per destination, selecting round-robin across provider categories
prioritizing schools, shopping centers and offices/companies, sharing slots across
these groups before filling remaining slots with other types. Nearest places within
each group come first. This favors type diversity, not an exhaustive
inventory or the ten absolute nearest places. Unknown categories remain available.
Supply names of up to two places per group to the explanation prompt. Cache 15 min.
Classification is provider-reported; unavailable types are never invented.
Only at least 3 retained distinct places support a description of multiple nearby places.
These context POIs are distinct from the 3 cafe rest candidates in the live collector.
No opening/shift/dismissal times or passenger counts are inferred from a POI match.
A single matching school cannot substantiate “many schools” or “students leaving now”.

## Operations

LLM call timeout 12 s, no automatic retry, max 1200 output tokens, 300 s bounded cache;
2 simultaneous explanation pipelines per backend process. POI calls timeout 4 s each.
Upstream redirects disabled; key, request URLs and upstream error bodies are never logged.
No account identity or personal trip logs are sent. Only public destination coordinates go
to TomTom; the LLM receives evidence text and current local time, not GPS or account IDs.

`explanation_status` reports engine fallback or grounded LLM composition, prompt version,
evidence IDs and POI context for inspection. This is optional additive response metadata;
frontend reads the existing `plan.summary` field with no new UI required.

Tests: `python -B -m unittest api.tests.test_llm_explanations -v`.
