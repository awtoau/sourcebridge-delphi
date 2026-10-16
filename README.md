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

Run the existing upstream harness, then create triage evidence. The output
status intentionally calls this *harness evidence*, never conversion evidence:

```text
python3 dev.py run-corpus --corpus-dir ../fpc-compiler-tests --dry-run
python3 dev.py run-corpus --corpus-dir ../fpc-compiler-tests
python3 dev.py triage-corpus --corpus-dir ../fpc-compiler-tests --dry-run
python3 dev.py triage-corpus --corpus-dir ../fpc-compiler-tests
```

`harness_setup_failure` means the harness or its dependencies could not run.
`harness_evidence_recorded` and `harness_triage_recorded` record only upstream
compiler-test outcomes; they do not validate a conversion or justify a
converter rule. The triage queue keeps missing units and missing harness logs
separate from compiler diagnostics.

The scalar fixtures remain conformance canaries, not the rule-development
corpus. Re-run their focused validators directly:

```text
python3 tools/validate_fpc_fixture.py
python3 tools/validate_fpc_scalar_behavior.py
python3 tools/validate_fpc_overflow_behavior.py
python3 tools/extract_fpc_fixture.py
```

The extractor writes normalized JSON facts to standard output.
