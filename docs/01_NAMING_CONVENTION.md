# Naming and collaboration convention

## Branches and commits

- `main`: stable integration point.
- `dev`: shared integration branch while the team is developing.
- Work branches: `feat/<short-name>`, `fix/<short-name>`, `docs/<short-name>`.
- Commit prefixes: `[feat]`, `[fix]`, `[docs]`, `[refactor]`, `[chore]`.

## Code and files

- Python modules/functions/variables: `snake_case`; classes: `PascalCase`.
- TypeScript functions/variables: `camelCase`; React components and types: `PascalCase`.
- Constants: `UPPER_SNAKE_CASE`.
- Python file: `snake_case.py`; React component: `PascalCase.tsx`; tests: `test_<subject>.py` or `<subject>.test.tsx`.
- API fields use `snake_case` in JSON. Units are part of field documentation or field names (for example `_km`, `_min`, `_mm_h`, `_vnd`).

See root [`RULES.md`](../RULES.md) for data handling and contract rules.

