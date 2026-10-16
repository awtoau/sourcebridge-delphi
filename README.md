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

The Stage-1 fixture extractor is operational, but the current Fedora 44
development environment does not have Free Pascal (`fpc`) or a Delphi compiler
installed. Its facts are therefore parser-only evidence. No rule may claim a
dialect, overflow, ABI, or runtime behavior until a concrete
compiler/version/target variant compiles the fixture and records its result.

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

```text
sourcebridge-delphi-extract fixtures/scalars.pas
```

The command writes normalized JSON facts to standard output.
