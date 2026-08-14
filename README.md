# Enable Chrome AI — Codex Plugin Marketplace

A Codex plugin that packages the field transformation from
[`lcandy2/enable-chrome-ai`](https://github.com/lcandy2/enable-chrome-ai) and
adds recoverable backups, atomic JSON writes, full-document write verification,
and selected-backup restore.

The plugin does not modify Chrome when installed. It first performs a read-only
check, and its skill requires explicit confirmation before applying or restoring
configuration.

## Install

Add this Git marketplace and install the plugin:

```bash
codex plugin marketplace add hugecheng/enable-chrome-ai-marketplace --ref main
codex plugin add enable-chrome-ai@enable-chrome-ai-marketplace
```

Start a new Codex task after installation so the plugin is loaded, then ask:

```text
Check whether Gemini eligibility is configured in my local Chrome.
```

## What it changes

The transformation intentionally follows the upstream `main.py` behavior:

- recursively changes existing `is_glic_eligible` entries to `true`;
- sets the root `variations_country` to `"us"`;
- when `variations_permanent_consistency_country` is already a list with at
  least two entries, updates its first entry to Chrome's `Last Version` and its
  second entry to `"us"`, preserving later entries.

The wrapper additionally:

- detects the Stable, Canary, Dev, and Beta paths used by upstream;
- closes the Chrome process set selected by upstream before a write;
- creates an owner-only backup before every actual write;
- writes through a temporary file in the same directory, flushes it, and uses
  an atomic replacement;
- reloads the result and verifies the complete JSON document;
- lists validated backups and restores only a selected backup from a recognized
  Chrome-channel backup directory;
- creates another safety backup before restore.

Backups are stored below each channel's user-data directory:

```text
Codex Backups/enable-chrome-ai/
```

## Important safety information

- Applying or restoring closes Chrome and may discard unsaved webpage forms,
  downloads, or other unfinished browser work.
- The script modifies Chrome's existing `Local State` file. Although it creates
  a backup and writes atomically, review the source and keep important profile
  data separately backed up.
- Run it as the same operating-system user that owns the Chrome profile. Do not
  run it with `sudo` or as an administrator unless that user owns the profile.
- Chrome or Google may rewrite these fields later. Do not loop the patch
  automatically; inspect the current state first.
- This only changes local eligibility/configuration fields. It cannot guarantee
  that Gemini appears: account type or age, organization policy, sign-in state,
  device region, product availability, and gradual rollout can still apply.
- This project is not affiliated with or endorsed by Google, Chromium, OpenAI,
  or the upstream project author. Use it at your own risk.

## Tested support

The packaged plugin has been exercised on:

- macOS 15.7.9 on Intel;
- Google Chrome Stable 151.0.7922.138;
- Python 3.14.3;
- Codex's local plugin marketplace flow.

The Windows and Linux user-data paths and the `psutil` process path come from
the upstream implementation, but this derivative has not been tested on real
Windows or Linux machines. Without `psutil`, a native process-management
fallback is available on macOS and Linux; Windows requires `psutil`.

Python 3.13 or later is recommended, matching the upstream project.

## Backups and restore

The normal Codex workflow asks for confirmation before both operations. For
development or auditing, the bundled script also exposes these commands:

```bash
python3 plugins/enable-chrome-ai/skills/enable-chrome-ai/scripts/chrome_ai_state.py check
python3 plugins/enable-chrome-ai/skills/enable-chrome-ai/scripts/chrome_ai_state.py apply
python3 plugins/enable-chrome-ai/skills/enable-chrome-ai/scripts/chrome_ai_state.py list-backups
python3 plugins/enable-chrome-ai/skills/enable-chrome-ai/scripts/chrome_ai_state.py restore --backup "/validated/backup/path"
```

Do not run `apply` or `restore` until unsaved browser work is closed.

## Development and validation

Run the isolated test suite without touching a real Chrome profile:

```bash
python3 -m unittest discover -s plugins/enable-chrome-ai/tests -v
```

The test suite compares the field transformation against the upstream
`main.py`, verifies array-tail preservation, exercises backup/apply/restore
round trips, checks owner-only backup permissions, and rejects backups outside
recognized channel directories.

## Attribution and license

This repository is a derivative of
[`lcandy2/enable-chrome-ai`](https://github.com/lcandy2/enable-chrome-ai),
originally researched and scripted by
[`lcandy2`](https://github.com/lcandy2). The upstream project is licensed under
the MIT License and requests credit for derivative works.

The upstream copyright notice and MIT permission notice are preserved in
[`LICENSE`](LICENSE). Additional attribution and a summary of modifications are
in [`NOTICE.md`](NOTICE.md).

## Reporting issues

When reporting a problem, do not upload your complete Chrome `Local State`,
profile, cookies, tokens, or backup files. Include only the Chrome version,
operating system, plugin version, command used, and redacted error message.
