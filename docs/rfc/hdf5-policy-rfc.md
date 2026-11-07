# HDF5 Policy RFC: Decoupling Validation from Authorization (draft)

> **Draft for review.** This covers the Introduction and Sections 1–4 — Use
> cases, Scope and controls inventory, Proposed interface, and Implementation and
> test plan. Further considerations and the appendix are still to come.

## Introduction

An HDF5 file can do more than hold data. By design, a well-formed file can
instruct the library — during an ordinary read — to **open other files**,
**reach arbitrary filesystem paths**, or **load and run external code**. These
are intentional, long-standing features: external datasets and external raw
storage, virtual datasets (VDS), external links, the multi/family virtual file
drivers, and dynamically loaded filter / VOL / VFD plugins.

Today the library treats **validity and authorization as the same thing.** If a
file is well-formed, it is automatically authorized to trigger these actions.
So an application that merely *reads a dataset* from an untrusted file can be
made to read `/proc/self/environ`, open `/etc/passwd`, or execute third-party
code — with nothing signalling that a trust boundary was crossed.

That conflation is the root problem. As long as validity implies authorization,
every "should the library do this?" question collapses into "is it a bug or a
feature?" — a debate that cannot be won, because the action is, by design, a
feature. This RFC proposes to **break the link between validation and
authorization.** Validation answers *"is this a well-formed HDF5 file?"*;
authorization — a separate, application-controlled decision — answers *"may this
file cause the library to cross a trust boundary?"* **By default, validity must
authorize nothing.**

The need is not hypothetical: in July 2026 a crafted HDF5 file was the opening
vector of a real intrusion (Section 1). This RFC originates in a maintainer
request to add controls for these cross-file features —
[HDFGroup/hdf5 issue #6618](https://github.com/HDFGroup/hdf5/issues/6618), which
enumerates them and points to that incident. The scope of this RFC is **every
trust-boundary-crossing action a file can induce** — external file access,
filesystem reach, and external code loading.

## 1. Use cases

### 1.1 Risk scenarios — where validity-equals-authorization bites

**Scenario A — Untrusted dataset in an ingest pipeline (the [Hugging Face
incident](https://huggingface.co/blog/agent-intrusion-technical-timeline#vector-1-hdf5-external-raw-storage-file-read),
July 2026).** An attacker committed a dataset to Hugging Face whose
configuration pointed each data "split" at a small, *valid* `.h5` file. Each
file used HDF5 **external raw storage** to declare that its dataset's bytes
lived at a **local filesystem path** on the worker — among them
`/proc/self/environ` and the worker's own source files. When the production
data-loader opened these files and read the datasets, the library transparently
read those local paths and returned their contents as dataset data. The result:
the worker's full environment (the environment variables of its Kubernetes
*pod*) — including secrets and credentials — plus internal source code,
disclosed to the attacker. **No code was executed**; this
was pure file disclosure through a normal read. The platform's URL allowlist,
which governed *network* fetches, never saw it, because external-reference reads
are *local* filesystem operations. This disclosure was the quiet first foothold
of a multi-stage intrusion: the leaked credentials and reconnaissance enabled
the escalation that followed.

**Scenario B — Untrusted file uploaded to a service (the archetype).** A
published proof-of-concept ([h5py issue #2891](https://github.com/h5py/h5py/issues/2891))
crafts an HDF5 file with an
external dataset pointing at `/etc/passwd`. A victim web application accepts the
upload, reads the dataset with default settings, and returns the contents in its
response — disclosing a local file to the attacker. This is the general shape for
any service that parses untrusted HDF5: external datasets, VDS, and external
links each let an uploaded file name a path the server then reads. The h5py
maintainers declined to add enforcement in the binding, noting the fix belongs
in the library.

**Why this is escalating.** These features have existed for years, but the
exposure is growing. Machine-learning (ML) and AI pipelines now routinely ingest
third-party datasets and models, and automated agents probe them at machine
scale — in the Hugging Face case the agent took roughly 17,600 actions, trying
many failing paths and repeatedly returning to leads, turning an ordinary
architectural weakness into a critical one faster than a human attacker could.
Detection-based defenses are the wrong tool for this: parser hardening and fetch
allowlists must anticipate every malformed input or attack path and fail on the
one case they miss — the Hugging Face URL allowlist watched *network* fetches but
not *local* reads, so it never saw the attack. An authorization boundary that
denies *by default* works differently: it needs to recognize nothing, because the
trust-boundary action is simply unavailable to untrusted input unless the
application turns it on. Such a boundary holds no matter how the attack is shaped
or how many probes are thrown at it — so its safety does not depend on the library
catching every parser bug or on defenders foreseeing every probe.

**The common pattern.** Scenarios A and B are not unrelated bugs. They are one
structural shape:

> untrusted file → ordinary read → trust-boundary crossing (external open /
> path reach / code load) → disclosure or code execution

with no authorization checkpoint between "the file is valid" and "the library
acts." Inserting that checkpoint — an authorization decision the application
controls — is what this RFC addresses.

### 1.2 Legitimate-use scenarios — what must keep working

These features exist because real applications use them deliberately. Any
control must let **authorized** callers keep using them; the goal is to deny
them *by default to untrusted input*, not to remove them. Each scenario below
states the feature's **documented intent** — what the format provides it for.

**L1 — External / raw storage wrapping large existing data.** External datasets
and external raw storage (`H5Pset_external`) let a dataset's raw bytes live in
one or more files *outside* the HDF5 container, at application-chosen offsets, so
an application can expose pre-existing large binary arrays — or data still being
produced by another process or instrument — as HDF5 datasets without copying
them in.

**L2 — Virtual datasets stitching many files.** A virtual dataset
(`H5Pset_virtual`) maps regions of several source datasets — typically one file
each — into a single logical dataset through a stored mapping, so many
separately produced files appear as one array without duplicating their bytes.
Its documented purpose includes assembling per-process or time-sequenced output
into one view.

**L3 — External links across a related file set.** An external link
(`H5Lcreate_external`) names an object — a group or dataset — in another HDF5
file by path, so one file can organize or navigate a collection of related
files as a single hierarchy.

**L4 — Splitting one file across members (multi / family VFD).** The family
driver (`H5Pset_fapl_family`) stores one logical HDF5 file as a series of
fixed-size member files, and the multi driver (`H5Pset_fapl_multi`) maps
different kinds of data to separate files — used to keep a file under a
filesystem's size limit, or to transport it in parts.

**L5 — Reading data compressed with third-party codecs (dynamically loaded
filters).** Registered filter plugins (`H5PL`) let the library read and write
data compressed with community codecs — Blosc, Zstd, LZ4, bitshuffle, and
others — distributed as plugins rather than built into the library, so files
using them are readable wherever the plugin is installed.

**What this means for the design.** The design cannot be built around an
allowlist of known-good uses. It must instead **deny by default and fail loudly
and recoverably**, so that an unanticipated legitimate use surfaces as a clear,
fixable error — a denied action with a documented opt-in — rather than as either
a silent security hole or a silent breakage.

### 1.3 Derived requirements — what the design must provide

The scenarios translate into the requirements below, which the rest of the RFC
must satisfy:

1. **Application-declared, per-file trust.** Trust is not a property of the file
   and cannot be inferred from its bytes; the application declares it per file
   (an untrusted upload vs. a trusted internal file) and the library enforces
   that declaration. The control must be per-file and must hold for concurrent
   files of differing trust open in one process.
2. **File-reference family — per-action granularity + path confinement.**
   Controls must gate each file-reference action distinctly — external datasets,
   external raw storage, virtual datasets, external links, and the multi/family
   VFD — and, for these, confine *where* a reference may resolve (an allowed
   prefix; denying `/proc`, `/sys`, `/dev`), with care for absolute paths, `..`
   escapes, and symlinks.
3. **Code-execution family — allow/deny of dynamic plugin loading.**
   Dynamically loaded filter / VOL / VFD plugins are the code-execution family:
   the risk is running untrusted *code*. The control must be a per-file
   **allow/deny decision** on whether such a plugin may be loaded or run — gated
   distinctly from the file-reference actions. Path confinement does not apply
   here. The deeper question of *which* code is trustworthy — its **provenance**
   (origin and integrity) — is a complementary control, out of scope for this
   RFC and the natural meeting point with work on signed plugins.
4. **Practical defaults, and a safe default.** The controls must group into a
   few practical policy defaults (profiles). The default when an application
   declares nothing should move toward "authorize nothing," with a migration
   path that does not break the legitimate uses above.
5. **Fail-safe and visible.** Because the legitimate-use set can never be
   enumerated completely, a denied action must fail *loudly and recoverably* — a
   clear error and a documented opt-in — rather than silently, so an unforeseen
   legitimate use is a fixable breakage, not a silent security hole.
6. **Detectability.** An application should be able to determine whether a file
   would cross a trust boundary — and where — *without* triggering it. This
   echoes a concrete ask from the h5py discussion
   ([h5py issue #2891](https://github.com/h5py/h5py/issues/2891)), where
   maintainers floated a tri-state `obj.internal` property (internal / external /
   unknown) so a caller can check before reading. Detectability here is a
   *complement* to enforcement, not a substitute for it: detection *instead of*
   enforcement — "detect-only," leaving each application to check and act — is a
   weaker alternative, because it protects only applications that remember to
   check, which the motivating incidents did not. Detect-only is recorded among the
   alternatives (Further considerations); detectability itself — detection
   alongside enforcement — is required here.

## 2. Scope and controls inventory

Section 1 established *why* the library must separate validation from
authorization, and *what* the design must provide. This section is the
**supply** side to Section 1's demand: it enumerates, action by action, exactly
what the library controls. For each trust-boundary-crossing action it records
the action, its risk family, the control that gates it, the behavior today, and
the behavior this RFC proposes. The result is an auditable map — a reviewer can
confirm that every action Section 1 raised has a defined control, and that none
is left implicit.

### 2.1 In scope and out of scope

**In scope.** Every action by which a *well-formed* HDF5 file, read with default
settings, causes the library to cross a trust boundary — open another file,
reach a filesystem path, or load and run external code — during normal
operation. These are the actions inventoried in Section 2.2.

**Out of scope** (deliberately excluded; several recur in Further
considerations):

- **Plugin provenance / signature verification.** The plugin-load *action* is in
  scope (Section 2.2); the provenance *control* on it is not — it is a separate
  RFC's concern, not a later phase of this one. This RFC gates plugin loading
  *on or off* — *may any plugin load for this file?* Verifying the
  origin and integrity of the plugin code (signing) — *which* code is trustworthy
  to run — is a separate, complementary control, the subject of the Signed
  Plugins RFC. Provenance layers on top of this on/off authorization gate rather
  than replacing it: a validly signed plugin can still be malicious.
- **Validation and parser hardening.** Detecting malformed or corrupt metadata
  is a separate concern; this RFC governs authorization of *valid* files and
  does not change how invalid files are rejected.
- **Application-selected remote drivers** — the read-only `ros3`
  (`H5Pset_fapl_ros3`, Amazon S3 and S3-compatible stores) and `hdfs`
  (`H5Pset_fapl_hdfs`) VFDs. These are selected by the application through the
  FAPL, not induced by the file, so they are not a file-driven trust-boundary
  crossing. (The multi / family driver *is* in scope, because its member layout
  travels with the file.)
- **Resource-exhaustion and decompression-bomb defenses.** A valid file can be
  crafted to exhaust memory, CPU, or time on read — for example a metadata count
  that drives a huge allocation, or a small compressed chunk that inflates to
  many gigabytes when decompressed (a decompression bomb). Guarding against this
  is a distinct axis — resource budgets and quotas — from authorizing
  trust-boundary actions, and belongs to a separate mechanism.
- **The write path.** This RFC protects a process *reading* an untrusted file;
  an application's own deliberate use of these features when creating files is
  its own choice.

### 2.2 The controls inventory

| Action | Family | Control | Current default | Proposed default (nothing declared) |
|---|---|---|---|---|
| External storage read (a dataset's raw bytes in a separate file) | file-reference | allow / deny + path confinement | allow — because valid | deny; opt-in within a confined path |
| Virtual dataset (VDS) source open | file-reference | allow / deny + path confinement | allow — because valid | deny; opt-in within a confined path |
| External link traversal | file-reference | allow / deny + path confinement | allow — because valid | deny; opt-in within a confined path |
| Multi / family VFD member open | file-reference | allow / deny + path confinement | allow — because valid | deny; opt-in within a confined path |
| Dynamic filter plugin load | code-execution | allow / deny (on/off gate) | allow — because valid | deny; opt-in |
| Dynamic VOL / VFD plugin load | code-execution | allow / deny (on/off gate) | allow — because valid | deny; opt-in |

Three things the table makes explicit:

- **The current default is identical on every row** — *allow, because the file
  is valid.* That uniform column is exactly the validity-equals-authorization
  conflation Section 1 identifies.
- **The proposed default is the behavior when the application declares
  nothing.** The policy profiles (Section 3) adjust these, within the invariant
  that a denied action always fails safe and visibly (Section 1.3, requirements
  4–5), and within a migration path that does not break existing files overnight
  (Further considerations).
- **The control differs by family.** File-reference actions add *path
  confinement* — an allowed prefix, with `/proc`, `/sys`, `/dev` denied and care
  for `..` and symlinks. For code-execution actions this RFC provides only the
  on/off gate; their other axis — *provenance* (which code is trustworthy,
  Section 1.3, requirement 3) — is a complementary control out of scope here
  (Section 2.1). Dynamic VOL / VFD plugin loading shares the legitimate-use
  rationale of filters (Section 1.2, L5); filters are simply the most common
  case.

### 2.3 Actors

Only three parties take part in an authorization decision:

- **The application** declares the per-file trust and policy, through the FAPL,
  at or before open. It is the only party that can know whether a given file is
  trusted.
- **The file** is the subject the policy is applied to — never a trusted source
  of its own authorization. Nothing in its bytes may raise its own privilege.
- **The library** enforces the declared policy at each action's chokepoint and
  reports a denial as a distinct, recoverable error.

This is the concrete form of Section 1.3, requirement 1: trust is *declared by
the application and enforced by the library, never inferred from the file.*

## 3. Proposed interface

### 3.1 Design basis

Section 1 established the requirements and Section 2 the actions to be governed.
This section proposes the interface that carries them: how an application
declares a per-file policy, what that policy contains, how the library enforces
it, and how an application can detect a trust-boundary crossing without
triggering it.

The interface must satisfy the six Section 1.3 requirements directly:

1. **Application-declared, per-file (req 1):** the policy is set by the
   application on a file access property list (FAPL) and applies per file.
2. **Per-action gating + path confinement (req 2):** each file-reference action
   is gated distinctly, and where a reference may resolve is confined.
3. **Plugin allow/deny (req 3):** dynamic plugin loading is gated by a per-file
   on/off decision; the code's provenance is left to complementary work.
4. **Profiles and a safe default (req 4):** the controls group into a few named
   profiles, with a safe default.
5. **Fail-safe and visible (req 5):** a denied action fails loudly and
   recoverably, with a clear error.
6. **Detectable (req 6):** an application can determine whether a file would
   cross a trust boundary without triggering it.

Two stances shape everything that follows. First, the interface **reuses the
mechanism** worked out in a prior proposal to add a policy profile to H5PL: a
policy value set on a FAPL and snapshotted into shared file state at open. That mechanism already solves the hard part — a
per-file decision that survives concurrent files of differing trust in one
process — so this RFC adopts it rather than reinventing it. Second, the interface
**does not house the policy inside the plugin module.** The policy spans actions
well beyond plugin loading — external storage, virtual datasets, external links,
the multi/family VFD — so this RFC proposes a **dedicated, library-wide policy
interface** that owns the policy value, with each subsystem (the plugin loader
included) merely *consuming* the part that bears on it. Section 3.6 weighs this
choice against the alternative of extending H5PL, and recommends the dedicated
interface.

### 3.2 Declaration and scope

An application declares the policy **before it opens the file**, by setting it on
a file access property list (FAPL) — the same list it already uses to choose a
driver or cache settings — and passing that FAPL to `H5Fopen` (or `H5Fcreate`).
The shape is (names are illustrative; the API shape is settled in Section 3.6):

```c
hid_t fapl = H5Pcreate(H5P_FILE_ACCESS);
H5Pset_policy_profile(fapl, H5_POLICY_STRICT);            /* declare the policy */
hid_t file = H5Fopen(path, H5F_ACC_RDONLY, fapl);         /* snapshot taken here */
```

**The policy is snapshotted into the file's shared state at open.** From that
moment it is fixed for the lifetime of the open file: changing or closing the
source FAPL afterward has no effect, and nothing in the file's own bytes can
alter it. This is the concrete realization of requirement 1 — the library
enforces a decision the application made, and the file cannot influence it.

**The snapshot is per-file, so trust does not leak between files.** Two files
opened in the same process under different policies — an untrusted upload and a
trusted internal file — each carry their own snapshot and are enforced
independently. Because the decision lives in each file's state rather than in a
process-global switch, there is no set-open-restore race and no way for one
file's policy to affect another. This is the central advantage the mechanism
was designed for, and the reason this RFC reuses it.

**Every object opened from the file inherits the snapshot.** Datasets, groups,
and attributes reached through the file identifier are governed by the same
policy, including deferred or asynchronous work that outlives the call that
started it. An application cannot open a file under a strict policy and then
reach a more permissive state through one of its objects.

**The policy is runtime state, never written to the file.** It is not HDF5
format metadata and does not travel with the file — it is the reader's
declaration about *this* open, not a property of the bytes. `H5Fget_access_plist`
returns a FAPL carrying the resolved policy, so an application can audit the live
configuration of an open file.

**Opening the same file more than once.** When a process opens a file that is
already open, HDF5 may share one underlying file state between the opens, and the
policy lives in that shared state. The rule is fail-safe and simple: a reopen
must declare the **same policy** as the one already in force, and a conflicting
request **fails with a clear error**. This prevents a later, more permissive
open from bypassing the policy already applied, and avoids a later open silently
changing the rules for an earlier one. `H5Fget_access_plist` reports the policy
in force. (The exact test for when two opens are "the same file" is an
implementation detail — see Further considerations.)

### 3.3 The policy value

The policy an application declares has two levels: pick a **named profile** for
the common case, or supply a **custom value** for finer control. Both are the
same underlying value — a profile is just a named preset of it.

**Named profiles.** Three profiles cover the common cases:

- **`legacy`** — allow every action, unconfined. The library's historical
  behavior; the backward-compatible default.
- **`confined`** — allow the file-reference actions, but only within a confined
  path (Section 3.4); deny plugin loading. A middle ground for data trusted to
  live in a known location but not to run external code.
- **`strict`** — deny every action. For untrusted input.

```c
typedef enum {
    H5_POLICY_LEGACY   = 0,  /* allow all, unconfined (the default) */
    H5_POLICY_CONFINED = 1,  /* file-reference allowed but path-confined; plugins denied */
    H5_POLICY_STRICT   = 2,  /* deny all */
    H5_POLICY_CUSTOM   = 3   /* a custom value set via H5Pset_policy_value */
} H5_policy_profile_t;
```

A freshly created FAPL contains `H5_POLICY_LEGACY`, preserving current behavior.
`H5_POLICY_CUSTOM` is an output marker: after a custom value is set the getter
reports it, but it cannot be *looked up* as a definition, because it has no
single canonical value.

**The invariant.** Profiles differ only in *authorization* policy. None of them
changes whether corrupt or truncated metadata is rejected — a malformed file is
rejected under every profile.

**What a profile expands to — the value.** Each profile is a preset of a single
policy value, which an application can also set directly. That value carries
exactly the controls this RFC governs, and nothing else:

- a per-action **allow/deny** for each inventoried action — external storage,
  virtual datasets, external links, the multi/family VFD, dynamic filter
  plugins, and VOL/VFD plugins; and
- **path-confinement** configuration for the file-reference actions (an allowed
  prefix, plus a built-in deny list for always-refused paths such as `/proc`;
  the required-versus-default split and the rest of the details are in
  Section 3.4).

Representative shape (names illustrative; the API shape is settled in
Section 3.6):

```c
typedef struct {
    unsigned    version;      /* caller sets to the layout it compiled against */
    size_t      struct_size;
    /* per-action allow/deny — 1 = allow, 0 = deny */
    uint8_t     allow_external_storage;
    uint8_t     allow_vds;
    uint8_t     allow_external_links;
    uint8_t     allow_multi_family_vfd;
    uint8_t     allow_dynamic_filters;
    uint8_t     allow_vol_vfd_plugins;
    /* path confinement for the file-reference actions (see Section 3.4) */
    const char *allowed_path_prefix;   /* NULL = unconfined */
} H5_policy_value_t;
```

It deliberately carries only authorization controls — not resource budgets,
heuristics, or analysis settings, which are inspection concerns (Section 2.1),
not authorization. Every field it exposes is a control the library actually
enforces.

**Versioned and self-describing.** The value begins with `version` and
`struct_size`, which the caller sets to the layout it compiled against. This lets
the value gain fields in a later release without breaking binaries built against
an earlier one: the library reads that preamble, honors the fields the caller's
version defines, and defaults the rest.

**Custom values.** An application that needs something between the presets builds
a value by **clone-and-adjust**: start from a predefined profile, change the
fields it needs, and set the result. The stored value is the complete, resolved
value — not a base name plus overrides (which could silently change meaning if the
base profile were later redefined) — so an open file's policy never depends on a
mutable template.

```c
H5_policy_value_t policy = { .version = H5_POLICY_VERSION,
                            .struct_size = sizeof(policy) };
H5Pget_policy_profile_definition(H5_POLICY_LEGACY, &policy);
policy.allow_external_storage = 0;   /* deny external storage ... */
policy.allow_external_links   = 0;   /* ... and external links   */
H5Pset_policy_value(fapl, &policy);
```

**Setting and querying.** A policy is set either **by name** —
`H5Pset_policy_profile(fapl, H5_POLICY_STRICT)` — or **by value** —
`H5Pset_policy_value(fapl, &value)`. You never set `H5_POLICY_CUSTOM`; it is an
*output* only. Setting a value makes the policy custom, so
`H5Pget_policy_profile` then reports `H5_POLICY_CUSTOM` — **even if the value
matches a preset**, because the name records *how* the policy was set, not what it
equals. `H5Pget_policy_value` returns the effective fields. The profile name is
**informational**; enforcement is driven by the **value**, never the name.

### 3.4 Enforcement semantics

The policy snapshotted into the file's state at open (Section 3.2) is consulted
at the point each action would cross a trust boundary. This section says where that happens, when,
what a denial looks like, and how the policy composes with controls that already
exist.

**Where each action is gated.** Each inventoried action has a single enforcement
point — the site at which the library would perform the crossing — where it
consults the snapshot before proceeding:

| Action | Enforcement point | Checked when |
| --- | --- | --- |
| External storage | external-file-list read path | raw bytes would be read from an external file |
| Virtual dataset (VDS) | source-dataset open | a source file would be opened to satisfy a read |
| External link | link traversal | the link would be followed to open its target |
| Multi/family VFD | VFD member open | a member file would be opened |
| Dynamic filter plugin | filter pipeline / plugin loader | a non-core (dynamically loaded) filter would be loaded or invoked |
| VOL/VFD plugin | plugin loader | a VOL connector or VFD plugin would be loaded |

**The gate fires at the crossing, not on inspection.** Enforcement triggers when
the library would *perform* the action — open the external file, follow the link,
load the plugin — not when an application merely reads metadata that *describes*
it. Reading a dataset's shape, datatype, or filter list, or an external link's
stored target, is inspection and stays available under every profile; only the
crossing itself is gated. This keeps a denying profile compatible with safe
inspection (Section 3.5) and makes the denial deterministic — it occurs exactly
when, and only when, the boundary would be crossed.

**Path confinement (file-reference actions).** For the file-reference
family, a permitted action is additionally constrained in *where* it may resolve.
Confinement covers **local filesystem** references:

- an **allowed prefix** (application-supplied; `NULL` means unconfined) — the
  resolved target must lie under it;
- a **deny list** of always-refused paths, defaulting to `/proc`, `/sys`, and
  `/dev`, which the application may extend;
- the target is **canonicalized** — relative paths made absolute and `..`
  segments collapsed — so a reference cannot escape the prefix through `..`; and
- a confined reference **does not follow symbolic links**: a symlink in the path
  is refused. This removes the symlink-swap race by construction, and the
  reference is opened against the resolved, verified target rather than
  re-resolved from a path string.

Only the allowed prefix is the application's to set; the deny list,
canonicalization, and symlink refusal are library behavior. Three extensions are
**out of scope, left to Further considerations**: following symbolic links
race-safely, Windows-specific path rules (device names, UNC paths,
case-insensitivity), and object-store / non-POSIX namespaces.

**The plugin gate.** Denying a plugin takes more than refusing a fresh load,
because a non-core filter may already be registered or cached. The gate
therefore:

- identifies **core** filters by the library's own **built-in implementations**,
  not by filter ID or the mutable registration table, so a non-core filter
  cannot be disguised as core;
- checks the policy when the pipeline would **engage** a non-core filter for a
  read or write, again immediately **before the filter callback runs**, and
  **before any plugin search or load** — so a denial causes no filesystem
  search, no library load, and no plugin code to run; and
- keeps cached plugins identifiable by origin, so a denying file cannot reach
  **cached** external code through the registry.

**Composition with existing controls.** The policy composes with the library's
existing plugin controls as an **intersection**, never an override: the effective
permission is the policy *and* the H5PL loading-state mask *and*
`HDF5_PLUGIN_PRELOAD` *and* any build-time signature requirement. A policy can
only *tighten* an existing restriction, never relax it — in particular, no
profile can re-enable loading that `HDF5_PLUGIN_PRELOAD` has disabled.
(`HDF5_PLUGIN_PRELOAD` is the existing, coarse, process-global deny that this
per-file, per-action policy refines.)

**Failure is safe and visible.** A denied action fails with a **distinct,
documented error** — distinguishable from "file corrupt," "not found," or
"filter unavailable" — that identifies the action and the policy in force, so an
application can tell a policy denial from any other failure and point a user at
the opt-in. Evaluation is **fail-closed**: if the policy cannot be evaluated, the
action is denied. This is requirement 5.

**Propagation to files opened through a file.** When a permitted action opens
another file — an external link's target, a VDS source, a multi/family member —
the parent file's policy must flow into that child open, so trust cannot be
escaped in one hop. The enforcement sites above apply that propagation; the exact
mechanism — how the snapshot threads into an internally-initiated open — is
addressed in the implementation plan (Section 4). Where the application has also
set an external-link access FAPL, this RFC proposes that the parent's policy
govern the linked file and that the elink FAPL's own policy not alter it; letting
the elink FAPL *tighten* a linked file is a possible refinement (Further
considerations).

### 3.5 Detectability

**What it provides.** An application can ask, for a file or an object within it,
**whether reading it would cross a trust boundary — which action, and where —
without performing the crossing.** For a dataset: does it use external or virtual
storage, and at what path(s)? For a group or link: is there an external link, and
to what target? For the file: is it a multi/family container, and does a
pipeline use a non-core filter? Every answer is drawn from metadata alone — no
external file is opened and no plugin is loaded.

**It is inspection, so it works under any policy.** Because detection reads only
metadata — the same inspection §3.4 leaves ungated — it succeeds even under
`strict`, where the crossings themselves would be denied. This is what lets a
cautious application, or a security analyst, **examine an untrusted file and see
exactly where it would reach, without ever letting it reach there.** Detection
does not require a policy to be set.

**Representative shape** (names illustrative; the API shape is settled in
Section 3.6). The detectable facts are offered at two scopes — a
single object or the whole file — and two levels of detail — a full list of
crossings, or a lightweight tri-state summary:

| | Lightweight (tri-state) | Full (crossings + targets) |
| --- | --- | --- |
| Per-object | `H5Oget_crossing_status` | `H5Oget_crossings` |
| Per-file | `H5Fget_crossing_status` | `H5Fget_crossings` |

The **full** query reports each crossing an object (or the whole file) would make,
without performing any of them:

```c
/* report the trust-boundary crossings an object would trigger, triggering none */
H5_crossing_report_t report;
H5Oget_crossings(obj_id, &report);
/* report lists, per crossing: the action, and its target (a path or filter id) */
```

The **lightweight** check answers, as a tri-state, whether reading would cross a
boundary at all — `SELF_CONTAINED` (no crossing), `CROSSES_BOUNDARY` (at least
one), or `UNDETERMINED` (cannot classify) — for a single object
(`H5Oget_crossing_status`) or the whole file (`H5Fget_crossing_status`). It serves
the common "just tell me whether this is safe to read plainly" triage, in the
spirit of the tri-state detectability property raised in the h5py discussion
(requirement 6).

**A complement to enforcement, not a substitute.** Detectability lets an
application make an *informed* decision and supports inspection-only tools, but it
does not replace the gate: an application that merely *can* detect a crossing is
not protected unless it also *acts* on what it finds. Enforcement (deny by
default) protects the application that does nothing; detection serves the one that
chooses to look first. Detection *instead of* enforcement — "detect-only" — is
the weaker alternative set aside in requirement 6.

### 3.6 API shape: a dedicated interface vs. extending H5PL

The preceding subsections used illustrative names; this subsection settles the one
genuinely open structural question — **where the policy interface lives.** Two
options were considered.

**Option A — extend H5PL (the plugin layer).** Extending H5PL is the direction a
prior proposal took, and the choice the issue explicitly posed, so it is weighed
here. The approach adds the policy to the existing plugin module: a profile or
value set on a FAPL, snapshotted at open, consulted when a filter would load. Its
strength is reuse — it builds on the module that already owns plugin loading, the
mechanism is already worked out, and the change is additive. Its weakness is scope: the
policy also governs external storage, VDS, external links, and the multi/family
VFD — actions with no connection to plugin loading — so housing a library-wide
policy in the plugin module is a poor fit. The functions would carry an `H5PL`
prefix while governing things that are not plugins, and the plugin module would
hold a policy of which it uses only one part.

**Option B — a dedicated, library-wide policy interface (recommended).** Give the
policy its own interface: the property lives on the file access property list
(`H5Pset_policy_profile`, `H5Pset_policy_value`, and their getters), and the
detectability queries live on the object and file layers (`H5Oget_crossings`,
`H5Fget_crossing_status`, and the rest). This interface **owns** the policy value;
each subsystem **consumes** the part that bears on it — the external-storage, VDS,
external-link, and multi/family sites consume the file-reference controls, and the
plugin layer (H5PL) consumes the one plugin bit at its own chokepoint. The result
is honest naming, the right architectural home for a whole-file concern, a plugin
module left focused on plugins, and all six actions covered uniformly. The cost is
a new public surface to design and maintain.

**This RFC recommends Option B.** The deciding reason is scope: the policy is a
property of *the whole open file*, spanning actions across several subsystems —
storage, VDS, external links, the multi/family VFD, and plugins — not a
plugin-loading setting. Housing it in the plugin module would make the naming
misleading and leave the plugin layer holding controls it never uses. The prior
H5PL proposal reaches the same doubt in its own open questions, asking whether a
cross-module policy should sit in H5PL at all, or in a dedicated interface that
H5PL merely consumes from. The names used throughout Sections 3.2–3.5 are the
Option-B forms.

**Prior art, and what stays in place.** Two existing pieces inform this interface
and remain beneath it:

- The **prior H5PL policy-profile proposal** is the source of the reused
  mechanism — a policy value set on a FAPL and snapshotted into shared file state
  at open (Section 3.2). Under Option B the mechanism is kept; only its *home*
  moves from the plugin module to the dedicated interface.
- **`HDF5_PLUGIN_PRELOAD`** and **`H5PLset_loading_state`** are the existing,
  coarse, process-global plugin controls. They are unchanged: the new per-file
  policy composes with them as an intersection (Section 3.4) and can only tighten,
  never relax, what they allow. H5PL remains the enforcement site for the plugin
  bit; the dedicated interface decides *whether* that bit is set for a given file,
  and H5PL enforces it.

## 4. Implementation and test plan

### 4.1 Implementation approach

The design reduces to a thin seam over code paths the library already has. The
policy touches the library at three kinds of point, each an existing seam rather
than new infrastructure:

- **one declaration point** — the policy is set on the FAPL (Section 3.2), through
  the same property-list machinery that already carries driver and cache settings;
- **one snapshot point** — at `H5Fopen` / `H5Fcreate`, the resolved policy is
  copied into the file's shared state, where it is immutable for the file's
  lifetime (Section 3.2);
- **one consultation pattern** — at each action's chokepoint (the sites in the
  Section 3.4 table), the library reads that snapshot and allows or denies before
  proceeding.

Each of those points already exists in the library, which is why this is a
bounded change rather than a rewrite. The library itself performs every gated
action — it opens external files, follows links, opens VFD members, and loads
plugins through its own code — so enforcement is a check added at an existing
seam, not a new subsystem. The FAPL-property-plus-snapshot mechanism is a
well-established property-list pattern, and the prior H5PL proposal already worked
out snapshotting a policy value into shared file state and consulting it at the
filter site. Detectability (Section 3.5) reuses the metadata the library already
parses to understand a file, reporting it instead of acting on it. The subsections
that follow enumerate the concrete work (Section 4.2), sequence it (Section 4.3),
and set out how it is verified (Section 4.4).

### 4.2 Required implementation work

The change comprises the concrete pieces below. Most are additive and
self-contained; the two genuinely hard items — path confinement and trust
propagation — are noted as such and sequenced accordingly in Section 4.3.

1. **The dedicated API surface.** The profile enum and policy-value struct
   (Section 3.3), the FAPL property that carries them, the set/get functions (by
   name and by value), and the detectability queries (Section 3.5) — plus
   validation of a custom value, so a malformed value is rejected before any
   file I/O.
2. **Snapshot into shared file state.** At `H5Fopen` / `H5Fcreate`, copy the
   resolved policy into the file's shared state; make it immutable for the file's
   lifetime and reported by `H5Fget_access_plist` for audit. Every object opened
   from the file is governed by it; and because the snapshot persists in shared
   state and is consulted at the action site, an **asynchronous operation is
   governed when it runs — even if the call that queued it has already returned.**
   Apply the match-or-fail rule when the same file is opened more than once
   (Section 3.2).
3. **The per-action chokepoints.** Insert the "consult the snapshot, then allow
   or deny" check at each of the six action sites in the Section 3.4 table —
   external storage, VDS, external links, the multi/family VFD, dynamic filter
   plugins, and VOL/VFD plugins.
4. **Path confinement (file-reference family).** Canonicalize the target (`..`
   collapsed, made absolute), enforce the allowed prefix and the deny list, refuse
   symbolic links, and open the verified target race-safely (Section 3.4). The
   deferred extensions (following symlinks, Windows path rules, object-store
   namespaces) are out of scope here (Further considerations).
5. **The plugin gate.** Identify core filters by the library's own built-in
   implementations (not by filter ID or the registration table); keep cached
   plugins identifiable by origin; and gate at each point a non-core filter could
   be loaded or invoked (Section 3.4), so a denial runs no plugin code. This is the
   self-contained piece the prior H5PL proposal already works out.
6. **Trust propagation into internal opens.** Thread the snapshot into the files
   the library opens itself — external-link targets, VDS sources, multi/family
   members — deriving the child's policy by tightening from the parent and reusing
   the Section 3.2 match-or-fail rule on conflict. This is the load-bearing hard
   part: *every* internal-open site must propagate, and a missed site silently
   reopens the hole. Its interaction with the external-link access FAPL is as
   decided in Section 3.4 (the parent's policy governs).
7. **A distinct, fail-closed error.** Return a documented error for a policy
   denial — distinguishable from corruption, not-found, and filter-unavailable —
   that names the action and the policy in force; and deny if the policy cannot be
   evaluated (Section 3.4, requirement 5).
8. **Composition with existing plugin controls.** Compute the effective plugin
   permission as the intersection of the policy with `HDF5_PLUGIN_PRELOAD` and
   `H5PLset_loading_state`, so the policy can only tighten, never relax, what those
   already allow (Section 3.4).
9. **Detectability queries.** Implement the per-object and per-file, lightweight
   and full crossing queries (Section 3.5) over the metadata the library already
   parses, performing no crossing.

### 4.3 Phased delivery

The work in Section 4.2 need not land as a single change. It is delivered **one
action at a time**, each increment self-contained enough to design, review, test,
and ship on its own, and each adding exactly one new hard capability over the
last. (This is the delivery of the *controls*; moving a control's **default** from
allow toward deny is a separate, backward-compatibility concern — see Further
considerations.)

| Increment | Adds the control for | New hard capability introduced |
| --- | --- | --- |
| 1 | dynamic filter plugins | the end-to-end seam (FAPL → snapshot → chokepoint → error → composition) — no path confinement, no propagation |
| 2 | external storage | **path confinement** (first file-reference action); also closes the external-read exploit vector early |
| 3 | VDS, external links | **trust propagation** (these open other HDF5 files with their own crossings) |
| 4 | multi/family VFD, VOL/VFD plugins | completes the inventory |

Two considerations shape this order:

- the **plugin gate goes first** because it is self-contained — none of the hard
  parts apply, and the prior H5PL proposal already worked out its subtleties — so
  it proves the whole architecture (a *walking skeleton*) at low risk before the
  harder work begins; and
- **each later increment introduces one new hard capability and no more** —
  external storage adds path confinement (its target is raw data, so no
  propagation), and VDS and external links add propagation (their targets are HDF5
  files with their own crossings). Because external storage is the first of these,
  the demonstrated exploit vector (the Hugging Face external read of Section 1.1)
  is closed early — right after the mechanism is proven, rather than last.

Each increment ships with its control **available but not yet denied by default**
(the default-flip is a separate migration, Further considerations), together with
the tests that cover that action (Section 4.4) — so correctness is established per
increment, and the deny-by-default migration can later proceed action by action
over a proven mechanism.

### 4.4 Test plan

Correctness is established per increment (Section 4.3): each action's tests ship
with the increment that adds it. The suite covers:

- **Per-action enforcement fixtures.** For each inventoried action and each
  profile, a fixture asserts the crossing is **denied** under a denying policy and
  **allowed** under the matching opt-in. Specific cases include:
  - external storage pointing at `/etc/passwd` — denied under `strict`, read under
    `legacy`;
  - a reference escaping its allowed prefix via `..` or a symlink — denied by path
    confinement;
  - the one-hop-escape case — a restricted action moved into a linked, VDS, or
    member file is still denied (propagation);
  - the cached-plugin back-door — a denying file cannot reuse a plugin that an
    earlier file loaded;
  - a non-core filter — denied under a denying profile, loaded under an allowing
    one.
- **Positive (no-false-denial) tests.** Legitimate uses keep working where the
  policy allows them — external storage, VDS, external links, multi/family, and
  non-core filters all succeed under permissive and opt-in profiles.
- **Fail-safe tests.** A denial performs no filesystem search, file open, or
  plugin load; raises the distinct, documented error (Section 3.4); and the
  library denies when the policy cannot be evaluated (fail-closed).
- **Snapshot and lifetime tests.** The policy is fixed at open, inherited by
  objects and asynchronous work, reported by `H5Fget_access_plist`, and the
  match-or-fail rule fires when the same file is opened under conflicting policies
  (Section 3.2).
- **Detectability tests.** The crossing queries (Section 3.5) report the right
  crossings and tri-state without performing any crossing, and agree with what
  enforcement would do.
- **Composition tests.** The policy intersects correctly with
  `HDF5_PLUGIN_PRELOAD` and `H5PLset_loading_state` — a permissive profile cannot
  re-enable what those disable (Section 3.4).
- **Differential testing against libhdf5.** Compare policy-on with policy-off
  behavior, confirming the policy changes only authorization — a valid file's data
  is unchanged where allowed — and never relaxes corruption rejection.
- **Structure-aware fuzzing.** Mutate the gated metadata (external paths, link
  targets, filter IDs, driver info) to confirm the gates hold and fail safe on
  malformed input.
- **Independent oracle.** Cross-check verdicts against h5policy, which parses the
  same files independently of libhdf5 — both a feasibility check and a guard
  against the two drifting.

### 4.5 Documentation

Each new public function and type requires a **reference-manual entry**:

- **Policy types** — the profile enum (`H5_policy_profile_t`) and the policy value
  struct (`H5_policy_value_t`).
- **FAPL policy calls** — `H5Pset_policy_profile` / `H5Pget_policy_profile` (by
  name), `H5Pset_policy_value` / `H5Pget_policy_value` (by value), and
  `H5Pget_policy_profile_definition` (a predefined profile's definition).
- **Detectability queries** — `H5Oget_crossings` and `H5Fget_crossings` (full),
  and `H5Oget_crossing_status` and `H5Fget_crossing_status` (tri-state).
- **The policy-denial error** — the distinct, documented error a denied action
  raises (Section 3.4), so a caller can recognize and handle it.
- **The external-link interaction** — document that a policy set on an
  external-link access FAPL (`H5Pset_elink_fapl`) does **not** alter a linked
  file's policy; the parent's policy governs (Section 3.4). This is non-obvious —
  an application might expect its elink policy to take effect — so it must be
  called out.

Each entry gives the call's signature, parameters, return value, and the errors it
can raise.
