# Validation

Run from the repository root. No tests operate on existing artist sessions.

```powershell
& 'C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe' tests\run_checks.py `
  --mayapy 'C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe' `
  --maya-gui 'C:\Program Files\Autodesk\Maya2026\bin\maya.exe'
```

Omit `--maya-gui` for native/batch checks only. Logs, fixture exports, clipboard
files, a disposable Maya profile, and GUI screenshots are written under the
ignored `tests/results/` directory.

The checks cover:

- The existing 11 Studio Renamer planner/transaction tests through its legacy import.
- 14 real-Maya bulk material tests, including assignments, connections and undo.
- Stand-in mode changes for shapes, multiple groups, all-scene scope and undo.
- Copy in one mayapy process; paste in separate processes, including different
  frame rates, name conflicts, hierarchy, shader and animation import, repeat
  paste, latest-paste undo and redo. Empty/component copies retain the previous clip.
- Import every menu target without opening windows or editing scene nodes.
- A separate Maya GUI starts with the repository as a `.mod` module and a test
  profile. Its automatic menu must exist before the test runs. It opens every
  tool window, checks scene nodes were preserved, rebuilds the menu twice and
  validates installation into a fixture directory. The two direct scene cleanup
  actions are registered but are not clicked in this UI check.

The GUI test closes only its own disposable Maya process. The copy and paste
checks likewise use isolated standalone processes and do not save artist scenes.
