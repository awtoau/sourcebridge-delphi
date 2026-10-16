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

Create source facts coupled to the pinned compiler variant for a target backend:

```text
python3 tools/extract_fpc_fixture.py
```

```text
sourcebridge-delphi-extract fixtures/scalars.pas
```

The command writes normalized JSON facts to standard output.
