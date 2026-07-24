# AGENTS instructions

## CVE process

- Apply the [§11 CVE process](./docs/A%20CVE%20strategy%20for%20the%20HDF5%20library.md)
  to the specimen(s) and produce the complete case documentation — the real
  artifacts, not a sketch of one.

- Consider 32-bit vs. 64-bit platform differences, and any other relevant platform differences, when producing the
  case documentation.

- Local evidence only: no web fetches, no publishing, nothing outbound. If the
  advisory text would have mattered, say so in the record instead of going to get it.

- I expect the oracle already rejects this. Treat "are we covered?" as something to
  confirm in passing, not the point — the point is what a fully filled-in bundle
  looks like when every field is measured rather than asserted.

- Do not trust any previous work at `cases/*`, most likely leftovers from previous sessions,
  such as TODOs, plus some hand-written probe .c files worth keeping. Treat it as advisory,
  but not authoritative.

- If there's a half-finished bundle at `cases/*` from an earlier session — TODOs,
  plus some  hand-written probe .c files worth keeping — refresh it against
  current HEAD without losing those.

- Stop before anything tracked — no gencorpus generator, no `registry/` or
  `h5policy/tests/` edits. List them as promotion steps and I'll decide.

## Documentation

- Always keep the documentation up to date. If you add a new feature, tool, or API, or change an existing one, update the relevant documentation.

- Make documentation testable and include them in the CI/CD pipeline to catch any discrepancies early.

- If documentation tests are available, run them to ensure the documentation is accurate. Wire them into the CI/CD pipeline to catch any discrepancies early. See for example the `docs-check` target in [`CMakeLists.txt`](./CMakeLists.txt).

## Boundaries

- **Ask first**
  - Large cross-package refactors.
  - New dependencies with broad impact.
  - Destructive data or migration changes.
- **Never**
  - Commit secrets, credentials, or tokens.
  - Do not introduce GHSA-* IDs into comments or commit messages, as they are not authoritative and can be misleading. Use OSS-Fuzz numbers instead.
  - Edit generated files by hand when a generation workflow exists.
  - Use destructive git operations unless explicitly requested.

## References

- [CVE strategy for the HDF5 library](docs/A%20CVE%20strategy%20for%20the%20HDF5%20library.md)
- [What is bounded raw decode?](docs/What%20is%20bounded%20raw%20decode.md)
