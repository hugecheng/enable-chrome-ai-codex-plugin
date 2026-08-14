# Attribution and modifications

This project includes a derivative of the field transformation and Chrome
channel-detection logic from:

- Project: `lcandy2/enable-chrome-ai`
- Source: <https://github.com/lcandy2/enable-chrome-ai>
- Original author attribution: citron / lcandy2
- Upstream license: MIT
- Upstream `main.py` blob used as the behavior baseline:
  `332e6c2f27331cddb0323ffe5b177d2e219a319d`

The derivative wrapper adds:

- Codex plugin and marketplace packaging;
- a read-only inspection command;
- validated, owner-only backups;
- atomic JSON replacement with file and directory synchronization;
- complete-document write verification;
- validated backup listing and selected-backup restore;
- a safety backup before restore;
- isolated behavioral and recovery tests;
- a macOS/Linux process-management fallback when `psutil` is unavailable.

The upstream transformation conditions are intentionally preserved and tested
against the original `main.py` implementation.

The Codex plugin wrapper and distribution packaging are maintained by
[`hugecheng`](https://github.com/hugecheng).

This project is not affiliated with or endorsed by Google, Chromium, OpenAI,
or the upstream project author.
