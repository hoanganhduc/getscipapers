"""Lightweight Tkinter GUI wrapper around the ``getpapers`` CLI.

This module provides a simple cross-platform window for triggering common
search and download workflows without remembering all command-line options.
It wraps the existing asynchronous CLI so behavior matches terminal usage
on both Windows and Linux.
"""

from __future__ import annotations

import asyncio
import io
import os
import subprocess
import sys
import json
import threading
import tkinter as tk
import webbrowser
from collections.abc import Callable
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .getpapers import main as getpapers_main
from .getpapers import DB_CHOICES, DEFAULT_DOWNLOAD_FOLDER, DEFAULT_PROXY_FILE, GETPAPERS_CONFIG_FILE
from .getpapers import DOWNLOAD_TIMEOUT
from .remove_metadata import remove_metadata as strip_pdf_metadata
from .__name__ import __author__, __version__


def _append_output(widget: tk.Text, text: str) -> None:
    widget.configure(state="normal")
    widget.insert(tk.END, text)
    widget.see(tk.END)
    widget.configure(state="disabled")


def _append_log(widget: tk.Text, text: str) -> None:
    widget.configure(state="normal")
    timestamp = datetime.now().strftime("%H:%M:%S")
    for line in text.splitlines():
        widget.insert(tk.END, f"[{timestamp}] {line}\n")
    widget.see(tk.END)
    widget.configure(state="disabled")


def _run_getpapers_async(
    argv: list[str],
    widget: tk.Text,
    on_complete: Callable[[], None] | None = None,
    *,
    log_widget: tk.Text | None = None,
) -> None:
    """Execute the async ``getpapers`` entry point on a background thread."""

    buffer = io.StringIO()

    def _target() -> None:
        try:
            with redirect_stdout(buffer), redirect_stderr(buffer):
                asyncio.run(getpapers_main(argv))
        except Exception as exc:  # pragma: no cover - UI safety net
            buffer.write(f"\n❌ {exc}\n")
        finally:
            widget.after(0, _deliver)

    def _deliver() -> None:
        text = buffer.getvalue()
        _append_output(widget, text)
        if log_widget is not None:
            _append_log(log_widget, text)
        if on_complete:
            on_complete()

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()


class GetSciPapersGUI(ttk.Frame):
    """A minimal GUI for issuing searches and DOI downloads."""

    def __init__(self, master: tk.Tk | None = None) -> None:
        super().__init__(master)
        self.master.title(f"GetSciPapers {__version__}")
        self.profile_path = Path.home() / ".getscipapers_gui_profile.json"
        self._build_widgets()
        self._load_profile()
        self._configure_initial_size()

    def _set_running_state(self, running: bool, message: str = "Ready") -> None:
        self.status_var.set(message)
        state = "disabled" if running else "normal"
        for button in self._action_buttons:
            button.configure(state=state)
        if not running:
            self.output.focus_set()

        if running:
            self.progress_task_var.set(message)
            self.progress_bar.start(10)
        else:
            self.progress_task_var.set("")
            self.progress_bar.stop()

    def _build_widgets(self) -> None:
        padding = {"padx": 8, "pady": 4}

        self.status_var = tk.StringVar(value=f"Ready • v{__version__}")
        self.progress_task_var = tk.StringVar()

        self.main_notebook = ttk.Notebook(self)
        self.main_notebook.grid(column=0, row=0, sticky="nsew", **padding)

        run_tab = ttk.Frame(self.main_notebook)
        settings_tab = ttk.Frame(self.main_notebook)
        about_tab = ttk.Frame(self.main_notebook)
        self.main_notebook.add(run_tab, text="Run")
        self.main_notebook.add(settings_tab, text="Settings")
        self.main_notebook.add(about_tab, text="About")

        # Search input
        search_frame = ttk.LabelFrame(run_tab, text="Search")
        search_frame.grid(column=0, row=0, sticky="nsew", **padding)
        ttk.Label(search_frame, text="Keyword or DOI:").grid(column=0, row=0, sticky="w")
        self.search_var = tk.StringVar()
        ttk.Entry(search_frame, textvariable=self.search_var, width=50).grid(
            column=1, row=0, sticky="ew", **padding
        )
        self.search_error = ttk.Label(search_frame, foreground="#b00020")
        self.search_error.grid(column=2, row=0, sticky="w")

        ttk.Label(search_frame, text="Limit:").grid(column=0, row=1, sticky="w")
        self.limit_var = tk.IntVar(value=5)
        ttk.Spinbox(search_frame, from_=1, to=100, textvariable=self.limit_var, width=8).grid(
            column=1, row=1, sticky="w", **padding
        )

        # DOI inputs
        doi_frame = ttk.LabelFrame(run_tab, text="DOIs")
        doi_frame.grid(column=0, row=1, sticky="nsew", **padding)
        ttk.Label(doi_frame, text="Type DOIs (comma-separated):").grid(column=0, row=0, sticky="w")
        self.doi_input_var = tk.StringVar()
        ttk.Entry(doi_frame, textvariable=self.doi_input_var, width=50).grid(
            column=1, row=0, sticky="ew", **padding
        )
        self.doi_input_error = ttk.Label(doi_frame, foreground="#b00020")
        self.doi_input_error.grid(column=2, row=0, sticky="w")

        ttk.Label(doi_frame, text="Or choose DOI list file:").grid(column=0, row=1, sticky="w")
        self.doi_file_var = tk.StringVar()
        ttk.Entry(doi_frame, textvariable=self.doi_file_var, width=50).grid(column=1, row=1, sticky="ew", **padding)
        ttk.Button(doi_frame, text="Browse", command=self._choose_doi_file).grid(column=2, row=1, **padding)
        self.doi_file_error = ttk.Label(doi_frame, foreground="#b00020")
        self.doi_file_error.grid(column=3, row=1, sticky="w")

        cleanup_frame = ttk.LabelFrame(run_tab, text="Metadata cleanup")
        cleanup_frame.grid(column=0, row=2, sticky="nsew", **padding)
        ttk.Label(cleanup_frame, text="PDF to clean metadata:").grid(column=0, row=0, sticky="w")
        self.metadata_file_var = tk.StringVar()
        ttk.Entry(cleanup_frame, textvariable=self.metadata_file_var, width=50).grid(
            column=1, row=0, sticky="ew", **padding
        )
        ttk.Button(cleanup_frame, text="Browse", command=self._choose_metadata_file).grid(
            column=2, row=0, **padding
        )
        self.metadata_inplace_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            cleanup_frame,
            text="Overwrite original (in place)",
            variable=self.metadata_inplace_var,
        ).grid(column=3, row=0, sticky="w", **padding)
        self.metadata_error = ttk.Label(cleanup_frame, foreground="#b00020")
        self.metadata_error.grid(column=4, row=0, sticky="w")

        # Download options
        options_frame = ttk.LabelFrame(settings_tab, text="Options")
        options_frame.grid(column=0, row=0, sticky="nsew", **padding)
        self.download_folder_var = tk.StringVar(value=DEFAULT_DOWNLOAD_FOLDER)
        ttk.Label(options_frame, text="Download folder:").grid(column=0, row=0, sticky="w")
        ttk.Entry(options_frame, textvariable=self.download_folder_var, width=50).grid(
            column=1, row=0, sticky="ew", **padding
        )
        ttk.Button(options_frame, text="Choose", command=self._choose_folder).grid(column=2, row=0, **padding)
        ttk.Button(options_frame, text="Open", command=self._open_download_folder).grid(column=3, row=0, **padding)

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

        ttk.Label(options_frame, text="Credentials file (optional):").grid(
            column=0, row=4, sticky="w"
        )
        self.credentials_path_var = tk.StringVar(value=GETPAPERS_CONFIG_FILE)
        ttk.Entry(options_frame, textvariable=self.credentials_path_var, width=50).grid(
            column=1, row=4, sticky="ew", **padding
        )
        ttk.Button(options_frame, text="Browse", command=self._choose_credentials_file).grid(
            column=2, row=4, **padding
        )
        self.credentials_error = ttk.Label(options_frame, foreground="#b00020")
        self.credentials_error.grid(column=3, row=4, sticky="w")

        ttk.Label(options_frame, text="Proxy config (optional):").grid(column=0, row=5, sticky="w")
        self.proxy_file_var = tk.StringVar(value=str(DEFAULT_PROXY_FILE))
        ttk.Entry(options_frame, textvariable=self.proxy_file_var, width=50).grid(
            column=1, row=5, sticky="ew", **padding
        )
        ttk.Button(options_frame, text="Browse", command=self._choose_proxy_file).grid(
            column=2, row=5, **padding
        )
        self.use_proxy_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="Use proxy", variable=self.use_proxy_var).grid(
            column=3, row=5, sticky="w", **padding
        )
        self.auto_proxy_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="Auto fetch", variable=self.auto_proxy_var).grid(
            column=4, row=5, sticky="w", **padding
        )
        self.proxy_error = ttk.Label(options_frame, foreground="#b00020")
        self.proxy_error.grid(column=5, row=5, sticky="w")

        ttk.Separator(options_frame, orient="horizontal").grid(column=0, row=6, columnspan=6, sticky="ew", pady=(8, 4))
        profile_buttons = ttk.Frame(options_frame)
        profile_buttons.grid(column=0, row=7, columnspan=6, sticky="w", **padding)
        ttk.Button(profile_buttons, text="Save profile", command=self._save_profile).grid(column=0, row=0, padx=(0, 6))
        ttk.Button(profile_buttons, text="Reload profile", command=self._load_profile).grid(column=1, row=0)

        # Action buttons
        actions = ttk.Frame(run_tab)
        actions.grid(column=0, row=3, sticky="ew", **padding)
        search_btn = ttk.Button(actions, text="Search", command=self._run_search)
        search_btn.grid(column=0, row=0, **padding)
        doi_btn = ttk.Button(actions, text="Download typed DOIs", command=self._run_doi_input)
        doi_btn.grid(column=1, row=0, **padding)
        doi_file_btn = ttk.Button(actions, text="Download DOI list", command=self._run_doi_file)
        doi_file_btn.grid(column=2, row=0, **padding)
        metadata_btn = ttk.Button(actions, text="Remove metadata", command=self._run_metadata_cleanup)
        metadata_btn.grid(column=3, row=0, **padding)
        clear_btn = ttk.Button(actions, text="Clear output", command=self._clear_output)
        clear_btn.grid(column=4, row=0, **padding)
        self._action_buttons = (search_btn, doi_btn, doi_file_btn, metadata_btn, clear_btn)
        self.progress_bar = ttk.Progressbar(self, mode="indeterminate")
        progress_row = ttk.Frame(self)
        progress_row.grid(column=0, row=1, sticky="ew", padx=8)
        ttk.Label(progress_row, textvariable=self.progress_task_var).grid(column=0, row=0, sticky="w")
        self.progress_bar.grid(column=0, row=2, sticky="ew", padx=8)

        # About tab content
        about_frame = ttk.LabelFrame(about_tab, text="About GetSciPapers")
        about_frame.grid(column=0, row=0, sticky="nsew", **padding)
        ttk.Label(
            about_frame,
            text=(
                "Lightweight desktop companion for the getpapers CLI. "
                "Search, download, and clean PDFs while keeping credentials and proxy options in sync."
            ),
            wraplength=520,
            justify="left",
        ).grid(column=0, row=0, columnspan=2, sticky="w", **padding)
        ttk.Label(about_frame, text=f"Author: {__author__}").grid(column=0, row=1, sticky="w", **padding)
        ttk.Label(about_frame, text=f"Version: {__version__}").grid(column=1, row=1, sticky="w", **padding)
        ttk.Label(about_frame, text="License: GPL-3.0").grid(column=0, row=2, sticky="w", **padding)
        self._link_label(
            about_frame,
            text="View license",
            url="https://www.gnu.org/licenses/gpl-3.0.en.html",
        ).grid(column=1, row=2, sticky="w", **padding)
        self._link_label(
            about_frame,
            text="GitHub repository",
            url="https://github.com/hoanganhduc/getscipapers",
        ).grid(column=0, row=3, sticky="w", **padding)
        self._link_label(
            about_frame,
            text="Documentation",
            url="https://github.com/hoanganhduc/getscipapers#usage",
        ).grid(column=1, row=3, sticky="w", **padding)
        self._link_label(
            about_frame,
            text="Buy me a coffee",
            url="https://www.buymeacoffee.com/hoanganhduc",
        ).grid(column=0, row=4, sticky="w", **padding)
        self._link_label(
            about_frame,
            text="Ko-fi",
            url="https://ko-fi.com/hoanganhduc",
        ).grid(column=1, row=4, sticky="w", **padding)
        self._link_label(
            about_frame,
            text="Crypto tip (BMACC)",
            url="https://bmacc.app/tip/hoanganhduc",
        ).grid(column=0, row=5, sticky="w", **padding)
        ttk.Label(
            about_frame,
            text="Thank you for supporting continued development!",
            foreground="#0b6cf4",
        ).grid(column=0, row=6, columnspan=2, sticky="w", **padding)

        # Output area with detailed log tab
        self.output_notebook = ttk.Notebook(self)
        self.output_notebook.grid(column=0, row=3, sticky="nsew", **padding)
        self.output = scrolledtext.ScrolledText(self.output_notebook, wrap=tk.WORD, height=16, state="disabled")
        self.detailed_log = scrolledtext.ScrolledText(
            self.output_notebook, wrap=tk.WORD, height=16, state="disabled"
        )
        self.output_notebook.add(self.output, text="Console")
        self.output_notebook.add(self.detailed_log, text="Detailed log")

        status_bar = ttk.Label(self, textvariable=self.status_var, anchor="w")
        status_bar.grid(column=0, row=4, sticky="ew", padx=8, pady=(0, 8))

        # Make columns stretch
        for frame in (search_frame, doi_frame, cleanup_frame, actions, options_frame, about_frame):
            frame.grid_columnconfigure(1, weight=1)
        about_tab.grid_columnconfigure(0, weight=1)
        about_tab.grid_rowconfigure(0, weight=1)
        for frame in (run_tab, settings_tab):
            frame.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        self._error_labels = {
            "search": self.search_error,
            "doi_input": self.doi_input_error,
            "doi_file": self.doi_file_error,
            "credentials": self.credentials_error,
            "proxy": self.proxy_error,
            "metadata": self.metadata_error,
        }
        self._clear_errors()

    def _link_label(self, parent: ttk.Frame, text: str, url: str) -> ttk.Label:
        label = ttk.Label(parent, text=text, foreground="#0b6cf4", cursor="hand2")

        def _open(_: object) -> None:
            webbrowser.open_new_tab(url)

        label.bind("<Button-1>", _open)
        return label

    def _toast(self, message: str, *, duration: int = 3000) -> None:
        """Show a small temporary toast notification near the main window."""

        toast = tk.Toplevel(self)
        toast.wm_overrideredirect(True)
        toast.attributes("-topmost", True)
        ttk.Label(toast, text=message, padding=8).pack()

        self.update_idletasks()
        x = self.winfo_rootx() + 40
        y = self.winfo_rooty() + 40
        toast.geometry(f"+{x}+{y}")
        toast.after(duration, toast.destroy)

    def _log_event(self, message: str) -> None:
        _append_log(self.detailed_log, message)

    def _clear_errors(self) -> None:
        for label in self._error_labels.values():
            label.configure(text="")

    def _flag_error(self, key: str, message: str) -> None:
        if key in self._error_labels:
            self._error_labels[key].configure(text=message)

    def _choose_doi_file(self) -> None:
        selected = filedialog.askopenfilename(title="Select DOI list", filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if selected:
            self.doi_file_var.set(selected)

    def _choose_folder(self) -> None:
        selected = filedialog.askdirectory(title="Select download folder")
        if selected:
            self.download_folder_var.set(selected)

    def _choose_credentials_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select credentials file",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if selected:
            self.credentials_path_var.set(selected)

    def _choose_proxy_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select proxy configuration",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if selected:
            self.proxy_file_var.set(selected)

    def _choose_metadata_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select PDF to clean metadata",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if selected:
            self.metadata_file_var.set(selected)

    def _configure_initial_size(self) -> None:
        """Resize the window based on its requested dimensions."""

        self.update_idletasks()
        required_width = self.winfo_reqwidth() + 32
        required_height = self.winfo_reqheight() + 32
        self.master.geometry(f"{required_width}x{required_height}")
        self.master.minsize(required_width, required_height)
        self.master.resizable(True, True)

    def _build_cli_args(self, mode: str) -> list[str] | None:
        self._clear_errors()

        args: list[str] = []
        if mode == "search":
            query = self.search_var.get().strip()
            if not query:
                self._flag_error("search", "Required")
                return None
            args.extend(["--search", query, "--limit", str(self.limit_var.get())])
        elif mode == "doi_file":
            doi_file = self.doi_file_var.get().strip()
            if not doi_file:
                self._flag_error("doi_file", "Choose a file")
                return None
            expanded = Path(doi_file).expanduser()
            if not expanded.is_file():
                self._flag_error("doi_file", "File not found")
                return None
            args.extend(["--doi-file", str(expanded)])
        elif mode == "doi_input":
            raw_input = self.doi_input_var.get().strip()
            if not raw_input:
                self._flag_error("doi_input", "Enter at least one DOI")
                return None
            dois = [doi.strip() for doi in raw_input.replace(";", ",").split(",") if doi.strip()]
            if not dois:
                self._flag_error("doi_input", "No valid DOIs")
                return None
            for doi in dois:
                args.extend(["--doi", doi])
        else:
            return None

        args.extend(["--download-folder", self.download_folder_var.get().strip() or DEFAULT_DOWNLOAD_FOLDER])
        selected_services = [name for name, var in self.service_vars.items() if var.get()]
        if len(selected_services) == len(DB_CHOICES) or not selected_services:
            args.extend(["--db", "all"])
        else:
            for service in selected_services:
                args.extend(["--db", service])
        credentials_path = self.credentials_path_var.get().strip()
        if credentials_path:
            expanded_path = Path(credentials_path).expanduser()
            if expanded_path.exists():
                args.extend(["--credentials", str(expanded_path)])
            elif credentials_path != GETPAPERS_CONFIG_FILE:
                self._flag_error("credentials", "Not found")
                return None
        if self.use_proxy_var.get():
            proxy_path = self.proxy_file_var.get().strip()
            if proxy_path:
                expanded_proxy = Path(proxy_path).expanduser()
                if expanded_proxy.exists():
                    args.extend(["--proxy", str(expanded_proxy)])
                    if self.auto_proxy_var.get():
                        args.append("--auto-proxy")
                else:
                    self._flag_error("proxy", "Missing file")
                    return None
            else:
                self._flag_error("proxy", "Add a proxy file or disable")
                return None
        else:
            args.append("--no-proxy")
        if self.no_download_var.get():
            args.append("--no-download")
        if self.verbose_var.get():
            args.append("--verbose")
        return args

    def _run_search(self) -> None:
        argv = self._build_cli_args(mode="search")
        if not argv:
            self._toast("Please fix the highlighted search input.")
            return
        _append_output(self.output, "\n➡️ Running search...\n")
        self._log_event("Search started")
        task_label = "Running search…"
        if self.auto_proxy_var.get():
            task_label += " (auto proxy)"
        self._set_running_state(True, task_label)
        _run_getpapers_async(
            argv,
            self.output,
            on_complete=lambda: self._finish_task("Search finished."),
            log_widget=self.detailed_log,
        )

    def _run_doi_input(self) -> None:
        argv = self._build_cli_args(mode="doi_input")
        if not argv:
            self._toast("Check the DOI field for errors.")
            return
        _append_output(self.output, "\n➡️ Downloading typed DOIs...\n")
        self._log_event("Typed DOI download started")
        task_label = "Downloading DOIs…"
        if self.auto_proxy_var.get():
            task_label += " (auto proxy)"
        self._set_running_state(True, task_label)
        _run_getpapers_async(
            argv,
            self.output,
            on_complete=lambda: self._finish_task("DOI download complete."),
            log_widget=self.detailed_log,
        )

    def _run_doi_file(self) -> None:
        argv = self._build_cli_args(mode="doi_file")
        if not argv:
            self._toast("Please provide a valid DOI list file.")
            return
        _append_output(self.output, "\n➡️ Downloading DOI list...\n")
        self._log_event("DOI list download started")
        task_label = "Downloading DOI list…"
        if self.auto_proxy_var.get():
            task_label += " (auto proxy)"
        self._set_running_state(True, task_label)
        _run_getpapers_async(
            argv,
            self.output,
            on_complete=lambda: self._finish_task("DOI list download complete."),
            log_widget=self.detailed_log,
        )

    def _finish_task(self, message: str) -> None:
        self._set_running_state(False, "Ready")
        self._log_event(message)
        self._toast(message)

    def _save_profile(self) -> None:
        payload = {
            "download_folder": self.download_folder_var.get().strip(),
            "credentials": self.credentials_path_var.get().strip(),
            "proxy_file": self.proxy_file_var.get().strip(),
            "use_proxy": self.use_proxy_var.get(),
            "auto_proxy": self.auto_proxy_var.get(),
            "no_download": self.no_download_var.get(),
            "verbose": self.verbose_var.get(),
            "services": {name: var.get() for name, var in self.service_vars.items()},
            "limit": self.limit_var.get(),
            "doi_file": self.doi_file_var.get().strip(),
            "doi_input": self.doi_input_var.get().strip(),
            "metadata_inplace": self.metadata_inplace_var.get(),
        }
        try:
            self.profile_path.write_text(json.dumps(payload, indent=2))
            self._toast(f"Profile saved to {self.profile_path}")
        except Exception as exc:  # pragma: no cover - defensive UI path
            _append_output(self.output, f"\n❌ Failed to save profile: {exc}\n")
            self._toast("Unable to save profile")

    def _load_profile(self) -> None:
        if not self.profile_path.exists():
            return
        try:
            data = json.loads(self.profile_path.read_text())
        except Exception as exc:  # pragma: no cover - defensive UI path
            _append_output(self.output, f"\n❌ Failed to load profile: {exc}\n")
            self._toast("Profile load failed")
            return

        self.download_folder_var.set(data.get("download_folder", self.download_folder_var.get()))
        self.credentials_path_var.set(data.get("credentials", self.credentials_path_var.get()))
        self.proxy_file_var.set(data.get("proxy_file", self.proxy_file_var.get()))
        self.use_proxy_var.set(bool(data.get("use_proxy", self.use_proxy_var.get())))
        self.auto_proxy_var.set(bool(data.get("auto_proxy", self.auto_proxy_var.get())))
        self.no_download_var.set(bool(data.get("no_download", self.no_download_var.get())))
        self.verbose_var.set(bool(data.get("verbose", self.verbose_var.get())))
        self.metadata_inplace_var.set(bool(data.get("metadata_inplace", self.metadata_inplace_var.get())))
        self.limit_var.set(int(data.get("limit", self.limit_var.get())))
        self.doi_file_var.set(data.get("doi_file", self.doi_file_var.get()))
        self.doi_input_var.set(data.get("doi_input", self.doi_input_var.get()))

        services = data.get("services", {})
        if isinstance(services, dict):
            for name, var in self.service_vars.items():
                var.set(bool(services.get(name, var.get())))

        self._toast("Profile loaded")

    def _run_metadata_cleanup(self) -> None:
        target = self.metadata_file_var.get().strip()
        self._clear_errors()
        if not target:
            self._flag_error("metadata", "Select a PDF")
            self._toast("Choose a PDF to clean.")
            return
        pdf_path = Path(target).expanduser()
        if not pdf_path.is_file():
            self._flag_error("metadata", "File not found")
            self._toast("Selected PDF was not found.")
            return

        inplace = self.metadata_inplace_var.get()
        output_path = pdf_path if inplace else pdf_path.with_name(f"{pdf_path.stem}_no_metadata{pdf_path.suffix}")

        def _deliver(text: str) -> None:
            _append_output(self.output, text)
            _append_log(self.detailed_log, text)
            self._finish_task("Metadata cleanup finished.")

        def _task() -> None:
            buffer = io.StringIO()
            try:
                with redirect_stdout(buffer), redirect_stderr(buffer):
                    strip_pdf_metadata(str(pdf_path), str(output_path), verbose=self.verbose_var.get())
                summary = (
                    f"\n✅ Cleaned metadata in place: {output_path}\n"
                    if inplace
                    else f"\n✅ Saved cleaned PDF to: {output_path}\n"
                )
                buffer.write(summary)
            except Exception as exc:  # pragma: no cover - UI safety net
                buffer.write(f"\n❌ Failed to remove metadata: {exc}\n")
            finally:
                self.output.after(0, lambda: _deliver(buffer.getvalue()))

        _append_output(self.output, "\n➡️ Removing PDF metadata...\n")
        self._log_event("Metadata cleanup started")
        self._set_running_state(True, "Cleaning PDF metadata…")
        thread = threading.Thread(target=_task, daemon=True)
        thread.start()

    def _clear_output(self) -> None:
        self.output.configure(state="normal")
        self.output.delete("1.0", tk.END)
        self.output.configure(state="disabled")
        self.detailed_log.configure(state="normal")
        self.detailed_log.delete("1.0", tk.END)
        self.detailed_log.configure(state="disabled")

    def _open_download_folder(self) -> None:
        folder = Path(self.download_folder_var.get().strip() or DEFAULT_DOWNLOAD_FOLDER).expanduser()
        if not folder.exists():
            messagebox.showerror("Folder not found", f"Download folder does not exist:\n{folder}")
            return
        try:
            if os.name == "nt":
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", folder], check=False)
            else:
                subprocess.run(["xdg-open", folder], check=False)
        except Exception as exc:  # pragma: no cover - best-effort helper
            messagebox.showerror("Unable to open folder", str(exc))


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
