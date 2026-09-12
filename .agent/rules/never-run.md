---
trigger: always_on
---

Never execute, launch, or run the application yourself. This is a GUI desktop app
(Flet), and some agent models will try to launch the full app or run heavyweight
processes (e.g. `python main.py`, `flet run`...) without asking first.

Running the app is always the user's job:

- Do not launch the GUI (or the CLI) to "see if it works".
- Do not run long/blocking commands, scripts that start services, or anything
  that spawns a window, server, or worker processes without permission.
- Do not use execution as a substitute for testing: reason through the change,
  review the diff, and let the user run and verify it themselves.
- If a smoke test really is required, ask the user first and only run something
  minimal and non-interactive.

When in doubt: make the change, tell the user how to run it, and stop.