# Inter-Rater Variability Analyzer

**Version 0.1.0 — RELEASE CANDIDATE.** An offline, single-user Windows 11 desktop application for exploring how consistently reviewers rate the same items.

Use it to compare categorical judgments or numerical scores, identify disagreement, and plan reviewer calibration. Agreement measures describe consistency; they do not establish whether ratings are correct.

## Try it

1. Download `InterRaterAnalyzer-0.1.0-Setup.exe` from this repository's GitHub Releases page. Python is not required for the installer.
2. Install and launch the application. This release is unsigned; Windows may display a publisher warning. Follow your organization's software approval process.
3. Download [synthetic-mixed.xlsx](examples/synthetic-mixed.xlsx).
4. Follow the [quick-start guide](docs/QUICK_START.md) to import it, select rating types, and run an analysis.

The application runs locally and is designed for offline use. Installation files and saved analyses are separate. See [data handling](docs/QUICK_START.md#data-handling).

## Included workbooks

All examples are generated, fictional data: 60 items, three reviewers, and intentionally varied agreement. They are demonstrations, not organizational records or statistical reference fixtures.

| Workbook | Use |
|---|---|
| [Blank template](examples/blank-template.xlsx) | Header-only starting point; fill it before importing. |
| [Binary](examples/synthetic-binary.xlsx) | Yes / No decisions. |
| [Nominal](examples/synthetic-nominal.xlsx) | Unordered Category A / B / C labels. |
| [Ordinal](examples/synthetic-ordinal.xlsx) | Low / Medium / High judgments. |
| [Continuous](examples/synthetic-continuous.xlsx) | Numerical scores in arbitrary units. |
| [Mixed](examples/synthetic-mixed.xlsx) | All four types in separate worksheets. |

## What you can explore

Categorical agreement, Cohen and Fleiss kappa, Krippendorff alpha, and Gwet AC1/AC2; continuous agreement, error measures, Lin concordance, ICC and Bland–Altman comparisons. Availability depends on rating type and computability. Results include item and reviewer diagnostics, uncertainty estimates, saved analysis versions, and report exports.

Read [statistical methods](docs/statistical_methods.md) and [priority formulas](docs/priority_formulas.md) before interpreting results. Continuous tolerance and ordinal order must reflect your actual rating process.

## Release candidate limitations

Local automated checks passed with 256 tests, lint, formatting and strict type checking. Packaged application checks passed. Clean-machine Windows 11 installation, OS-level network-disabled execution, and uninstall retention acceptance remain unverified. The installer is unsigned. See the [release acceptance checklist](docs/release_acceptance.md). This is a trial release, not a production-approved release.

## Run from source

Install Python 3.14.x and uv, then run in the repository directory:

```powershell
uv sync --locked
.\.venv\Scripts\python.exe -m inter_rater_analyzer
```

Development setup requires downloading dependencies. To check the code:

```powershell
.\.venv\Scripts\python.exe scripts/quality.py
```

The Windows build procedure is in `scripts/build_windows.ps1` and the release checklist. Developer build tools are not included in this repository.

## Licensing and feedback

A project license has not yet been selected. Public availability alone does not grant an open-source license. The owner should add a license and review third-party redistribution notices before publishing. No license grant is implied by this package.

For feedback, describe the app version, rating type, settings, and steps to reproduce. Use synthetic data; do not attach organizational workbooks, database files, backups or identifiable reports.
