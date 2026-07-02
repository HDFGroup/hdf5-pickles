# h5policy Tests

Phase 3 reserves the corpus layout described in `h5policy.md`:

- `valid/`
- `malformed/`
- `policy/`
- `cve/`
- `expected/`

The current implementation is validated against the repository `file.h5`, compact
hard-link traversal, and simple synthetic malformed or policy-denied inputs.
Future phases should add expected YAML files with required findings and forbidden
outcomes.
