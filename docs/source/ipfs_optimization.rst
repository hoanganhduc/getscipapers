IPFS Configuration Reference
=============================

This document explains the IPFS configuration used with getscipapers
for accessing Nexus Search database.
The configuration balances performance with resource usage for typical users.

Default Configuration
---------------------

docker-compose.yml Settings
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   environment:
     - IPFS_DATASTORE_STORAGEMAX=20GB  # Enough for cached papers
     - IPFS_REPROVIDER_INTERVAL=24h    # Reduced DHT traffic

Why These Settings?
~~~~~~~~~~~~~~~~~~~

**20GB Storage Limit**:

- Typical scientific paper: 1-5MB
- 20GB can cache ~4,000-20,000 papers
- Prevents unlimited disk usage
- Still useful for frequent access

**24-hour Reprovider Interval**:

- Reduces network traffic
- Still contributes to data availability
- Balanced approach for casual users

Optional Optimizations
----------------------

Using the Optimization Script
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   ./scripts/optimize-ipfs.sh

Optimization Levels
~~~~~~~~~~~~~~~~~~~

+----------+---------+------------------------------------+
| Level    | Storage | Best For                           |
+==========+=========+====================================+
| Light    | 50GB    | Most users, occasional access      |
+----------+---------+------------------------------------+
| Medium   | 100GB   | Frequent users, better performance |
+----------+---------+------------------------------------+
| Advanced | 200GB   | Dedicated nodes, maximum caching   |
+----------+---------+------------------------------------+

Configuration Details
---------------------

Storage Management
~~~~~~~~~~~~~~~~~~

+--------------------------------+-------------+-------------+--------------------------------+
| Setting                        | Default     | Optimized   | Purpose                        |
+================================+=============+=============+================================+
| ``Datastore.StorageMax``       | 10GB        | 100GB       | Increased cache for Nexus data |
+--------------------------------+-------------+-------------+--------------------------------+
| ``Datastore.StorageGCWatermark`` | 90        | 98          | Less frequent GC               |
+--------------------------------+-------------+-------------+--------------------------------+
| ``Datastore.GCPeriod``         | 1h          | 24h         | Less frequent GC runs          |
+--------------------------------+-------------+-------------+--------------------------------+
| ``Import.UnixFSChunker``       | size-262144 | size-262144 | 256KB chunks for papers        |
+--------------------------------+-------------+-------------+--------------------------------+

Network Optimization
~~~~~~~~~~~~~~~~~~~~

+--------------------------------------+---------+-----------+-----------------------------+
| Setting                              | Default | Optimized | Purpose                     |
+======================================+=========+===========+=============================+
| ``Swarm.ConnMgr.HighWater``          | 200     | 300       | More connections            |
+--------------------------------------+---------+-----------+-----------------------------+
| ``Swarm.ConnMgr.LowWater``           | 50      | 100       | Maintain more connections   |
+--------------------------------------+---------+-----------+-----------------------------+
| ``Swarm.DisableBandwidthMetrics``    | false   | true      | Reduce overhead             |
+--------------------------------------+---------+-----------+-----------------------------+
| ``Bitswap.MaxOutstandingBytesPerPeer`` | 512KB | 1MB       | Better transfer performance |
+--------------------------------------+---------+-----------+-----------------------------+
| ``Bitswap.TargetMessageSize``        | 512KB   | 1MB       | Larger message batches      |
+--------------------------------------+---------+-----------+-----------------------------+

Content Providing (Reader Mode)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

+----------------------------------+---------+-----------+------------------------------+
| Setting                          | Default | Optimized | Purpose                      |
+==================================+=========+===========+==============================+
| ``Provide.DHT.Enabled``          | true    | false     | Don't advertise content      |
+----------------------------------+---------+-----------+------------------------------+
| ``Experimental.OptimisticProvide`` | false | false     | Reduce DHT traffic           |
+----------------------------------+---------+-----------+------------------------------+
| ``Reprovider.Strategy``          | all     | pinned    | Only re-advertise pinned     |
+----------------------------------+---------+-----------+------------------------------+
| ``Reprovider.Interval``          | 12h     | 24h       | Less frequent re-advertising |
+----------------------------------+---------+-----------+------------------------------+

Performance Impact
------------------

Expected Improvements
~~~~~~~~~~~~~~~~~~~~~

1. **Reduced DHT Traffic**: 60-80% reduction
2. **Lower CPU Usage**: 20-30% reduction
3. **Better Cache Hit Rate**: 2-3x improvement
4. **Reduced Network Overhead**: 40-50% reduction

Trade-offs
~~~~~~~~~~

1. **Increased Storage**: 100GB vs 10GB default
2. **Reduced Content Availability**: Node doesn't serve content to others
3. **Slower GC**: Less frequent garbage collection

Monitoring
----------

Key Metrics to Watch
~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Check storage usage
   docker exec ipfs_host ipfs stats repo

   # Check bandwidth usage
   docker exec ipfs_host ipfs stats bw

   # Check connected peers
   docker exec ipfs_host ipfs swarm peers | wc -l

   # Check DHT queries
   docker exec ipfs_host ipfs stats dht

Health Checks
~~~~~~~~~~~~~

.. code-block:: bash

   # Basic health check
   curl -s http://localhost:8080/ipfs/bafkqablimvwgy3y | head -1

   # API health check
   curl -s http://localhost:5001/api/v0/id | jq .ID

Troubleshooting
---------------

Common Issues
~~~~~~~~~~~~~

1. **High Memory Usage**

   .. code-block:: bash

      # Reduce cache size
      docker exec ipfs_host ipfs config Datastore.BloomFilterSize 0

2. **Slow Content Discovery**

   .. code-block:: bash

      # Increase bootstrap peers
      docker exec ipfs_host ipfs bootstrap add /dns4/bootstrap.libp2p.io/tcp/4001/p2p/QmNnooDu7bfjPFoTZYxMNLWUQJyrVwtbZg5gBMjTezGAJN

3. **Connection Issues**

   .. code-block:: bash

      # Check firewall
      sudo ufw allow 4001
      sudo ufw allow 8080
      sudo ufw allow 5001

Recovery
~~~~~~~~

To reset to defaults:

.. code-block:: bash

   # Remove volumes and restart
   docker-compose down -v
   docker-compose up -d ipfs

References
----------

- `IPFS Documentation <https://docs.ipfs.tech/>`_
- `Kubo Configuration <https://github.com/ipfs/kubo/blob/master/docs/config.md>`_
- `IPFS Performance Tuning <https://docs.ipfs.tech/how-to/performance-tuning/>`_
- `Nexus Search Database <https://www.reddit.com/r/science_nexus/>`_