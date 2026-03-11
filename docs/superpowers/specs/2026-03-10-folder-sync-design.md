# FolderSync — Design Spec

## Overview

A single-file Python/Tkinter utility for diffing and syncing two folders. Uses a diff-first approach: walk both directory trees, compare by existence and modification time, then copy only the deltas.

## UI Layout

- Source folder picker with Browse button
- Destination folder picker with Browse button
- Mode toggle: Copy → (one-way) or Sync ↔ (two-way)
- Scan button to analyze differences
- Results panel with expandable sections (missing, changed, unique-in-dest)
- Progress bar with status text
- Copy Now button to execute, Close button

## Workflow

1. Pick source and dest folders via native Windows file dialogs
2. Choose mode: Copy → (one-way) or Sync ↔ (two-way)
3. Click Scan — walks both trees, compares, shows summary
4. Review the diff in expandable treeviews
5. Click Copy Now — copies with progress bar
6. Summary shows total copied, total bytes

## Sync Logic

- Walk both trees into dicts: `{relative_path: (size, mtime)}`
- Silently skip Windows reserved device names (nul, con, prn, aux, com1-9, lpt1-9)
- Copy →: copy missing + newer-in-source files to dest
- Sync ↔: also copy unique-in-dest + newer-in-dest files back to source
- Conflict resolution: newer mtime wins (2-second threshold for filesystem precision)
- Uses shutil.copy2 to preserve timestamps

## Technical Details

- Single file: folder_sync.py
- Zero dependencies beyond Python stdlib (tkinter, shutil, os, pathlib)
- Scan and copy run in background threads to keep UI responsive
- Progress bar updates via tkinter's after() method
- No logging of skipped reserved files (silent skip)

## Decisions

- Tkinter over WinUI 3/XAML: reuses proven Python sync logic, zero dependencies, single file
- Newer-wins over ask-per-conflict: avoids tedious dialogs with many differences
- Silent skip over logged skip for reserved files: keeps UI clean
- Lives in Dropbox/Github/FolderSync: synced across machines, version controlled
