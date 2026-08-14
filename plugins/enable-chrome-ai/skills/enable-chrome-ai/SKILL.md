---
name: enable-chrome-ai
description: Safely inspect, enable, verify, and restore Gemini in locally installed Google Chrome channels by applying the lcandy2/enable-chrome-ai main.py field transformations with backups and atomic writes. Use when Gemini or Ask Gemini disappears from Chrome, Chrome AI features are missing because the local variations country is unsupported, the user asks to apply the lcandy2/enable-chrome-ai method, or the user wants to check or restore a previous Chrome AI eligibility backup.
---

# Enable Chrome AI

Use the bundled script for deterministic checks and changes. It detects the same Stable, Canary, Dev, and Beta user-data paths as the upstream GitHub `main.py` on Windows, Linux, and macOS. Do not clear cookies, delete profiles, reset flags, install extensions, or change Google account/payment countries.

## Workflow

1. Run a read-only check from this skill directory:

   ```bash
   python3 scripts/chrome_ai_state.py check
   ```

2. Report each detected channel's Chrome version, country fields, Gemini eligibility counts, and whether a patch is needed. Do not expose unrelated profile contents.
3. If every channel reports `needs_patch: false`, do not patch again. Explain that an absent Gemini icon may instead be caused by sign-in, account age/type, organization policy, device region, or gradual rollout.
4. If a patch is needed, explain that all Chrome processes selected by the upstream script will close and restart and that unsaved webpage forms may be lost. Request explicit confirmation immediately before running the change.
5. After confirmation, run `apply` with the permissions required to write Chrome's user-data directory and restart Chrome:

   ```bash
   python3 scripts/chrome_ai_state.py apply
   ```

6. Wait a few seconds, then run `check` again. Treat `needs_patch: false` as configuration-level success because that value is calculated by previewing the exact upstream transformation. Do not claim the toolbar icon is visible unless it was visually verified.
7. Report every exact backup path returned by `apply`; a channel that needed no write returns `backup: null`.

## Backups and restore

List backups read-only:

```bash
python3 scripts/chrome_ai_state.py list-backups
```

Before restoring, show the user the exact selected backup. Explain that Chrome will close and its current `Local State` will be backed up before replacement. Request explicit confirmation immediately before restore.

Restore only a backup returned by `list-backups`:

```bash
python3 scripts/chrome_ai_state.py restore --backup "/absolute/path/from-list-backups"
```

Run `check` after restore and report the resulting fields.

## Interpretation

- `needs_patch` is derived by applying the upstream transformation to an in-memory copy and comparing it with the file. This includes the current `Last Version` value and the upstream handling of non-boolean `is_glic_eligible` values.
- As in upstream, `variations_permanent_consistency_country` is changed only when it already exists as a list with at least two entries; later entries are preserved.
- The script stores backups under each Chrome channel's `Codex Backups/enable-chrome-ai` directory. It sets mode `0600` on POSIX; on Windows, files inherit the Chrome user-data directory ACL.
- If Chrome or Google later rewrites the values, diagnose the current state before rerunning. Do not loop patches automatically.
- The field transformation and Chrome channel detection come from `https://github.com/lcandy2/enable-chrome-ai/blob/main/main.py`. The local wrapper adds backup validation, atomic writes, full-document write verification, restore support, and a command-line interface.
