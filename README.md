# FolderSync

A diff-first folder sync utility with a Tkinter GUI. Walk both trees, show you exactly what differs,
then copy only the deltas — after you've seen the list.

Single file, ~375 lines, **stdlib only**. No pip install.

## It never deletes anything

Worth stating plainly, because "sync" usually implies it. FolderSync only ever calls
`shutil.copy2`. A file in the destination that is absent from the source is left alone in one-way
mode, and *pulled back to the source* in two-way mode. There is no path through the code that
removes a file.

That is the whole reason it exists: `robocopy /MIR` and its equivalents mirror **deletions** too, so
a mistake in the source direction destroys the destination. This one can only ever add or overwrite.

## Running it

```bash
python folder_sync.py
```

Pick a source and a destination, choose a mode, hit **Scan**, read the list, then sync. There are no
command-line arguments — it's GUI-only by design, because the point is seeing the diff before
committing to it.

## The two modes

**Copy → (one-way)** proposes two kinds of operation:

| action | meaning |
|---|---|
| `missing` | in source, absent from destination |
| `newer` | in both, source modified more recently |

**Sync ↔ (two-way)** adds the mirror image, so changes made on either side come together:

| action | meaning |
|---|---|
| `pull_unique` | in destination, absent from source |
| `pull_newer` | in both, destination modified more recently |

## Two details that matter in practice

**Timestamps are compared with a 2-second tolerance** (`MTIME_THRESHOLD`). Filesystems disagree
about mtime precision — FAT32 stores 2-second granularity, and copies across filesystems or network
shares routinely land a fraction of a second off. An exact comparison reports thousands of
identical files as "newer" on every scan, which makes the diff useless.

**Windows reserved device names are skipped silently** — `nul`, `con`, `prn`, `aux`, `com1`–`com9`,
`lpt1`–`lpt9`. These cannot exist as real files on Windows, but they turn up in trees copied from
other systems, and touching one hangs or errors the walk.

Comparison is by **existence and modification time**, not by content hash. That is a deliberate
trade: hashing both trees costs a full read of every file, which on a large folder is the difference
between a scan that takes seconds and one that takes hours.

## Building a standalone executable

```bash
pyinstaller FolderSync.spec
```

Produces a windowed `FolderSync` executable (no console). If
[sun-valley.tcl](https://github.com/rdbende/Sun-Valley-ttk-theme) is present it is applied; if not,
the app falls back to the default ttk theme rather than failing.

## Repository layout

```
folder_sync.py     the whole application
FolderSync.spec    PyInstaller build spec
docs/superpowers/specs/2026-03-10-folder-sync-design.md
```

## Status

CI runs `python -m compileall` on 3.13 — a syntax gate. **There is no automated test suite**, so the
diff logic (`compute_diff`, `walk_tree`) is unverified by anything but use. That is the most
worthwhile thing to add: both are pure functions over dictionaries and would test cleanly without a
GUI.
