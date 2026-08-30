Usage Guide
===========

The ``getscipapers`` command-line interface provides a set of subcommands that
coordinate searches, downloads, and requests across multiple services.

Basic Usage
-----------

- Show available modules and entry points::

    getscipapers --list

- Get help for a specific module::

    getscipapers getpapers --help

- Perform a quick DOI search using Crossref and Unpaywall::

    getscipapers getpapers --doi 10.1038/s41586-020-2649-2

- Request a paper through community bots without direct downloads::

    getscipapers request --doi 10.1038/s41586-020-2649-2 --service nexus

Example Workflows
-----------------

Use these ready-to-run commands as starting points:

.. code-block:: bash

   # Keyword search limited to 5 results, downloading PDFs when available
   getscipapers getpapers --search "graph neural network" --limit 5

   # Download a DOI via Unpaywall with non-interactive credentials
   GETSCIPAPERS_EMAIL=you@example.com \
   getscipapers getpapers --doi 10.1038/nature12373 --db unpaywall --non-interactive

   # Process many DOIs from a text file and save outputs to a custom folder
   getscipapers getpapers --doi-file dois.txt --download-folder ./pdfs

   # Extract DOIs from a PDF without downloading
   getscipapers getpapers --extract-doi-from-pdf paper.pdf --no-download

   # Show metadata only across all services for a DOI
   getscipapers getpapers --doi 10.1016/j.cell.2019.05.031 --no-download --verbose

   # If a proxy is configured, getpapers tries direct access first and retries
   # through the proxy only when the direct request fails or returns a
   # retryable HTTP status.

   # Log in to Z-Library using saved credentials (prompts and saves if missing)
   getscipapers zlib --login

   # Log in to Z-Library without prompting (fails if credentials are missing)
   getscipapers zlib --login --non-interactive

   # Search Z-Library and download selected books (interactive)
   getscipapers zlib --search "deep learning" --download

Graphical wrapper
-----------------

If you prefer not to remember command-line flags, start the Tkinter-based GUI wrapper (works on Windows and Linux) and trigger the same searches and DOI list downloads::

   getscipapers gui

The window exposes database selection (toggle one or many services), metadata-only runs, verbose logging, and custom download folders while reusing the existing CLI logic under the hood.

Search Strategies
-----------------

``getpapers`` combines several strategies to maximize discovery:

* **Crossref lookups** for authoritative metadata and publisher links.
* **Unpaywall queries** to find open access versions.
* **Nexus bot searches** to leverage community mirrors when direct download is not possible.
* **Sci-Hub**, **LibGen**, and **Anna's Archive** lookups for articles the
  publisher does not serve openly.

Pick between them with ``--db``, which accepts ``all``, ``nexus``, ``scihub``,
``anna``, ``unpaywall``, and ``libgen``. Z-Library is not part of this download
path; it has its own ``zlib`` subcommand for book-like content.

Under ``getpapers --db anna``, a cold DOI falls through to the browser route
when the md5 cache and LibGen both miss and ``--anna-scidb`` is not armed. That
route has Chromium solve the DDoS-Guard challenge, and whether it solves depends
on the address the request leaves from; from this host the page stayed on the
check for its whole budget and the run ended without a file. ``--db libgen``
still resolves a DOI to a catalog entry, and transfers of 82 kB, 407 kB and
922 kB each arrived at their full declared length, but a 48 MB file broke mid-stream on
every attempt and no fallback mirror produced it either. The
:doc:`cli_reference` covers the Anna's Archive routes and the LibGen transfers
in more detail.

Combine options thoughtfully. For example, a saved ``email`` credential or
``GETSCIPAPERS_EMAIL`` ensures Crossref and Unpaywall requests include a
contact address, improving API reliability.

Download Locations
------------------

Downloads are saved to the configured output directory (see
:doc:`configuration`). When running inside Docker or Codespaces, mount or bind a
host directory so that downloaded files persist outside the container.

For a container stack that pairs ``getscipapers`` with its own IPFS gateway, see
:doc:`docker_compose`.

Non-interactive Runs
--------------------

Many environments (CI, containers) cannot handle interactive prompts. Use the
``--non-interactive`` flag to require environment-provided credentials and avoid
blocking for input. When set, the command will exit with an error if a needed
credential is missing instead of waiting for keyboard input.
