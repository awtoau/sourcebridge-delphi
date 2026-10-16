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

The Stage-1 fixture extractor is operational, but this development environment
does not currently have Free Pascal (`fpc`) or a Delphi compiler installed.
Its facts are therefore parser-only evidence. No rule may claim a dialect,
overflow, ABI, or runtime behavior until a concrete compiler/version/target
variant compiles the fixture and records its result.

```text
sourcebridge-delphi-extract fixtures/scalars.pas
```

The command writes normalized JSON facts to standard output.
