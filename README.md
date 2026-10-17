# Sourcebridge Delphi frontend pack

This pack extracts Delphi source facts for Sourcebridge profiles. It does not
emit target-language code and does not claim compiler, dialect, or runtime
validation that it has not run.

## Stage-1 scope

The first supported fixture grammar extracts:

- a `unit` name;
- `function` signatures using `Integer` or `Cardinal` parameters and returns;
- a function body consisting of `Result := Left + Right`.

Unsupported syntax is a reported extraction error. The intentionally small
scope gives the Delphi Stage-1 pilot an executable fact boundary before
compiler integration and broader language support.

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
  `434`–`436`) and the next basics candidate `438`;
- `rule-curriculum.json` is the version-controlled `basics` selector
  curriculum, ordered from rule/test `437` to candidate rule/test `438`;
- `tools/run_sourcebridge_engine_test.py` is a `json-command` adapter. It
  checks the pinned FPC variant, compiles the Stage-1 fixture in Delphi mode,
  and invokes the existing extractor.

The adapter honors `SOURCEBRIDGE_FPC`, so the `sourcebridge-fpc` wrapper built
by `bootstrap-runtime` can be reused instead of the host `fpc`. With the
Sourcebridge core CLI available, run the one focused case as:

```text
sourcebridge dev sourcebridge-delphi test 437 \
  --database evidence/sourcebridge.db \
  --pack-manifest sourcebridge-delphi.pack.json
```

The expected structured result is source `passed`, extraction `passed`,
target `blocked`, and oracle `skipped`. This is a frontend smoke test only:
the pack does not invoke a target backend, does not compare generated target
behavior, and does not claim a general Delphi converter, Embarcadero Delphi
equivalence, or target equivalence.

The focused boolean candidate can be run with the same adapter:

```text
sourcebridge dev sourcebridge-delphi test 438 \
  --database evidence/sourcebridge.db \
  --pack-manifest sourcebridge-delphi.pack.json
```

It covers a Delphi-mode `Boolean` function using an integer comparison and
`if`/`else` result assignment. The extractor reports only this fixture fact;
it does not claim general Pascal control-flow support.
