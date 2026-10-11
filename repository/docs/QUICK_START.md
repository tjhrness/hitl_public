# Quick start — release candidate 0.1.0

## Install

Use Windows 11. Download the installer and its `.sha256` file from GitHub Releases. In PowerShell, calculate `Get-FileHash .\InterRaterAnalyzer-0.1.0-Setup.exe -Algorithm SHA256` and compare the hash with the checksum file. Install and launch the app. Python is bundled; Excel is only needed if you want to edit the workbooks with Excel.

This installer is unsigned. Clean-machine installation, OS-level offline execution and uninstall acceptance remain pending; see [release acceptance](release_acceptance.md).

## Run the synthetic demonstration

1. Download `examples/synthetic-mixed.xlsx`. Create a new analysis with a descriptive name, then import this workbook.
2. Confirm each worksheet's rating type: Binary, Nominal, Ordinal, and Continuous respectively.
3. For Ordinal, set the order **Low → Medium → High**. For Continuous, set practical agreement tolerance to **5** for this demonstration. These scores use arbitrary units; five is a demo setting, not a recommended organizational threshold.
4. Start with the application's recommended metrics and default priority settings. Review any warnings and acknowledge them where required. A warning or noncomputable metric needs review; it is not a software failure by itself.
5. Review the configuration and select **Execute**. Wait for completion, then explore the summary, criterion results, item disagreement, and reviewer comparisons.
6. Open Analysis History to revisit saved results or create a new version. Use the report export action when you need a report package.

Single-type examples follow the same steps with only their matching type. Synthetic examples contain imperfect agreement by design; no single target score is prescribed.

## Prepare your own workbook

Copy `examples/blank-template.xlsx`. It contains headers only and cannot be analyzed until you add complete ratings.

- Start the header row at row 1. The first visible column must be exactly `Item ID`.
- Use 2–10 reviewer columns whose headers begin with `Rater:`, followed by a unique reviewer identity. Replace the three placeholder reviewers as needed.
- Put one item per row and one criterion per worksheet. Use 1–10 visible criterion worksheets and 1–1,000 items per worksheet.
- Use unique, nonblank item IDs. Every criterion must have the same item ID set and the same reviewers in the same column order.
- Fill every rating cell. Do not use formulas, totals, merged headers, explanatory rows, or additional metadata columns in the rating table. Hidden rows/columns are excluded; keep intended data visible.
- For binary use two consistent labels; for nominal use unordered categories; for ordinal define category order in the application; for continuous enter numeric values and choose a tolerance in the same units.
- Save as `.xlsx`. Do not add an instructions worksheet: visible worksheets are interpreted as criteria.

Very small samples, constant ratings and highly imbalanced categories can limit interpretation or make some metrics unavailable. Use the findings displayed by the application to resolve data or configuration issues.

## Read the results

Raw agreement describes exact matches; chance-adjusted measures answer a different question and can behave differently when category frequencies are imbalanced. Continuous practical agreement depends on your tolerance. Correlation alone does not establish agreement. Read estimates alongside their uncertainty, sample size, warnings and disagreement patterns. Priorities depend on selected settings and are aids to review, not ground truth.

See [methods](statistical_methods.md) for implemented definitions and [priority formulas](priority_formulas.md) for the triage calculations.

## Data handling

The app stores original workbooks, identities and analyses locally under `%LOCALAPPDATA%\InterRaterAnalyzer`. These files remain sensitive even when result views use reviewer aliases. Backups are unencrypted and include original data; protect them as you would the source workbook. Restore replaces current application state after validation and confirmation; read [backup and restore](backup_restore.md).

Do not upload your runtime folder, workbooks, databases, backups, logs or organizational reports to a public repository. Review exported reports before sharing: reviewer aliases do not make the underlying organizational content public.

## Troubleshooting

- Import blocked: check exact headers, missing ratings, duplicate item IDs, reviewer order and visible worksheet count.
- Metric unavailable: read the specific computability finding; review category variation, sample size and metric settings.
- To report a problem, create a small synthetic reproducer and describe the settings. Do not send production data.
