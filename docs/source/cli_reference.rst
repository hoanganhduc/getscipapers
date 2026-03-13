CLI Reference
=============

``getscipapers`` acts as a dispatcher for module-based subcommands. The most
commonly used modules are summarized below.

getpapers
---------

.. code-block:: bash

   getscipapers getpapers --doi <doi> --email <you@example.com> --download-dir <path>

Searches for papers using Crossref and Unpaywall, optionally requesting downloads
from Nexus. Key options:

* ``--doi`` or ``--query``: choose between direct DOI lookup or keyword search.
* ``--email``: contact email required by several APIs.
* ``--non-interactive``: fail fast if credentials are missing.

request
-------

.. code-block:: bash

   getscipapers request --title "Graph Representation Learning" --nexus

Coordinates community requests through Nexus, AbleSci, SciNet, or Wosonhj when
immediate downloads are not available.

checkin
-------

.. code-block:: bash

   getscipapers checkin --service ablesci

Runs daily check-in flows that grant credits on supported services.

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
