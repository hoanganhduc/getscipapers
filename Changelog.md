# Changelog

All notable changes to this project are documented in this file. Dates reflect the commit timestamps for each recorded version in `pyproject.toml`.

## [Unreleased]
- Read the IPFS gateway address from `GETSCIPAPERS_IPFS_HTTP_BASE_URL` instead of hardcoding `http://127.0.0.1:8080`, so the Nexus/STC search works when the gateway is a separate container rather than a daemon on the same host.
- Document running getscipapers and an IPFS gateway as a Docker Compose stack, and the Kubo settings worth revisiting for a read-only node.

## [0.1.5] - 2026-08-30
- Reach Anna's Archive through the routes its DDoS-Guard challenge does not gate: the quota-free record route, the fast-download API, the member SciDB page behind an explicit `--scidb` opt-in, and a real browser when no account is configured.
- Add an `anna` CLI with credential, md5-cache, and account-status handling, and wire `--anna-md5`, `--anna-scidb`, and `--no-anna-browser` into `getpapers`.
- Resolve a cold DOI to an md5 through LibGen so Anna's Archive can take its quota-free route without launching a browser.
- Send a browser User-Agent to LibGen, which otherwise answers every request with the nginx placeholder page, and resolve relative mirror URLs before downloading.
- Expire auto-discovered proxies after an hour instead of trusting them forever, and stamp the entries `nexus` persists the same way.
- Keep the proxy `nexus` discovers out of the process environment so it cannot leak into unrelated requests.
- Probe the Z-Library domains instead of hardcoding one: `2-lib.org` no longer serves the API at all, and most of the hosts that replaced it answer every `/eapi/` path with a browser check, so the working host is selected on a JSON response rather than on the status code.
- Declare the `webdriver-manager` dependency in `pyproject.toml`.
- Correct the documented CLI invocations that no longer matched the parsers, and document the Anna's Archive routes, the browser prerequisites, the shared proxy behaviour, and the modules missing from the API reference.

## [0.1.4] - 2025-12-25
- Increase download timeouts across LibGen, Wiley, and Unpaywall fetchers to better tolerate slow mirrors and networks.
- Allow running `getscipapers gui` to launch the Tkinter wrapper via the package entrypoint.
- Add a `main` entrypoint to the GUI module so subcommand dispatch works without warnings.
- Add a cross-platform Tkinter GUI wrapper that reuses the CLI logic for searches and DOI list downloads.
- Allow programmatic invocations of ``getpapers`` with explicit argument lists for easier embedding in tools like the new GUI.
- Expand GUI service selection to let users target one or many sources (defaulting to all) and accept multiple `--db` flags in the CLI for parity.

## [0.1.3] - 2025-12-25
- Set the Windows event loop policy to `WindowsSelectorEventLoopPolicy` for CLI invocations to avoid Proactor cleanup errors when exiting.
- Standardize CLI option names and shorthand flags across modules for a consistent experience.
- Add explicit CLI usage examples to the README and Sphinx docs to guide common workflows.
- Enforce configured email usage across API calls and validate credentials before running CLI flows to avoid silent fallbacks.
- Refresh LibGen endpoints (download and FTP upload) and broaden DOI/ISBN extraction to improve request reliability.
- Improve PDF cleaning utilities with clearer logging for watermark removal, repeated text/images, and DOI/title resolution fallbacks.
- Refine DOI request orchestration to better handle title-based submissions and streamline Open Access link handling.
- Document donation links and developer tooling additions introduced after the 0.1.2 release.
- Centralize credentials, default paths, and directory creation helpers into a shared configuration module for reuse across CLI flows.
- Add comprehensive Sphinx documentation (usage, configuration, CLI/API reference) and link it from the README for easier contributor onboarding.
- Align the lightweight package metadata shim with the current version and author details to avoid stale information in tools that import `getscipapers_hoanganhduc.__name__`.

## [0.1.2] - 2025-08-11
- Expanded DOI extraction with ISBN resolution, additional publisher patterns, and PDF text preservation for better matching.
- Added watermark removal helpers (`remove_repeated_text`, `remove_repeated_images`, and `remove_watermark_inplace`) with verbose diagnostics.
- Enhanced `request_by_doi` and related flows to integrate Crossref and DOI REST fallbacks, populate missing metadata, and improve download logging.
- Updated Unpaywall usage to include verbose Open Access retrieval and browser-style PDF downloads.
- Refined README content and devcontainer settings for clearer setup, including VNC support and badge organization.

## [0.1.1] - 2025-07-30
- Hardened DOI validation with redirect checks, machine-readable metadata detection, and Crossref fallback logic.
- Added Facebook scraper improvements, waiting-request cancellation, and multi-service DOI request handling (including text file inputs).
- Introduced daily check-ins for AbleSci and Wosonhj services plus credentials workflow updates for automation.
- Improved caching in CI, credential file handling, and command-line argument parsing for service selection and download paths.
- Added additional DOI extraction regex coverage, PDF page limiting, and interactive prompts for Nexus and upload flows.

## [0.1.0] - 2025-06-26
- Initial release with core CLI for DOI extraction from PDFs/text, downloads via LibGen/Nexus/SciNet, and credential management utilities.
- Added upload support with timeout-protected prompts, proxy/credential logging, and headless browser options.
- Implemented early DOI regex iterations, Unpaywall caching, and default download directory handling.
