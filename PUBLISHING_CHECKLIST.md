# Publishing checklist

This folder is a staging package, not a published GitHub repository.

1. Review `repository/` and choose a project license. Add LICENSE and appropriate third-party redistribution notices before public publication. No license was selected on the owner's behalf.
2. Complete the pending checks in `repository/docs/release_acceptance.md` or disclose them as pending. Keep the release candidate and unsigned-installer labels.
3. Upload the contents of `repository/` to the GitHub repository root. Do not upload the original workspace wholesale.
4. Create a GitHub prerelease for version 0.1.0; attach the two files in `release-assets/`. Suggested title: `0.1.0 — Release candidate`.
5. Include the release-candidate limitations in release notes. Link the README, quick-start guide and mixed example from the LinkedIn post.
6. Check the download and walkthrough from another Windows 11 machine.

Only allowlisted application source, tests, build scripts, selected documentation, newly generated synthetic workbooks and the existing installer are staged. Runtime folders, databases, backups, actual rating workbooks, organizational reports, logs, developer caches, original prompt documents and unrelated projects are excluded.

SHA256SUMS.txt records the staged file hashes. PACKAGE_VERIFICATION.json records the package checks; hashes verify integrity, not software safety or clean-machine acceptance.
