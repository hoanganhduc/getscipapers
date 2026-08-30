Docker Compose Guide
====================

``getscipapers`` reads the Nexus/STC index over an IPFS gateway. Running the two
as a Compose stack keeps the gateway beside the application, so neither has to
be installed on the host.

The stack is defined on the ``docker`` branch, alongside the ``Dockerfile`` that
produces the published image::

   git clone -b docker https://github.com/hoanganhduc/getscipapers.git getscipapers-docker
   cd getscipapers-docker

Prerequisites
-------------

* `Docker <https://docs.docker.com/get-docker/>`_ with the
  `Compose plugin <https://docs.docker.com/compose/install/>`_.
* Free disk for the IPFS datastore. Kubo caps it at 10 GB, but only enforces
  the cap when garbage collection is enabled, which it is not by default --
  see :doc:`ipfs_optimization`.

Quick Start
-----------

1. Prepare the configuration directory
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The stack mounts a host directory at the location the CLI reads its
configuration from, so credentials survive container restarts:

.. code-block:: bash

   mkdir -p config/getpapers downloads
   cp sample_credentials.json config/getpapers/config.json
   chmod 600 config/getpapers/config.json

Edit ``config/getpapers/config.json`` and fill in the keys the services you use
require. ``sample_credentials.json`` lists every key the bundled modules read;
leaving a key empty is fine. See :doc:`configuration` for what each one does.

The file name matters. ``getpapers`` reads
``~/.config/getscipapers/getpapers/config.json``, which the mount below places
inside the container.

2. Start the services
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   docker compose up -d

The first start downloads the IPFS repository and takes a few minutes to find
peers. ``docker compose logs -f ipfs`` shows progress; the gateway is ready once
the daemon prints its listening addresses.

3. Run commands
~~~~~~~~~~~~~~~

.. code-block:: bash

   docker compose exec getscipapers getscipapers --list

   docker compose exec getscipapers getscipapers getpapers \
       --search "machine learning" --limit 5

   docker compose exec getscipapers getscipapers getpapers \
       --doi 10.1371/journal.pone.0245581

Downloads land in ``./downloads`` on the host.

4. Stop the services
~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   docker compose down          # keeps the IPFS datastore
   docker compose down -v       # also discards it

What the stack defines
----------------------

IPFS service
~~~~~~~~~~~~

* Image ``ipfs/kubo:latest``, with the datastore in a named volume so it
  survives ``docker compose down``.
* ``IPFS_PROFILE=server`` suppresses local-network peer discovery, which is the
  right default on a hosted machine and harmless on a laptop.
* Port ``4001`` is published on all interfaces, because peer connectivity
  depends on it. The gateway (``8080``) and the API (``5001``) are bound to
  ``127.0.0.1`` — the API port grants full control of the node and must not be
  reachable from outside the host.
* Kubo does not read datastore or reprovider settings from the environment.
  Anything beyond the profile is applied with ``ipfs config``; see
  :doc:`ipfs_optimization`.
* A healthcheck runs ``ipfs id``, so ``docker compose ps`` reports when the
  daemon is ready rather than merely started.

getscipapers service
~~~~~~~~~~~~~~~~~~~~

* Image ``ghcr.io/hoanganhduc/getscipapers:latest``, rebuilt from the ``docker``
  branch.
* ``GETSCIPAPERS_IPFS_HTTP_BASE_URL=http://ipfs:8080`` points the Nexus/STC
  search at the gateway service. Without it the search falls back to
  ``http://127.0.0.1:8080``, which inside the container is the container itself.
* ``./config`` is mounted at ``/home/vscode/.config/getscipapers`` and
  ``./downloads`` at ``/home/vscode/Downloads/getscipapers``. The image runs as
  the ``vscode`` user, so both paths are under that home directory.
* The container idles under ``tail -f /dev/null``; work is done through
  ``docker compose exec``.
* The published image is built for ``linux/amd64``. Running it on an arm64
  host, such as Apple Silicon or an ARM server, needs binfmt emulation;
  without it the container restarts with exit status 255.

Both services share a bridge network, which is what lets the application resolve
``ipfs`` as a hostname.

Troubleshooting
---------------

**Nexus/STC search reports no results and the gateway looks idle.**
Confirm the application can reach the gateway:

.. code-block:: bash

   docker compose exec getscipapers curl -sS -o /dev/null -w '%{http_code}\n' \
       http://ipfs:8080/ipfs/bafkqaaa

``bafkqaaa`` is the empty file, encoded in the address itself, so a healthy
gateway answers ``200`` without going to the network. A connection error means
the services are not on the same network; a hang usually means the daemon is
still starting. Note that the gateway does not serve ``/api/v0`` -- that is the
API on port ``5001``.

**Credentials prompt on every command.**
The configuration is not where the CLI looks. Check the path inside the
container:

.. code-block:: bash

   docker compose exec getscipapers ls -l \
       /home/vscode/.config/getscipapers/getpapers/config.json

**Permission denied writing downloads.**
The host directory must be writable by UID 1000, which is the ``vscode`` user in
the image:

.. code-block:: bash

   sudo chown -R 1000:1000 downloads config

**Datastore keeps growing.**
The cap is a Kubo setting rather than a Compose one. :doc:`ipfs_optimization`
covers raising, lowering, and reclaiming it.

Backing up the datastore
------------------------

The datastore is a named volume, so it is not in the project directory:

.. code-block:: bash

   docker run --rm -v getscipapers-docker_ipfs_data:/data -v "$PWD":/backup \
       alpine tar czf /backup/ipfs-data.tar.gz -C /data .

The volume name is prefixed with the project directory name; ``docker volume
ls`` shows the actual one.

Security notes
--------------

* Keep ``config/getpapers/config.json`` at mode ``600``. It holds API keys in
  plain text, and the CLI warns when it is readable by others.
* Add ``config/`` and ``downloads/`` to any ignore file before committing work
  in a clone of the ``docker`` branch.
* Leave the Kubo API bound to ``127.0.0.1``. Anything that reaches port ``5001``
  can reconfigure the node and read everything it stores.
