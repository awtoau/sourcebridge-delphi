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

Run the platform-aware probe before provisioning:

```text
python3 tools/toolchain_report.py
```

On Fedora, install the initial open-source compiler with:

```text
tools/bootstrap_fedora_fpc.sh
```

The probe reports any detected `fpc`, `dcc32`, or `dcc64` compiler and records
the FPC version, target CPU, and target OS needed to pin a Sourcebridge variant.

Re-run the pinned source validation at any time:

```text
python3 tools/validate_fpc_fixture.py
```

The bounded scalar behavior observation confirms the selected variant's
`Integer` and `Cardinal` widths and non-overflow addition examples:

```text
python3 tools/validate_fpc_scalar_behavior.py
```

It does not establish overflow behavior.

The default-mode overflow observation is separate and must remain coupled to
the compiler options used by the validator:

```text
python3 tools/validate_fpc_overflow_behavior.py
```

Create source facts coupled to the pinned compiler variant for a target backend:

```text
python3 tools/extract_fpc_fixture.py
```

## Existing corpus discovery

The scalar fixtures are conformance canaries, not the rule-development corpus.
The primary Stage-1 corpus is the upstream Free Pascal compiler test suite,
checked out with only its `tests/` directory. Set `FPC_TEST_CORPUS` in a local
`.env` from [`.env.example`](.env.example) to that checkout.

Create the pinned test corpus plus its `rtl`/`packages` harness dependencies:

```text
bash tools/bootstrap_fpc_test_corpus.sh ../fpc-compiler-tests
```

Record its complete manifest before analysis:

```text
python3 tools/record_fpc_compiler_test_corpus.py \
  --output evidence/fpc-compiler-tests-manifest.json
```

The manifest scans every `.pas`, `.pp`, `.lpr`, and `.inc` source file below
that tree. Its compiler compatibility is measured through the upstream harness;
it is never inferred solely from a close version number.

After an upstream run, persist its digest summary:

```text
python3 tools/record_fpc_compiler_test_run.py \
  --manifest evidence/fpc-compiler-tests-manifest.json \
  --digest /path/to/fpc-digest.txt \
  --workers 32 \
  --output evidence/fpc-compiler-tests-quick-run.json
```

Turn the harness failure list into a triage queue before assigning language
work. Missing runtime/package units are setup dependencies, not converter gaps:

```text
python3 tools/build_fpc_corpus_triage_queue.py \
  --output-dir "$FPC_TEST_CORPUS/tests/output/x86_64-linux" \
  --output evidence/fpc-compiler-tests-triage.json
```

```text
sourcebridge-delphi-extract fixtures/scalars.pas
```

The command writes normalized JSON facts to standard output.
