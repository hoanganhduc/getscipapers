IPFS Gateway Tuning
===================

``getscipapers`` uses IPFS in one direction only: it reads the Nexus/STC index
through a gateway. It pins nothing and serves nothing of its own. Kubo's
defaults assume a node that both fetches and publishes, so a few settings are
worth revisiting for a read-only node.

Everything here is optional. The stack in :doc:`docker_compose` works without
it.

Applying settings
-----------------

Kubo reads its configuration from the repository, not from the environment. The
one exception is ``IPFS_PROFILE``, which the image applies on first
initialization. Everything else is set with ``ipfs config`` and takes effect
after a restart:

.. code-block:: bash

   docker compose exec ipfs ipfs config --json <Key> <value>
   docker compose restart ipfs

``ipfs config show`` prints the current repository configuration, and
``ipfs config profile apply <name>`` applies a named profile to an existing
repository. Profiles are not idempotent in both directions -- ``ipfs config
profile apply`` stores a backup of the previous configuration and names it in
its output.

Disk
----

The datastore grows without limit as content is fetched. ``Datastore.StorageMax``
caps it, but the cap only binds when garbage collection runs, and the published
image starts the daemon without ``--enable-gc``.

Enable periodic collection and set a cap that suits the host:

.. code-block:: bash

   docker compose exec ipfs ipfs config Datastore.StorageMax 20GB
   docker compose exec ipfs ipfs config Datastore.GCPeriod 12h

Then add ``--enable-gc`` to the daemon by overriding the command in
``docker-compose.yml``:

.. code-block:: yaml

   services:
     ipfs:
       command: ["daemon", "--migrate=true", "--enable-gc"]

A one-off collection is available at any time, and reports what it removed::

   docker compose exec ipfs ipfs repo gc

``ipfs repo stat`` shows the current size against the cap. Collection discards
unpinned blocks, so an index chunk that is dropped is simply fetched again on
the next search.

Content providing
-----------------

By default a Kubo node announces every block it holds to the DHT, which for a
node that only reads is work with no consumer. Restricting announcements to
pinned content removes most of it:

.. code-block:: bash

   docker compose exec ipfs ipfs config Provide.Strategy pinned

If the node pins nothing, this reduces announcement traffic to nearly zero. The
cost is that other peers cannot fetch the blocks this node happens to hold; for
a private client that is not a service anyone depends on.

.. warning::

   Older guides set ``Reprovider.Strategy`` instead. ``Provide.Strategy``
   replaced it in Kubo 0.38, and 0.43 removed the ``Reprovider`` section
   outright: a node whose configuration still carries it **refuses to start**,
   reporting ``deprecated configuration detected``.

   Recovering needs a one-off container, because the daemon is down and
   ``docker compose exec`` has nothing to attach to::

      docker compose stop ipfs
      docker compose run --rm ipfs config --json Reprovider null
      docker compose run --rm ipfs config Provide.Strategy pinned
      docker compose start ipfs

   ``docker compose run`` starts a second container on the same volume, so it
   edits the same repository the daemon will read on the next start.

   The bundled ``scripts/optimize-ipfs.sh`` picks the key by asking the node
   which schema it has, so it is safe on either side of the change.

Lookup latency
--------------

The accelerated DHT client keeps a fuller routing table, so content lookups
resolve in fewer hops:

.. code-block:: bash

   docker compose exec ipfs ipfs config --json Routing.AcceleratedDHTClient true

It buys latency with memory and bandwidth -- the node sweeps the DHT
periodically to maintain the table, and start-up takes longer before the first
lookup succeeds. It suits a long-running node on a machine with memory to spare,
not a laptop that starts the stack for one search.

Constrained hosts
-----------------

On a small machine, cap the connection manager instead:

.. code-block:: bash

   docker compose exec ipfs ipfs config --json Swarm.ConnMgr.HighWater 40
   docker compose exec ipfs ipfs config --json Swarm.ConnMgr.LowWater 20

Kubo's own ``lowpower`` profile sets the same two limits in one step::

   docker compose exec ipfs ipfs config profile apply lowpower

On Kubo 0.43 it also turns off the relay service and sets ``Routing.Type`` to
``autoclient``, which is why it must not be combined with the accelerated DHT
client above -- the profile is asking for a smaller routing table and the client
for a fuller one. Older descriptions of the profile mention that it disables
reproviding as well; it no longer does, so set ``Provide.Strategy`` separately.

Fewer peers means fewer places to find a block, so searches may take longer to
resolve.

Checking the node
-----------------

.. code-block:: bash

   docker compose exec ipfs ipfs id                 # identity and listen addresses
   docker compose exec ipfs ipfs swarm peers | wc -l  # peer count
   docker compose exec ipfs ipfs repo stat          # datastore size
   docker compose exec ipfs ipfs stats bw           # bandwidth totals

A healthy node holds a few dozen peers or more. A node stuck at zero peers is
usually blocked outbound on port ``4001``, or is behind a NAT that has not been
traversed; the gateway will appear to hang rather than fail.

Recovering from a bad configuration
-----------------------------------

Settings live in the named volume, so a bad edit survives ``docker compose
down``. Restore the defaults by re-applying a profile, or discard the repository
entirely and let the next start rebuild it:

.. code-block:: bash

   docker compose down -v
   docker compose up -d

Rebuilding costs only re-fetch time; nothing ``getscipapers`` needs is stored
only on this node.

References
----------

* `Kubo configuration reference <https://github.com/ipfs/kubo/blob/master/docs/config.md>`_
* `Kubo configuration profiles <https://github.com/ipfs/kubo/blob/master/docs/config.md#profiles>`_
