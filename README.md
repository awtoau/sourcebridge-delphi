# Sourcebridge Delphi frontend pack

This pack extracts bounded Delphi source facts and emits Rust only for the
explicitly supported Stage-1 function shapes. It records compiler outcomes
without claiming unsupported dialect, runtime, or equivalence behavior.

## Stage-1 scope

The first supported fixture grammar extracts:

- a `unit` name;
- `function` signatures using `Integer` or `Cardinal` parameters and returns;
- a function body consisting of `Result := Left + Right`.
- a Boolean comparison branch of the form `if Left <op> Right then Result :=
  True else Result := False`;
- the constrained `ScalarLayout` `program` fixture with literal
  `SizeOf(Integer/Cardinal)` and typed `1 + 2` output expressions.

The program extraction records expressions and source spans, not runtime byte
widths or output values. Unsupported syntax is a reported extraction error.
The intentionally small scope gives the Delphi Stage-1 pilot an executable
fact boundary before compiler integration and broader language support.

## Compiler validation status

The Stage-1 fixture extractor and source-side compiler baseline are
operational. The pinned initial variant is Free Pascal 3.2.3, x86_64 Linux,
using Delphi mode; it compiles `fixtures/scalars.pas` successfully.

This proves only that the fixture compiles in that concrete variant. No rule
may claim overflow behavior, ABI compatibility, runtime behavior, or
Embarcadero Delphi equivalence without further evidence.

## Verified development workflow

Use `dev.py` as the development entry point. It has a machine-readable command
registry and keeps corpus locations as explicit arguments rather than recording
local paths in committed evidence:

```text
python3 dev.py describe
python3 dev.py readiness
```

Bootstrap the pinned external compiler-test corpus only after reviewing its
dry-run plan. A successful bootstrap also records the whole-tree manifest at
`evidence/fpc-compiler-tests-manifest.json`; it records the upstream remote and
revision, never the local checkout path:

```text
python3 dev.py bootstrap-corpus \
  --corpus-dir ../fpc-compiler-tests \
  --dry-run
python3 dev.py bootstrap-corpus --corpus-dir ../fpc-compiler-tests
```

Build a compatible self-hosted compiler/runtime from that exact pinned
checkout before treating broader harness outcomes as compiler semantics. The
install directory is intentionally explicit and must be empty, so this cannot
replace the host compiler or reuse an unverified prior build:

```text
python3 dev.py bootstrap-runtime \
  --corpus-dir ../fpc-compiler-tests \
  --install-dir /path/to/fpc-runtime \
  --host-fpc /usr/bin/fpc \
  --dry-run
python3 dev.py bootstrap-runtime \
  --corpus-dir ../fpc-compiler-tests \
  --install-dir /path/to/fpc-runtime \
  --host-fpc /usr/bin/fpc
```

The bootstrap expands the pinned checkout's sparse paths only for upstream
`compiler` and `utils`, builds with the named host compiler, and confirms the
installed `/path/to/fpc-runtime/bin/sourcebridge-fpc`. That wrapper binds the
new compiler to the matching pinned RTL units; use it with `run-corpus --fpc`.
Do not overwrite the committed run evidence until the runtime bootstrap
succeeds.

Run the existing upstream harness, then create triage evidence. The output
status intentionally calls this *harness evidence*, never conversion evidence:

```text
python3 dev.py run-corpus --corpus-dir ../fpc-compiler-tests --dry-run
python3 dev.py run-corpus --corpus-dir ../fpc-compiler-tests
python3 dev.py triage-corpus --corpus-dir ../fpc-compiler-tests --dry-run
python3 dev.py triage-corpus --corpus-dir ../fpc-compiler-tests
```

`run-corpus` runs `make clean` before each full execution, as required by the
upstream suite. It uses the selected compiler for both upstream `TEST_FPC` and
the helper-tool `PP` contract. During investigation, direct the run and triage
JSON to ignored `tmp/` paths; replace committed evidence only after reviewing
the new result:

```text
python3 dev.py run-corpus --corpus-dir ../fpc-compiler-tests \
  --fpc /path/to/fpc-runtime/bin/fpc \
  --digest tmp/fpc-runtime-run.log \
  --output tmp/fpc-runtime-run.json
python3 dev.py triage-corpus --corpus-dir ../fpc-compiler-tests \
  --output tmp/fpc-runtime-triage.json
```

Pass `--fpc` with the selected compiler executable when using a self-hosted
environment. The harness command, recorded compiler identity, and evidence
target then refer to that same executable:

```text
python3 dev.py run-corpus --corpus-dir ../fpc-compiler-tests \
  --fpc /path/to/self-hosted/fpc
```

`harness_setup_failure` means the harness or its dependencies could not run.
`harness_evidence_recorded` and `harness_triage_recorded` record only upstream
compiler-test outcomes; they do not validate a conversion or justify a
converter rule. The triage queue keeps missing units, linker-environment
failures, observed compiler semantic differences, empty harness logs, and
harness metadata separate from general compiler diagnostics.

The scalar fixtures remain conformance canaries, not the rule-development
corpus. Re-run their focused validators directly:

```text
python3 tools/validate_fpc_fixture.py
python3 tools/validate_fpc_scalar_behavior.py
python3 tools/validate_fpc_overflow_behavior.py
python3 tools/extract_fpc_fixture.py
```

The extractor writes normalized JSON facts to standard output.

## Sourcebridge engine-test smoke path

This repository also contains the minimum Sourcebridge frontend-pack
integration:

- `sourcebridge-delphi.pack.json` declares the frontend and its engine-test
  catalogue;
- `engine-tests.json` owns stable test ID `437` (outside the known C# IDs
  `434`–`436`) plus the ordered basics cases `439`, `440`, `438`, and `441`;
- `rule-curriculum.json` is the version-controlled `basics` selector
  curriculum, ordered as addition `437`, integer layout `439`, Boolean
  comparison `440`, branch control flow `438`, and string length `441`;
- `tools/run_sourcebridge_engine_test.py` is a `json-command` adapter. It
  checks the pinned FPC variant, compiles the Stage-1 fixture in Delphi mode,
  extracts facts, emits bounded Rust, and compiles the Rust module.

The adapter honors `SOURCEBRIDGE_FPC`, so the `sourcebridge-fpc` wrapper built
by `bootstrap-runtime` can be reused instead of the host `fpc`. With the
Sourcebridge core CLI available, run the one focused case as:

```text
sourcebridge dev sourcebridge-delphi test 437 \
  --database evidence/sourcebridge.db \
  --pack-manifest sourcebridge-delphi.pack.json
```

For test `437`, the expected structured result is source `passed`, extraction
`passed`, target `passed`, and oracle `skipped`. The target result is a real
`rustc --crate-type lib` compile of generated code. The oracle remains skipped
because a unit-only fixture has no executable source/target harness to compare.
This does not claim a general Delphi converter, Embarcadero Delphi equivalence,
or target equivalence.

The focused boolean branch case can be run with the same adapter:

```text
sourcebridge dev sourcebridge-delphi test 438 \
  --database evidence/sourcebridge.db \
  --pack-manifest sourcebridge-delphi.pack.json
```

It covers a Delphi-mode `Boolean` function using an integer comparison and
`if`/`else` result assignment. It follows the same emitted-Rust and target
compile contract as test `437`; it does not claim general Pascal control-flow
support.

The Boolean-expression and string-length cases intentionally report extraction
`failed` because the current extractor does not support those primitives.
The integer-layout program reports extraction `passed` for its constrained
source expressions only; target remains `blocked`. Oracle remains `skipped`
for every basics case because no fixture currently has an executable
source/target comparison harness.

## Prototype engine-test inventory

Create a JSON inventory directly from the registered `engine-tests.json`
catalogue. The deterministic mode records each fixture's SHA-256 and runs the
existing structured adapter; if the adapter cannot run, its declared
catalogue outcome is retained and marked as such rather than being replaced
with an invented result:

```text
python3 tools/inventory_engine_tests.py \
  --catalogue engine-tests.json \
  --output inventory.json
```

The report includes source, extraction, target, and oracle statuses for every
registered test. It is deliberately read-only: the command does not modify
the catalogue, rules, or Sourcebridge core.

Optional local Ollama enrichment is explicitly supplemental and
non-authoritative. Supply the endpoint, model, and the user-provided model
digest together:

In a separate visible VS Code integrated terminal, start the operational
monitor first and leave it running while making optional inventory or proposal
runs:

```text
python3 tools/monitor_ollama.py \
  --endpoint http://localhost:11434 \
  --interval 5
```

It polls `/api/ps` and displays loaded model names, digests, sizes, and expiry
times. This is an operational monitor only; its output is not evidence,
validation, or a target-equivalence result.

Then run the optional enrichment:

```text
python3 tools/inventory_engine_tests.py \
  --ollama-endpoint http://localhost:11434 \
  --ollama-model delphi-planner \
  --ollama-digest sha256:... \
  --output inventory-with-notes.json
```

Each small fixture is sent with deterministic facts. The response must be
strict JSON containing `language_features`, `complexity_band`,
`prerequisites`, and `uncertainties`; the report retains the raw response,
model and model digest, and the rendered prompt and versioned template
digests. The prompt template is version-controlled at
`prompts/engine-test-inventory-v1.txt`; tune it through a new template file
and an explicit `--prompt-template-version`, then compare saved evidence
runs. Ollama notes cannot create or
change rules or catalogue entries and cannot claim target equivalence.
Without all three Ollama options, no network or model request is made.
If an optional Ollama request fails or returns invalid schema, the inventory
command exits non-zero and emits no success-shaped report. Deterministic-only
mode retains its no-network behavior.

To persist a supplemental run in the shared Sourcebridge evidence database,
write one importable record per fixture, import the engine-test catalogue into
that database, then import only the generated evidence directory:

```text
python3 tools/inventory_engine_tests.py \
  --ollama-endpoint http://localhost:11434 \
  --ollama-model qwen2.5-coder:7b \
  --ollama-digest <exact-local-digest> \
  --evidence-directory evidence/ollama-test-inventory

sourcebridge test import \
  --database evidence/sourcebridge.db \
  engine-tests.json
sourcebridge import-json \
  --database evidence/sourcebridge.db \
  --root evidence/ollama-test-inventory
```

The import verifies the fixture digest against the registered engine test and
stores the exact rendered prompt, template version/digest, model identity,
raw response, inventory annotation, and structured adapter statuses. These
records remain supplemental planning evidence, not rule or target validation.

Focused tests:

```text
python3 -m unittest discover -s tests -p 'test_inventory_engine_tests.py'
```

### Local FPC source-candidate queue

`tools/run_fpc_source_candidates.py` persistently queues attributed source
locations from the pinned `tmp/fpc` checkout. It prefers `tests/` and `rtl/`,
sends one local Ollama request per candidate, and cannot emit rules or claim
target validation. Supply the observed, exact digest for the local
`qwen3-coder:30b` model; it is intentionally never guessed:

```text
python3 tools/run_fpc_source_candidates.py \
  --model-digest sha256:<exact-qwen3-coder-30b-digest> \
  --limit 1
```

The smoke default is one candidate and the maximum is 100. Durable queue state
and content-addressed request/response transcripts are written below
`evidence/` by default. The runner accepts only HTTP loopback Ollama endpoints.
