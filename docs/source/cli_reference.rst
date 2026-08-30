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
* ``--anna-md5``: hand Anna's Archive a known md5 so it can skip DOI
  resolution entirely. Otherwise the md5 cache and then LibGen are consulted
  before any Anna's Archive route runs.
* ``--anna-scidb`` / ``--no-anna-browser``: arm or disable the Anna's Archive
  routes described below.

The contact address several APIs require comes from the credentials file or
``GETSCIPAPERS_EMAIL``; there is no ``--email`` flag.

``--db libgen`` finds files more reliably than it delivers them. A DOI resolves
to a catalog entry and an md5, and small transfers complete byte-exact:
downloads of 82 kB, 407 kB and 922 kB each arrived at their full declared
length.

A 48 MB file did not. Every attempt broke mid-stream after a few megabytes
had arrived, at a point that moved between runs, and once every mirror had
failed the run printed ``PDF file is not available on LibGen``. The server
reported the right ``Content-Length`` each time, so the catalog entry and the
link were sound and only the byte transfer broke. Exactly one large file was
tested, so where the behaviour changes, and why, is not known.

anna
----

.. code-block:: bash

   getscipapers anna --doi 10.1038/nature12373

Downloads a document from Anna's Archive. Anna's Archive puts a DDoS-Guard
challenge in front of every content path, so the module reaches the same files
through the routes that are not challenge-gated, and falls back to a real
browser when no account is configured:

.. list-table::
   :header-rows: 1
   :widths: 8 34 22 18 18

   * - Route
     - How it fetches
     - Requires
     - Quota
     - Latency
   * - R1
     - the record JSON, then an IPFS gateway
     - md5 and a paid account
     - none
     - ~2s
   * - R2
     - the fast-download API
     - md5 and a paid account
     - 25-50 per day
     - ~1s
   * - R4
     - the SciDB page with the account cookie
     - a DOI and a tier-2 account
     - none
     - ~1s
   * - R5
     - Chromium solving the challenge
     - nothing
     - none
     - ~40s when it solves

R1 and R2 are addressed by md5, not by DOI, so a DOI must be resolved first.
The ``anna`` command resolves one from ``--md5``, from the local md5 cache, or
through R4 and R5. Under ``getpapers --db anna`` there is one more resolver:
LibGen indexes the same files, so it is asked for the md5 before any Anna's
Archive route runs, and a hit puts a cold DOI straight onto the quota-free R1.
A paid membership on its own does not make a cold DOI resolvable:

.. list-table::
   :header-rows: 1
   :widths: 46 12 42

   * - Situation
     - Works?
     - Route taken
   * - ``--md5 <hex>`` supplied
     - yes
     - R1, then R2
   * - the DOI is already in the md5 cache
     - yes
     - R1
   * - cold DOI, ``--scidb`` armed
     - yes
     - R4
   * - cold DOI resolved by LibGen (``getpapers`` only)
     - yes
     - R1
   * - cold DOI, ``--scidb`` not given
     - not reliably
     - R5, which never needed the key

Because R4 and R5 both write the md5 cache, a second fetch of the same DOI
drops to the quota-free R1.

Key options:

* ``--doi`` / ``--md5``: what to fetch. An md5 skips DOI resolution.
* ``--key``: the account secret, or ``-`` to read it from standard input.
  Prefer ``GETSCIPAPERS_ANNA_SECRET_KEY`` or a credentials file: a key given on
  the command line is visible to every user on the machine.
* ``--credentials``: a JSON file holding ``{"anna_secret_key": "..."}``.
* ``--scidb``: enable R4. Anna's Archive qualifies the no-browser-checks perk
  with "Only for normal browser use. For scripts please use our metadata
  torrents.", so it is off by default and enabling it risks the account.
* ``--no-browser``: disable R5, for hosts with no display.
* ``--user-info``: report whether the configured key logs in.
* ``--md5-cache-clear`` / ``--clear-cache``: drop the cached DOI-to-md5 map or
  the whole cache directory.

R5 launches Chromium itself rather than through chromedriver, since a
chromedriver-launched browser fails the challenge. It needs ``chromium`` and
``chromedriver``, plus ``xvfb-run`` on a Linux host with no display; headless
Chromium cannot pass the challenge and is never used.

Whether R5 solves at all also depends on the address the request leaves from.
DDoS-Guard can hold that address, and on a held address the page title stays at
``DDoS-Guard`` for the whole 120-second budget and the run ends without a file.
The module adds a line naming that case after the timeout message, so a held
address is distinguishable from a slow one.

That line reports the address as held at a manual captcha, and says a longer
timeout will not clear the hold and that a different network path is needed. A
different path has not been seen to clear it here: three runs on this host, one
of them through a proxy, each spent the full budget on the check. The same route
on the same host solved in about 42 seconds when the module was built.

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
