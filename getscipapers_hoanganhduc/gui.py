"""Lightweight Tkinter GUI wrapper around the ``getpapers`` CLI.

This module provides a simple cross-platform window for triggering common
search and download workflows without remembering all command-line options.
It wraps the existing asynchronous CLI so behavior matches terminal usage
on both Windows and Linux.
"""

from __future__ import annotations

import asyncio
import io
import threading
import tkinter as tk
from contextlib import redirect_stdout, redirect_stderr
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .getpapers import main as getpapers_main
from .getpapers import DB_CHOICES, DEFAULT_DOWNLOAD_FOLDER
from .getpapers import DOWNLOAD_TIMEOUT
from .__name__ import __version__


def _append_output(widget: tk.Text, text: str) -> None:
    widget.configure(state="normal")
    widget.insert(tk.END, text)
    widget.see(tk.END)
    widget.configure(state="disabled")


def _run_getpapers_async(argv: list[str], widget: tk.Text) -> None:
    """Execute the async ``getpapers`` entry point on a background thread."""

    def _target() -> None:
        buffer = io.StringIO()
        try:
            with redirect_stdout(buffer), redirect_stderr(buffer):
                asyncio.run(getpapers_main(argv))
        except Exception as exc:  # pragma: no cover - UI safety net
            buffer.write(f"\n❌ {exc}\n")
        finally:
            widget.after(0, lambda: _append_output(widget, buffer.getvalue()))

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()


class GetSciPapersGUI(ttk.Frame):
    """A minimal GUI for issuing searches and DOI downloads."""

    def __init__(self, master: tk.Tk | None = None) -> None:
        super().__init__(master)
        self.master.title(f"GetSciPapers {__version__}")
        self.master.geometry("760x520")
        self.master.resizable(True, True)
        self._build_widgets()

    def _build_widgets(self) -> None:
        padding = {"padx": 8, "pady": 4}

        # Search input
        search_frame = ttk.LabelFrame(self, text="Search")
        search_frame.grid(column=0, row=0, sticky="nsew", **padding)
        ttk.Label(search_frame, text="Keyword or DOI:").grid(column=0, row=0, sticky="w")
        self.search_var = tk.StringVar()
        ttk.Entry(search_frame, textvariable=self.search_var, width=50).grid(
            column=1, row=0, sticky="ew", **padding
        )

        ttk.Label(search_frame, text="Limit:").grid(column=0, row=1, sticky="w")
        self.limit_var = tk.IntVar(value=5)
        ttk.Spinbox(search_frame, from_=1, to=100, textvariable=self.limit_var, width=8).grid(
            column=1, row=1, sticky="w", **padding
        )

        # DOI file picker
        file_frame = ttk.LabelFrame(self, text="DOI list")
        file_frame.grid(column=0, row=1, sticky="nsew", **padding)
        self.doi_file_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.doi_file_var, width=50).grid(column=0, row=0, sticky="ew", **padding)
        ttk.Button(file_frame, text="Browse", command=self._choose_doi_file).grid(column=1, row=0, **padding)

        # Download options
        options_frame = ttk.LabelFrame(self, text="Options")
        options_frame.grid(column=0, row=2, sticky="nsew", **padding)
        self.download_folder_var = tk.StringVar(value=DEFAULT_DOWNLOAD_FOLDER)
        ttk.Label(options_frame, text="Download folder:").grid(column=0, row=0, sticky="w")
        ttk.Entry(options_frame, textvariable=self.download_folder_var, width=50).grid(
            column=1, row=0, sticky="ew", **padding
        )
        ttk.Button(options_frame, text="Choose", command=self._choose_folder).grid(column=2, row=0, **padding)

        ttk.Label(options_frame, text="Sources:").grid(column=0, row=1, sticky="nw")
        self.service_vars = {name: tk.BooleanVar(value=True) for name in DB_CHOICES}
        services_frame = ttk.Frame(options_frame)
        services_frame.grid(column=1, row=1, columnspan=2, sticky="w", **padding)
        for idx, name in enumerate(DB_CHOICES):
            ttk.Checkbutton(
                services_frame,
                text=name,
                variable=self.service_vars[name],
            ).grid(column=idx % 3, row=idx // 3, sticky="w", padx=4, pady=2)

        self.no_download_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="Metadata only (no download)", variable=self.no_download_var).grid(
            column=0, row=2, columnspan=2, sticky="w", **padding
        )
        self.verbose_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="Verbose", variable=self.verbose_var).grid(
            column=2, row=2, sticky="w", **padding
        )

        ttk.Label(options_frame, text=f"Download timeout: {DOWNLOAD_TIMEOUT}s").grid(
            column=0, row=3, columnspan=3, sticky="w", **padding
        )

        # Action buttons
        actions = ttk.Frame(self)
        actions.grid(column=0, row=3, sticky="ew", **padding)
        ttk.Button(actions, text="Search", command=self._run_search).grid(column=0, row=0, **padding)
        ttk.Button(actions, text="Download DOI list", command=self._run_doi_file).grid(column=1, row=0, **padding)

        # Output area
        self.output = scrolledtext.ScrolledText(self, wrap=tk.WORD, height=16, state="disabled")
        self.output.grid(column=0, row=4, sticky="nsew", **padding)

        # Make columns stretch
        for frame in (search_frame, file_frame, options_frame, actions):
            frame.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

    def _choose_doi_file(self) -> None:
        selected = filedialog.askopenfilename(title="Select DOI list", filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if selected:
            self.doi_file_var.set(selected)

    def _choose_folder(self) -> None:
        selected = filedialog.askdirectory(title="Select download folder")
        if selected:
            self.download_folder_var.set(selected)

    def _build_cli_args(self, search: bool) -> list[str]:
        args: list[str] = []
        if search:
            query = self.search_var.get().strip()
            if not query:
                raise ValueError("Please enter a keyword or DOI to search.")
            args.extend(["--search", query, "--limit", str(self.limit_var.get())])
        else:
            doi_file = self.doi_file_var.get().strip()
            if not doi_file:
                raise ValueError("Please choose a DOI list file to download.")
            args.extend(["--doi-file", doi_file])

        args.extend(["--download-folder", self.download_folder_var.get().strip() or DEFAULT_DOWNLOAD_FOLDER])
        selected_services = [name for name, var in self.service_vars.items() if var.get()]
        if len(selected_services) == len(DB_CHOICES) or not selected_services:
            args.extend(["--db", "all"])
        else:
            for service in selected_services:
                args.extend(["--db", service])
        if self.no_download_var.get():
            args.append("--no-download")
        if self.verbose_var.get():
            args.append("--verbose")
        return args

    def _run_search(self) -> None:
        try:
            argv = self._build_cli_args(search=True)
        except ValueError as exc:
            messagebox.showerror("Missing input", str(exc))
            return
        _append_output(self.output, "\n➡️ Running search...\n")
        _run_getpapers_async(argv, self.output)

    def _run_doi_file(self) -> None:
        try:
            argv = self._build_cli_args(search=False)
        except ValueError as exc:
            messagebox.showerror("Missing input", str(exc))
            return
        _append_output(self.output, "\n➡️ Downloading DOI list...\n")
        _run_getpapers_async(argv, self.output)


def launch_gui() -> None:
    root = tk.Tk()
    app = GetSciPapersGUI(master=root)
    app.pack(fill="both", expand=True)
    root.mainloop()

def main() -> None:
    """CLI entrypoint that launches the Tkinter GUI."""

    launch_gui()

if __name__ == "__main__":  # pragma: no cover - manual invocation helper
    launch_gui()
