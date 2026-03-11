"""FolderSync — Diff-first folder sync utility with Tkinter GUI."""

import os
import shutil
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

# Windows reserved device names to silently skip
RESERVED_NAMES = frozenset(
    {
        "nul",
        "con",
        "prn",
        "aux",
        *(f"com{i}" for i in range(1, 10)),
        *(f"lpt{i}" for i in range(1, 10)),
    }
)

MTIME_THRESHOLD = 2.0  # seconds — filesystem timestamp precision


def is_reserved(name: str) -> bool:
    stem = name.split(".")[0].lower()
    return stem in RESERVED_NAMES


def walk_tree(root: Path) -> dict:
    """Walk directory tree into {relative_path_str: (size, mtime, full_path)}."""
    entries = {}
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            if is_reserved(f):
                continue
            full = Path(dirpath) / f
            try:
                st = full.stat()
                rel = str(full.relative_to(root))
                entries[rel] = (st.st_size, st.st_mtime, full)
            except OSError:
                pass
    return entries


def compute_diff(src_tree, dst_tree, two_way=False):
    """Compute file operations needed.

    Returns list of (rel_path, action, src_path, dst_path, size) tuples.
    Actions: 'missing', 'newer', 'pull_unique', 'pull_newer'
    """
    ops = []

    for rel, (size, mtime, full) in src_tree.items():
        if rel not in dst_tree:
            ops.append((rel, "missing", full, None, size))
        else:
            dst_size, dst_mtime, _ = dst_tree[rel]
            if mtime - dst_mtime > MTIME_THRESHOLD:
                ops.append((rel, "newer", full, None, size))

    if two_way:
        for rel, (size, mtime, full) in dst_tree.items():
            if rel not in src_tree:
                ops.append((rel, "pull_unique", full, None, size))
            else:
                src_size, src_mtime, _ = src_tree[rel]
                if mtime - src_mtime > MTIME_THRESHOLD:
                    ops.append((rel, "pull_newer", full, None, size))

    return ops


def format_size(nbytes: int) -> str:
    if nbytes < 1024:
        return f"{nbytes} B"
    elif nbytes < 1024 * 1024:
        return f"{nbytes / 1024:.1f} KB"
    elif nbytes < 1024 * 1024 * 1024:
        return f"{nbytes / (1024 * 1024):.1f} MB"
    else:
        return f"{nbytes / (1024 * 1024 * 1024):.1f} GB"


class FolderSyncApp:
    def __init__(self, root):
        self.root = root
        self.root.title("FolderSync")
        self.root.geometry("720x600")
        self.root.minsize(600, 500)

        self.src_tree = {}
        self.dst_tree = {}
        self.ops = []
        self.working = False

        self._build_ui()

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # --- Folder pickers ---
        folder_frame = ttk.LabelFrame(main, text="Folders", padding=8)
        folder_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(folder_frame, text="Source:").grid(
            row=0, column=0, sticky=tk.W, pady=2
        )
        self.src_var = tk.StringVar()
        ttk.Entry(folder_frame, textvariable=self.src_var, width=60).grid(
            row=0, column=1, padx=4, pady=2, sticky=tk.EW
        )
        ttk.Button(
            folder_frame, text="Browse", command=lambda: self._browse(self.src_var)
        ).grid(row=0, column=2, pady=2)

        ttk.Label(folder_frame, text="Dest:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.dst_var = tk.StringVar()
        ttk.Entry(folder_frame, textvariable=self.dst_var, width=60).grid(
            row=1, column=1, padx=4, pady=2, sticky=tk.EW
        )
        ttk.Button(
            folder_frame, text="Browse", command=lambda: self._browse(self.dst_var)
        ).grid(row=1, column=2, pady=2)

        folder_frame.columnconfigure(1, weight=1)

        # --- Mode selector ---
        mode_frame = ttk.LabelFrame(main, text="Mode", padding=8)
        mode_frame.pack(fill=tk.X, pady=(0, 8))

        self.mode_var = tk.StringVar(value="oneway")
        ttk.Radiobutton(
            mode_frame,
            text="Copy  \u2192  (Source to Dest)",
            variable=self.mode_var,
            value="oneway",
        ).pack(side=tk.LEFT, padx=(0, 20))
        ttk.Radiobutton(
            mode_frame,
            text="Sync  \u2194  (Two-way)",
            variable=self.mode_var,
            value="twoway",
        ).pack(side=tk.LEFT)

        # --- Scan button ---
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(0, 8))
        self.scan_btn = ttk.Button(btn_frame, text="Scan", command=self._on_scan)
        self.scan_btn.pack(side=tk.LEFT)

        # --- Results treeview ---
        results_frame = ttk.LabelFrame(main, text="Results", padding=8)
        results_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        self.tree = ttk.Treeview(
            results_frame,
            columns=("size", "action"),
            show="tree headings",
            selectmode="none",
        )
        self.tree.heading("#0", text="File", anchor=tk.W)
        self.tree.heading("size", text="Size", anchor=tk.E)
        self.tree.heading("action", text="Action", anchor=tk.W)
        self.tree.column("#0", width=400, stretch=True)
        self.tree.column("size", width=80, stretch=False, anchor=tk.E)
        self.tree.column("action", width=120, stretch=False)

        scrollbar = ttk.Scrollbar(
            results_frame, orient=tk.VERTICAL, command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Progress bar ---
        progress_frame = ttk.Frame(main)
        progress_frame.pack(fill=tk.X, pady=(0, 8))

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            progress_frame, variable=self.progress_var, maximum=100
        )
        self.progress_bar.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 8))

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(
            progress_frame, textvariable=self.status_var, width=30, anchor=tk.W
        ).pack(side=tk.LEFT)

        # --- Bottom buttons ---
        bottom_frame = ttk.Frame(main)
        bottom_frame.pack(fill=tk.X)

        self.copy_btn = ttk.Button(
            bottom_frame, text="Copy Now", command=self._on_copy, state=tk.DISABLED
        )
        self.copy_btn.pack(side=tk.LEFT)

        ttk.Button(bottom_frame, text="Close", command=self.root.quit).pack(
            side=tk.RIGHT
        )

    def _browse(self, var):
        path = filedialog.askdirectory(initialdir=var.get() or str(Path.home()))
        if path:
            var.set(path)

    def _validate_paths(self):
        src = self.src_var.get().strip()
        dst = self.dst_var.get().strip()
        if not src or not dst:
            messagebox.showwarning(
                "FolderSync", "Please select both source and destination folders."
            )
            return None, None
        if not Path(src).is_dir():
            messagebox.showwarning("FolderSync", f"Source folder not found:\n{src}")
            return None, None
        if not Path(dst).is_dir():
            messagebox.showwarning(
                "FolderSync", f"Destination folder not found:\n{dst}"
            )
            return None, None
        return Path(src), Path(dst)

    def _set_working(self, working: bool):
        self.working = working
        state = tk.DISABLED if working else tk.NORMAL
        self.scan_btn.configure(state=state)
        if not working and self.ops:
            self.copy_btn.configure(state=tk.NORMAL)
        elif working:
            self.copy_btn.configure(state=tk.DISABLED)

    # --- Scan ---

    def _on_scan(self):
        src, dst = self._validate_paths()
        if not src:
            return
        self._set_working(True)
        self.status_var.set("Scanning...")
        self.progress_var.set(0)
        self.tree.delete(*self.tree.get_children())
        self.ops = []

        threading.Thread(target=self._scan_worker, args=(src, dst), daemon=True).start()

    def _scan_worker(self, src, dst):
        self.src_tree = walk_tree(src)
        self.dst_tree = walk_tree(dst)
        two_way = self.mode_var.get() == "twoway"
        self.ops = compute_diff(self.src_tree, self.dst_tree, two_way=two_way)
        self.root.after(0, self._scan_done)

    def _scan_done(self):
        self._set_working(False)

        # Group operations by action
        groups = {}
        for rel, action, src_path, dst_path, size in self.ops:
            groups.setdefault(action, []).append((rel, size))

        action_labels = {
            "missing": "Missing in dest",
            "newer": "Newer in source",
            "pull_unique": "Unique in dest",
            "pull_newer": "Newer in dest",
        }

        total_files = len(self.ops)
        total_bytes = sum(op[4] for op in self.ops)

        for action, label in action_labels.items():
            items = groups.get(action, [])
            if not items:
                continue
            group_bytes = sum(s for _, s in items)
            parent = self.tree.insert(
                "",
                tk.END,
                text=f"{label}  ({len(items)} files, {format_size(group_bytes)})",
                values=("", ""),
                open=False,
            )
            for rel, size in sorted(items):
                self.tree.insert(
                    parent, tk.END, text=rel, values=(format_size(size), label)
                )

        if total_files == 0:
            self.status_var.set("Folders are in sync!")
            self.copy_btn.configure(state=tk.DISABLED)
        else:
            self.status_var.set(
                f"Found {total_files} files ({format_size(total_bytes)}) to sync"
            )

        self.progress_var.set(100)

    # --- Copy ---

    def _on_copy(self):
        if not self.ops:
            return
        self._set_working(True)
        self.status_var.set("Copying...")
        self.progress_var.set(0)

        threading.Thread(target=self._copy_worker, daemon=True).start()

    def _copy_worker(self):
        src_root = Path(self.src_var.get().strip())
        dst_root = Path(self.dst_var.get().strip())
        total = len(self.ops)
        copied = 0
        copied_bytes = 0
        errors = 0

        for i, (rel, action, src_path, _, size) in enumerate(self.ops):
            try:
                if action in ("missing", "newer"):
                    target = dst_root / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src_path), str(target))
                elif action in ("pull_unique", "pull_newer"):
                    target = src_root / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src_path), str(target))
                copied += 1
                copied_bytes += size
            except Exception:
                errors += 1

            if i % 50 == 0 or i == total - 1:
                pct = ((i + 1) / total) * 100
                self.root.after(
                    0, self._update_progress, pct, f"Copying {i + 1}/{total}..."
                )

        self.root.after(0, self._copy_done, copied, copied_bytes, errors)

    def _update_progress(self, pct, msg):
        self.progress_var.set(pct)
        self.status_var.set(msg)

    def _copy_done(self, copied, copied_bytes, errors):
        self._set_working(False)
        self.progress_var.set(100)
        self.ops = []
        self.copy_btn.configure(state=tk.DISABLED)

        msg = f"Done! Copied {copied} files ({format_size(copied_bytes)})"
        if errors:
            msg += f", {errors} errors"
        self.status_var.set(msg)
        messagebox.showinfo("FolderSync", msg)


def main():
    root = tk.Tk()
    try:
        root.tk.call("source", "sun-valley.tcl")
        root.tk.call("set_theme", "light")
    except tk.TclError:
        pass  # sv_ttk theme not installed, use default
    FolderSyncApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
