# Backup and restore

Use Backup History to create a permanent manual backup or select an `.irabackup`
file for restoration. Archives are unencrypted: they include internal rater mappings
and source workbooks. They are local recovery artifacts, not anonymized reports.
There is no application action to edit, delete, or export them.

Format 1 is a ZIP containing `manifest.json`, a consistent SQLite snapshot,
and every workbook/report referenced by that snapshot. The database contains
analyses, drafts, settings, immutable presets, identities, results, and audit state.
The manifest records the exact application version, UTC timestamp, backup type,
and SHA-256 for every state file. Temporary files and prior backups are excluded
to avoid recursive archive growth. Existing permanent backup history is retained
separately when analysis state is replaced; analysis records are never merged.
Archive validation currently limits a single snapshot to 8 GiB uncompressed;
larger snapshots fail safely rather than producing an incomplete backup.

Restore checks archive paths, duplicates, required files, app/schema compatibility,
checksums, SQLite integrity, foreign keys, and referenced artifacts before changing
active state. It creates a permanent Pre-Restore safety backup before the explicit
replacement confirmation. Cancellation retains that safety backup. A changed state
invalidates an earlier confirmation plan. UI maintenance operations prevent other
analysis/report actions while a backup or restore is running.

Validated state is staged beside the runtime root on the same volume. Directory
renames replace the complete state, with rollback on failure. A recovery journal
allows startup to recover a process/power interruption between renames before
opening the database. Backup and restore work runs outside the Qt UI thread.
