CLI Reference
=============

``getscipapers`` acts as a dispatcher for module-based subcommands. The most
commonly used modules are summarized below.

getpapers
---------

.. code-block:: bash

   getscipapers getpapers --doi <doi> --download-folder <path>

Searches for papers using Crossref and Unpaywall, then downloads from the
selected sources. Key options:

* ``--doi``, ``--doi-file``, or ``--search``: choose between a direct DOI
  lookup, a file of DOIs, and a keyword search.
* ``--db``: which source to download from, one of ``all``, ``nexus``,
  ``scihub``, ``anna``, ``unpaywall``, ``libgen``. Repeat the flag to target
  several; defaults to ``all``.
* ``--download-folder``: where to save the PDFs.
* ``--credentials``: load a JSON credentials file instead of the default one.
* ``--non-interactive``: fail fast if credentials are missing.

The contact address several APIs require comes from the credentials file or
``GETSCIPAPERS_EMAIL``; there is no ``--email`` flag.

request
-------

.. code-block:: bash

   getscipapers request --doi 10.1000/xyz123 --service nexus

Coordinates community requests through Nexus, AbleSci, SciNet, Wosonhj, or
Facebook when immediate downloads are not available. ``--doi`` accepts a single
DOI, a delimited list, a text file, or a blob of text to scan; ``--service``
accepts one name, several names, or ``all``.

checkin
-------

.. code-block:: bash

   getscipapers checkin ablesci

Runs daily check-in flows that grant credits on supported services. The
services are positional arguments, so ``getscipapers checkin ablesci wosonhj``
and ``getscipapers checkin all`` are both valid.

Other Modules
-------------

Specialized helpers such as ``remove_metadata`` and ``upload`` can be invoked in
the same pattern. Run ``getscipapers <module> --help`` to view module-specific
options.

zlib
----

.. code-block:: bash

   getscipapers zlib --search "deep learning"

Searches Z-Library for books and optionally downloads them. Key options:

* ``--login``: log in using saved credentials (prompts if missing unless ``--non-interactive``).
* ``--credentials``: load a JSON credentials file and save it to the default location.
* ``--clear-credentials``: delete saved Z-Library credentials.
* ``--non-interactive``: do not prompt for credentials; fail fast if missing.
* ``--search`` / ``--download``: search and optionally download selected books.
* ``--search-limit``: cap the number of search results.
* ``--popular`` / ``--recent``: browse popular or recently added titles, with
  ``--popular-language`` to restrict the popular list.
* ``--user-info``: print the account status and remaining download quota.
