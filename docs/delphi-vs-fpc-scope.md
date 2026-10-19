# Scope: this pack uses Free Pascal (FPC), not Embarcadero Delphi

This is the honest statement of what "Delphi" means in this pack today, and the
lawful path to grounding real Embarcadero Delphi.

## What is actually used here

| Layer | Reality |
|---|---|
| Source compiler | **Free Pascal (FPC) 3.2.3**, invoked with `-Mdelphi` |
| Mode `-Mdelphi` | FPC's **Delphi-compatibility mode** — accepts Delphi-style syntax, but implements **FPC** semantics, which differ from Embarcadero Delphi in real ways (strings/RTL, runtime details, generics, etc.) |
| Parser | FPC's own `fcl-passrc` (see `tools/pasfacts.pas`) |
| Corpus | the **Free Pascal** compiler test suite (not Delphi code) |
| RTL | **Free Pascal** RTL |
| Embarcadero `dcc` compiler | **not present** |

`-Mdelphi` is *not* the Delphi compiler. FPC is the free Object Pascal
reference implementation; Embarcadero Delphi is a separate, commercial product.

## What this does and does not establish

- It **does** establish that bounded Object Pascal fixtures compile with FPC in
  Delphi mode and that generated Rust reproduces the **FPC** observable output
  (the oracle compares FPC vs Rust).
- It **does not** establish Embarcadero Delphi parsing, semantics, RTL
  behavior, or equivalence. No rule may claim Delphi (Embarcadero) equivalence
  on this evidence.

So the accurate description of the current system is an **Object Pascal / Free
Pascal → Rust** pipeline. The `delphi` label is a compatibility aspiration, not
proven Embarcadero Delphi support.

## The lawful path to real Delphi grounding

Getting a working Embarcadero Delphi compiler is an interactive, licensed
setup rather than an automatic download:

- The free edition (Delphi Community Edition) is obtained by registering an
  Embarcadero account and signing in to the CE licence, and it ships as a
  Windows installer.

`wine64` is available in this environment, so a licensed Delphi command-line
compiler (`dcc64.exe`) can run here. To ground real Delphi:

1. Install a licensed Delphi (e.g. Community Edition you are entitled to use)
   and locate `dcc64.exe`.
2. Make it available to the pack and run it (via Wine) as the **source**
   compiler and the source side of the oracle, alongside the existing Rust
   target.
3. Only then may a profile claim Embarcadero Delphi — proven by a real
   Delphi-vs-Rust differential oracle, not FPC.

Until a licensed `dcc64` is provided, this pack is honestly an FPC / Object
Pascal pack, and claims are scoped accordingly.

## Status of the licensed Delphi asset

A licensed installer **is** present at
`../sourcebridge/assets/delphi/7c1ba2_RADStudio_13_CE.exe` (RAD Studio 13
Community Edition, InnoSetup, 314 MB). It bundles the Delphi compiler **engine**
(`app/bin/dcc32370.dll`, `app/bin64/dcc64370.dll`), the IDE (`bds.exe`),
resource/link tools, and the RTL `.dcu` libraries.

It does **not** yet give a headless compiler, for two reasons:

1. **No `dcc64.exe`/`dcc32.exe` command-line driver is bundled** — only the
   compiler DLLs. `GetItCmd.exe` is present, i.e. this is a feature installer
   that downloads the command-line compiler during installation.
2. **License activation is required** (`LicenseManager.exe`/`bdsreg.exe`): the
   compiler needs an activated Community Edition license (Embarcadero account,
   online activation) before it will run.

So the engine is here, but producing a working `dcc64` is done by running the
installer once and signing in to the Community Edition licence (GetIt provisions
the command-line compiler). This is a normal interactive setup, best done on
Windows.

To enable real Delphi grounding: run the installer once with your CE license to
provision `dcc64.exe` (e.g. under `…/Embarcadero/Studio/23.0/bin`), then make
that path available (`SOURCEBRIDGE_DELPHI_DCC`). The adapter can then run it via
Wine as the real Delphi source compiler and oracle source side.
