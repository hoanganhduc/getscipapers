Docker Compose Guide
=====================

Overview
--------

This guide explains how to run getscipapers with IPFS Kubo using Docker Compose.
Docker Compose simplifies managing multi-container applications and ensures
proper service dependencies and networking.

Prerequisites
-------------

- `Docker <https://docs.docker.com/get-docker/>`_ installed
- `Docker Compose <https://docs.docker.com/compose/install/>`_ installed
- Basic understanding of Docker concepts

Quick Start
-----------

1. Use the provided docker-compose.yml
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The repository includes a ready-to-use ``docker-compose.yml`` file with sensible
defaults for Nexus Search access. Key optimizations:

- **Storage limit**: 20GB for cached papers
- **Reduced DHT traffic**: 24-hour reprovider interval
- **Automatic migration**: Enabled for version upgrades

View the complete configuration: `docker-compose.yml <../docker-compose.yml>`_

2. Create credentials file (optional)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Create a ``credentials.json`` file using the provided example:

.. code-block:: bash

   cp credentials.example.json credentials.json
   # Edit credentials.json with your API keys

Or create it manually with this structure:

.. code-block:: json

   {
     "email": "your-email@example.com",
     "elsevier_api_key": "your-elsevier-key",
     "wiley_tdm_token": "your-wiley-token",
     "ieee_api_key": "your-ieee-key"
   }

See ``credentials.example.json`` for a ready-to-use template.

3. Start the services
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   docker-compose up -d

4. Run getscipapers commands
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Execute commands in the running container
   docker-compose exec getscipapers getscipapers --help

   # Search for papers
   docker-compose exec getscipapers getscipapers getpapers --search "machine learning" --limit 5

   # Download specific DOI
   docker-compose exec getscipapers getscipapers getpapers --doi 10.1371/journal.pone.0245581

5. Stop the services
~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   docker-compose down

Configuration Options
---------------------

The default configuration balances performance with resource usage:

Key Settings
~~~~~~~~~~~~

- **``IPFS_DATASTORE_STORAGEMAX=20GB``**: Sufficient for cached papers without excessive disk usage
- **``IPFS_REPROVIDER_INTERVAL=24h``**: Reduces DHT traffic while still contributing to network

Design Philosophy
~~~~~~~~~~~~~~~~~

This configuration is designed for users who:

- Want to access Nexus Search database
- May not be familiar with IPFS/DHT concepts
- Have limited resources (disk space, bandwidth)
- Still want to contribute to data availability

**Примечание**: Эти настройки оптимизированы для доступа к Nexus Search, а не для общего использования IPFS.

For Advanced Users
~~~~~~~~~~~~~~~~~~

If you have more resources and want to optimize further, see the
`optimization script <../scripts/optimize-ipfs.sh>`_ or modify the
``docker-compose.yml`` file directly.

IPFS Configuration
~~~~~~~~~~~~~~~~~~

The IPFS container is configured with optimized settings for accessing large
datasets (like Nexus Search):

- **Server profile**: Optimized for server environments (``IPFS_PROFILE=server``)
- **Connection management**:

  - ``IPFS_SWARM_CONNMGR_HIGHWATER=200`` - Max connections
  - ``IPFS_SWARM_CONNMGR_LOWWATER=50`` - Min connections to maintain

- **Storage optimization**:

  - ``IPFS_DATASTORE_STORAGEMAX=20GB`` - Storage limit optimized for paper caching
  - ``IPFS_DATASTORE_STORAGEGCWATERMARK=95`` - GC triggers at 95% usage

- **Reprovider settings**:

  - ``IPFS_REPROVIDER_INTERVAL=12h`` - Reduced frequency of content re-advertisement
  - ``IPFS_REPROVIDER_STRATEGY=pinned`` - Only re-advertise pinned content

- **Daemon options**:

  - ``--migrate=true`` - Automatic migration of repo format
  - ``--agent-version-suffix=docker`` - Identify as Docker instance
  - ``--enable-gc=true`` - Enable garbage collection (with optimized settings)

- **Persistent storage**: Data persists across container restarts
- **Required ports**: 4001 (P2P), 8080 (HTTP), 5001 (API)
- **Automatic restart**: Container restarts unless explicitly stopped

getscipapers Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Volume mounts**:

  - ``./downloads``: Host directory for downloaded papers
  - ``./config``: Host directory for configuration files
  - ``./credentials.json``: Read-only credentials file

- **Environment variables**:

  - ``GETSCIPAPERS_IPFS_HTTP_BASE_URL``: Points to the IPFS container

- **Interactive terminal**: Enabled for CLI interaction

Network Configuration
~~~~~~~~~~~~~~~~~~~~~

- **Custom bridge network**: Isolates getscipapers services
- **Service discovery**: Containers can reference each other by service name
- **Internal DNS**: ``ipfs`` hostname resolves to the IPFS container

Advanced Usage
--------------

Multiple getscipapers Instances
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For parallel processing:

.. code-block:: yaml

   services:
     getscipapers-worker-1:
       image: ghcr.io/hoanganhduc/getscipapers:latest
       container_name: getscipapers-worker-1
       # ... configuration
       environment:
         - GETSCIPAPERS_WORKER_ID=1

     getscipapers-worker-2:
       image: ghcr.io/hoanganhduc/getscipapers:latest
       container_name: getscipapers-worker-2
       # ... configuration
       environment:
         - GETSCIPAPERS_WORKER_ID=2

Optional IPFS Optimizations
---------------------------

Optimization Script
~~~~~~~~~~~~~~~~~~~

For users with more resources (disk space, bandwidth), optional optimizations
are available:

.. code-block:: bash

   # Make script executable
   chmod +x scripts/optimize-ipfs.sh

   # Run interactive optimization script
   ./scripts/optimize-ipfs.sh

The script offers three levels:

1. **Light** (50GB storage) - Recommended for most users
2. **Medium** (100GB storage) - For better performance
3. **Advanced** (200GB storage) - For dedicated nodes

When to Optimize
~~~~~~~~~~~~~~~~

Consider using optimization script if you:

- Frequently access Nexus Search
- Have ample disk space (>50GB free)
- Experience slow paper downloads
- Want to contribute more to data availability as a dedicated node

Default Settings
~~~~~~~~~~~~~~~~

The default configuration (20GB storage) is designed to:

- Work well for occasional users
- Use minimal disk space
- Still contribute to network
- Be safe for all hardware

Troubleshooting
---------------

Common Issues
~~~~~~~~~~~~~

1. **IPFS container not starting**:

   .. code-block:: bash

      # Check logs
      docker-compose logs ipfs
      
      # Check if ports are available
      netstat -tulpn | grep -E ':(4001|8080|5001)'

2. **getscipapers cannot connect to IPFS**:

   .. code-block:: bash

      # Test connectivity
      docker-compose exec getscipapers curl -v http://ipfs:8080
      
      # Check IPFS API
      docker-compose exec ipfs ipfs id

3. **Volume permissions**:

   .. code-block:: bash

      # Ensure host directories have correct permissions
      chmod 755 ./downloads ./config

Data Persistence
~~~~~~~~~~~~~~~~

- **IPFS data**: Stored in Docker volume ``ipfs_data``
- **Downloads**: Stored in host directory ``./downloads``
- **Configuration**: Stored in host directory ``./config``

To backup IPFS data:

.. code-block:: bash

   # Create backup
   docker run --rm -v ipfs_data:/data -v $(pwd):/backup alpine tar czf /backup/ipfs_backup.tar.gz /data

   # Restore from backup
   docker run --rm -v ipfs_data:/data -v $(pwd):/backup alpine sh -c "rm -rf /data/* && tar xzf /backup/ipfs_backup.tar.gz -C /"

Security Considerations
-----------------------

1. **Credentials**: Store credentials in a separate file with restricted permissions
2. **Network isolation**: Use the custom bridge network to limit exposure
3. **Volume permissions**: Ensure only necessary directories are mounted
4. **Image sources**: Use official images from trusted sources
5. **Regular updates**: Keep Docker images updated to latest versions

Performance Tips
----------------

1. **SSD storage**: Use SSD for volume storage for better IPFS performance
2. **Memory allocation**: Allocate sufficient memory for IPFS (2GB+ recommended)
3. **CPU allocation**: IPFS benefits from multiple CPU cores
4. **Network optimization**: Use host networking if low latency is critical
5. **Cache tuning**: Adjust IPFS cache sizes based on available memory

References
----------

- `Docker Compose Documentation <https://docs.docker.com/compose/>`_
- `IPFS Kubo Docker Image <https://hub.docker.com/r/ipfs/kubo>`_
- `IPFS Documentation <https://docs.ipfs.tech/>`_
- :doc:`ipfs_optimization`