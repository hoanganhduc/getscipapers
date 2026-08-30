Configuration
=============

Credentials and cache locations are centralized in
``getscipapers_hoanganhduc.configuration``. Key points:

Credential Sources
------------------

* Environment variables ``GETSCIPAPERS_EMAIL``,
  ``GETSCIPAPERS_ELSEVIER_API_KEY``, ``GETSCIPAPERS_WILEY_TDM_TOKEN``, and
  ``GETSCIPAPERS_IEEE_API_KEY`` can be provided to avoid interactive prompts.
  They override whatever the credentials file holds.
* JSON files at ``~/.config/getscipapers/getpapers/config.json`` (Linux/macOS)
  or ``%LOCALAPPDATA%\getscipapers\getpapers\config.json`` (Windows) are
  loaded when present. Point at a different file with ``--credentials``.
* Z-Library stores credentials in ``~/.config/getscipapers/zlib/zlib_config.json``
  (Linux/macOS) or the matching ``zlib`` folder under ``%LOCALAPPDATA%``
  (Windows).
* Anna's Archive stores its account secret in
  ``~/.config/getscipapers/anna/credentials.json`` under the key
  ``anna_secret_key``, or reads it from ``GETSCIPAPERS_ANNA_SECRET_KEY``.
* The ``--non-interactive`` flag forces the CLI to abort if credentials are
  missing instead of prompting for input.

``sample_credentials.json`` in the repository root lists every key the bundled
modules read.

Cache and Download Directories
------------------------------

* The Unpaywall cache sits beside the configuration file; the paths are exposed
  as ``configuration.UNPYWALL_CACHE_DIR`` and
  ``configuration.UNPYWALL_CACHE_FILE``.
* Download targets default to ``~/Downloads/getscipapers``, reported by
  ``configuration.get_default_download_folder()``, and can be overridden with
  the ``--download-folder`` flag in ``getpapers``.
* Every module prints the locations it will use when given ``--print-default``.

Token Management
----------------

API keys for Elsevier and Wiley can be set via environment variables or saved to
credentials files. The refresh helpers in ``configuration`` ensure these tokens
are reloaded each time a request is made rather than captured at import time.
An IEEE key is stored alongside them for future use, but no download path reads
it yet.

Proxy Configuration
-------------------

``getpapers``, ``anna``, and the service modules share the helpers in
``getscipapers_hoanganhduc.proxy_config``:

* ``--proxy <file>`` points at a JSON file holding either one proxy object or a
  list of them, in the shape of ``sample_proxy_config.json``. The default
  location is ``~/.config/getscipapers/getpapers/proxy.json``.
* ``--no-proxy`` forces direct connections even when a configuration is present.
* ``--auto-proxy`` discovers a working public proxy when none is configured or
  the configured one no longer answers. An auto-discovered entry is stamped with
  its discovery time and treated as stale after an hour
  (``AUTO_PROXY_MAX_AGE_SECONDS``), so a dead free proxy is replaced rather than
  trusted indefinitely.

Requests are attempted directly first. The proxy is used only as a retry, when
the direct attempt raises or returns one of ``PROXY_RETRY_STATUSES``
(403, 407, 408, 429, 500, 502, 503, 504).

IPFS Gateway
------------

The Nexus/STC search step reads its index over an IPFS gateway. It defaults to
``http://127.0.0.1:8080``, a Kubo daemon on the same host, and reads
``GETSCIPAPERS_IPFS_HTTP_BASE_URL`` when that address is wrong.

Set it whenever the gateway is not local. In a container stack the gateway runs
as its own service, so ``127.0.0.1`` inside the application container is the
application itself rather than the gateway::

   GETSCIPAPERS_IPFS_HTTP_BASE_URL=http://ipfs:8080

The variable is read each time a search starts, and an empty value falls back to
the default. It is not a credential, so it is read only from the environment and
never stored in the credentials file.
