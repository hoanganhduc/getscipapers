Configuration
=============

Credentials and cache locations are centralized in
``getscipapers_hoanganhduc.configuration``. Key points:

Credential Sources
------------------

* Environment variables such as ``CROSSREF_EMAIL`` and ``UNPAYWALL_EMAIL`` can
  be provided to avoid interactive prompts.
* JSON files at ``~/.config/getscipapers/credentials.json`` (Linux/macOS) or
  ``%APPDATA%/getscipapers/credentials.json`` (Windows) are loaded when present.
* The ``--non-interactive`` flag forces the CLI to abort if credentials are
  missing instead of prompting for input.

Cache and Download Directories
------------------------------

* The default cache directory is derived from the operating system and can be
  inspected via ``configuration.get_cache_dir()``.
* Download targets default to ``~/Downloads/getscipapers`` but can be overridden
  with the ``--download-dir`` flag in ``getpapers``.

Token Management
----------------

API keys for Elsevier and Wiley can be set via environment variables or saved to
credentials files. The refresh helpers in ``configuration`` ensure these tokens
are reloaded each time a request is made rather than captured at import time.
