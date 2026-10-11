# V1 release acceptance — 2026-10-10

Status: **release candidate; clean-machine acceptance remains unverified**.
Prompts 1–44 are complete. Prompt 45 is not complete until the outstanding
Windows installation and network-isolation checks below have evidence.

| Check | Evidence / result |
| --- | --- |
| Statistical, service, UI, backup, privacy regression | 256 tests passed; `scripts/quality.py` also passed Ruff, formatting and strict Pyright |
| Independent statistical references | Golden fixtures in `tests/golden`, unit tests, SciPy BCa comparison |
| Deterministic workers | Spawned criterion processes; serial/process equality test including 10,000 BCa draws |
| Full-size benchmark | 59.7287 seconds; 10 criteria × 1,000 items × 10 raters; 940 results; 10,000 resamples; all recommended metrics |
| Benchmark timing | Full Execute service: workbook reload, validation, preflight, calculation, persistence; excludes initial upload and reports |
| Reference machine | Intel Core 7 150U, 10 cores/12 logical processors, 32 GB RAM, Windows 11 Pro 10.0.26200, Python 3.14.8; four analysis workers |
| Benchmark margin | One recorded passing run, only 0.27 seconds below limit; slower/busier machines may fail. Do not reduce metrics/resamples to pass |
| Source acceptance | Passed worker analysis, version, comparison, UI/drill-down, report privacy, backup, restore, restart |
| Final packaged acceptance | Passed the same workflow in the bundled EXE, including long-path restore; `docs/packaged-acceptance.json` |
| Long Windows paths | Extended native storage paths; restore regression verifies staging beyond the legacy MAX_PATH limit |
| Offline automated regression | Socket connect, create_connection and DNS calls blocked during service workflow; passed |
| PDF/DOCX visual review | Generated reports rendered and all final pages inspected; no clipping/orphaned chart heading in fixture |
| Installer | PyInstaller application bundle and Inno Setup EXE; build requires packaged acceptance before compiling installer |
| Clean Windows 11 installation | **UNVERIFIED** — Windows Sandbox executable is unavailable on this host |
| Networking disabled/firewall-blocked application | **UNVERIFIED** — Python socket denial is not OS network-isolation evidence |
| Uninstall retains permanent data | Installer excludes runtime data by construction; actual clean-machine uninstall check **UNVERIFIED** |

The benchmark result is preserved in `docs/benchmark-result.json`. The initial
array-gather baseline took 160.48 seconds for calculation only. Row multiplicity
reduction improved performance without changing the sampled rows. Implementation
details and numerical tie conventions are in `bootstrap_performance.md`.

## Repeatable commands

From a locked Python 3.14 development environment:

```powershell
.\.venv\Scripts\python.exe scripts/quality.py
.\.venv\Scripts\python.exe scripts/benchmark.py
.\scripts\build_windows.ps1
.\scripts\create_offline_sandbox.ps1
```

The build requires the portable Inno Setup compiler at `.tools/inno/ISCC.exe`.
It isolates PATH during dependency discovery and rejects a private ICU DLL,
preventing incompatible document-tool libraries from replacing Windows ICU.
It runs the bundled executable's isolated acceptance workflow before compilation.
The installer goes in `dist/installer`; it installs application binaries beneath
`%LOCALAPPDATA%\Programs\InterRaterAnalyzer`. Permanent data is separately located
at `%LOCALAPPDATA%\InterRaterAnalyzer`. The installer has no state-deletion entries.

On a Windows 11 host with Windows Sandbox available, open the generated
`runtime-data/offline-acceptance.wsb`. Its networking is explicitly disabled.
It maps the package read-only and an isolated evidence folder writable. The
sandbox script performs a clean install, runs the packaged acceptance workflow,
uninstalls, and verifies a permanent-data sentinel survives. Review
`acceptance.json`, `installation.json`, any `failure.txt`, and `dashboard.png`.
The script refuses to install/uninstall on the ordinary host account.

Do not mark release acceptance complete until this clean-machine run succeeds.
The candidate is unsigned; release signing has not been configured.

Build references: [PyInstaller usage](https://pyinstaller.org/en/stable/usage.html),
[Inno Setup portable compiler](https://jrsoftware.org/ishelp/topic_technotes.htm),
[Inno Setup uninstall deletion rules](https://jrsoftware.org/ishelp/topic_uninstalldeletesection.htm).
