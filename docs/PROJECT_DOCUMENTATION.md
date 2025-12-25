# getscipapers Project Documentation

## Overview
getscipapers is a Python toolkit for locating scientific articles, validating DOIs, and requesting or downloading PDFs from multiple community and publisher-backed sources. The project exposes two primary CLIs:

- **getpapers**: end-to-end search and download orchestrator with DOI validation, metadata lookups, and multi-source downloads.
- **request**: a DOI-forwarding utility that posts requests to external helper services (e.g., Nexus bot, AbleSci) for community assistance.

The package also bundles source-specific helpers (Sci-Hub/Nexus/LibGen, Anna’s Archive, AbleSci, Facebook, etc.) and shared configuration utilities for credentials and cache paths.

## Package Layout
- `getscipapers_hoanganhduc/getpapers.py`: Core CLI for searching, validating, and downloading papers. Handles argument parsing, credential loading, DOI extraction, metadata lookup, and download orchestration across sources such as Unpaywall, Nexus, Sci-Hub, and Anna’s Archive.
- `getscipapers_hoanganhduc/request.py`: Async DOI requester that posts DOIs to supported services (Nexus, AbleSci, Wosonhj, Facebook, SciNet) with a synchronous wrapper for legacy usage.
- `getscipapers_hoanganhduc/configuration.py`: Centralized defaults, credential persistence, and directory helpers used by the CLIs.
- Source integrations: modules like `ablesci.py`, `nexus.py`, `libgen.py`, `scinet.py`, `facebook.py`, `Zlibrary.py`, and `zlib.py` provide site-specific login, scraping, or request routines.
- Utility scripts (e.g., `remove_metadata.py`, `upload.py`, `checkin.py`) offer ancillary workflows such as PDF metadata removal or daily check-ins for services that require activity.

## Configuration and Credentials
- The configuration module defines platform-aware defaults for the config file, download folder, and Unpaywall cache, exposing `GETPAPERS_CONFIG_FILE`, `DEFAULT_DOWNLOAD_FOLDER`, and cache paths. Directory creation is deferred to helpers so imports remain side-effect free, and calling `ensure_directory_exists` prepares folders on demand.
- Credentials are stored in JSON with keys for email, Elsevier API key, Wiley TDM token, and IEEE API key. `load_credentials` merges environment overrides (`GETSCIPAPERS_*`), optional interactive prompts, and file contents, updating module-level globals for reuse. It requires a terminal email value for APIs via `require_email`, surfacing a clear error when missing.
- `save_credentials` writes merged credentials back to disk, creating the config directory if necessary, and normalizes outputs for verbose CLI logging.

## getpapers CLI
- Argument parsing lives in `main()`, supporting mutually exclusive inputs for DOI (`--doi`), DOI file (`--doi-file`), keyword search (`--search`), or DOI extraction from PDF/text (`--extract-doi-from-pdf`, `--extract-doi-from-txt`). Global flags include verbosity, download folder overrides, source selection (`--db`), non-interactive credential loading, config printing, and credential clearing.
- The CLI initializes the Unpaywall cache, ensures download directories exist, and loads credentials from a chosen file or environment. It aborts early if required email credentials are missing or if conflicting input modes are provided.
- For DOI operations, the CLI validates and normalizes input, then orchestrates metadata checks (Crossref), open-access detection (Unpaywall), and download attempts across the selected sources. It summarizes successes/failures and respects `--no-download` to only print metadata without retrieving PDFs.
- Search mode (`--search`) queries Crossref via the `search_and_print` helper, limiting results with `--limit` and printing basic metadata such as title, journal, and publication year. Downloads can also be initiated from DOI lists provided via text files.

## DOI and Metadata Helpers
- Crossref interactions: `fetch_crossref_data` constructs requests with the configured email user agent, returning parsed metadata for DOI lookups and printing debug information when verbosity is enabled.
- Open access detection: `is_open_access_unpaywall` queries Unpaywall asynchronously to label DOIs as open/closed access prior to download attempts.
- Identifier normalization: utilities resolve Elsevier PIIs to DOIs (`resolve_pii_to_doi`), derive MDPI DOIs from URLs, and scan arbitrary URLs or text for DOI patterns (`fetch_dois_from_url`, text extraction helpers). PDF inspection is supported via PyPDF2 to locate embedded DOIs.

## Download Pipeline
- The download workflow iterates over requested DOIs, determines open-access status, and then attempts downloads from configured sources in priority order. Per-source results are tracked, and the CLI prints emoji-coded summaries for successes, failures, skipped downloads, or missing matches.
- Download directory preparation and caching use the shared configuration helpers to avoid hidden side effects and to reuse cache locations across runs.

## request CLI
- `request_dois` exposes a synchronous entry point that guards against nested asyncio loops, delegating to `async_request_dois` for concurrent posting to helper services. Users can target a single service, provide a list, or broadcast to all.
- Service handlers wrap each integration (Nexus, AbleSci, Wosonhj, Facebook, SciNet), translating return payloads into a consistent `{doi: {service: result}}` shape and surfacing errors per DOI for clearer CLI reporting.
- The CLI accepts flexible DOI input (single string, delimited list, text file, or arbitrary text blob) and normalizes service selections (single name, delimited names, or `all`). Results are printed with success/error icons per DOI.

## Source Integrations (Highlights)
- **AbleSci (`ablesci.py`)**: Selenium-driven login and request automation with cached cookies and credential storage. Provides default download directory helpers and credential file discovery tailored per OS.
- **Nexus (`nexus.py`)**: Utilities to interact with the Nexus bot/IPFS-powered database for DOI-based lookups and requests.
- **LibGen & Z-Library (`libgen.py`, `zlib.py`, `Zlibrary.py`)**: Search and download helpers for article/book retrieval from public libraries.
- **SciNet (`scinet.py`)**: Login and request routines for the sci-net.xyz community portal.
- **Facebook (`facebook.py`)**: Automation around posting DOI requests to relevant groups, including cookie handling for persisted sessions.
- **Anna’s Archive (`nexus.py`/`libgen.py` interplay)**: Included in the multi-source download path for fallback retrieval.

## Operational Notes
- Both CLIs inherit the project-wide `DEFAULT_LIMIT` and path defaults from the configuration module, ensuring consistent behavior across entry points.
- Non-interactive environments should supply `GETSCIPAPERS_EMAIL` (and any API keys) to bypass prompts and satisfy API requirements.
- The project relies on third-party services that may change behavior; verbose mode helps diagnose request headers, redirects, and fallback paths when integrations fail.
