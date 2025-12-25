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

    getscipapers getpapers --doi 10.1038/s41586-020-2649-2 --email you@example.com

- Request a paper through community bots without direct downloads::

    getscipapers request --title "Efficient Vision Transformers" --nexus --non-interactive

Example Workflows
-----------------

Use these ready-to-run commands as starting points:

.. code-block:: bash

   # Keyword search limited to 5 results, downloading PDFs when available
   getscipapers getpapers --search "graph neural network" --limit 5

   # Download a DOI via Unpaywall with non-interactive credentials
   GETSCIPAPERS_EMAIL=you@example.com \\
   getscipapers getpapers --doi 10.1038/nature12373 --db unpaywall --non-interactive

   # Process many DOIs from a text file and save outputs to a custom folder
   getscipapers getpapers --doi-file dois.txt --download-folder ./pdfs

   # Extract DOIs from a PDF without downloading
   getscipapers getpapers --extract-doi-from-pdf paper.pdf --no-download

   # Show metadata only across all services for a DOI
   getscipapers getpapers --doi 10.1016/j.cell.2019.05.031 --no-download --verbose

Search Strategies
-----------------

``getpapers`` combines several strategies to maximize discovery:

* **Crossref lookups** for authoritative metadata and publisher links.
* **Unpaywall queries** to find open access versions.
* **Nexus bot searches** to leverage community mirrors when direct download is not possible.
* Optional **LibGen** and **Z-Library** queries for book-like content.

Combine options thoughtfully. For example, supplying ``--email`` ensures
Crossref and Unpaywall requests include a contact address, improving API
reliability.

Download Locations
------------------

Downloads are saved to the configured output directory (see
:doc:`configuration`). When running inside Docker or Codespaces, mount or bind a
host directory so that downloaded files persist outside the container.

Non-interactive Runs
--------------------

Many environments (CI, containers) cannot handle interactive prompts. Use the
``--non-interactive`` flag to require environment-provided credentials and avoid
blocking for input. When set, the command will exit with an error if a needed
credential is missing instead of waiting for keyboard input.
