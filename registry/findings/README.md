# Finding registry

This directory is the authoritative source for the finding catalog and its
message-routing rules. It replaces the former flat `registry/findings.yml`,
which mixed static finding metadata with hundreds of repeated routing records.

## Layout

- `catalog/<record>.yml` contains the stable finding definitions whose primary
  `record` is that family. A finding code must occur in exactly one catalog
  shard.
- `routes/<finding-code>.yml` contains the message routes for one ambiguous
  finding. Rules with the same record, invariant, scope, and evidence share a
  `matches` list.

The route files are source data, not generated output. Matching is by substring.
`tools/finding_registry.py` expands grouped rules and orders matches longest
first, so a general discriminator cannot shadow a more specific one.

## Commands

Load every shard, reject duplicate YAML keys, and validate the directory
structure:

```sh
python3 tools/finding_registry.py check
```

Print counts derived from the current data:

```sh
python3 tools/finding_registry.py stats
```

Produce the historical flat YAML shape for a compatibility consumer:

```sh
python3 tools/finding_registry.py export /tmp/findings.yml
```

The export is generated. Do not copy it back over the authoritative shards.

## Adding a finding

1. Add its static definition to the catalog shard named by its primary
   `record`.
2. If `ambiguous: true`, add or update
   `routes/<finding-code>.yml`. Group messages that resolve to the same role.
3. Run `python3 tools/check_registry.py`. The check verifies source attribution,
   invariant ownership, route uniqueness, and every message the oracle can
   emit.

