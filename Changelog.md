# Changelog

All notable changes to this project are documented in this file. Dates reflect the commit timestamps for each recorded version in `pyproject.toml`.

## [Unreleased]
- No changes yet.

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
