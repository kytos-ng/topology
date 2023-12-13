|Stable| |Tag| |License| |Build| |Coverage| |Quality|

.. raw:: html

  <div align="center">
    <h1><code>kytos/topology</code></h1>

    <strong>NApp that manages the network topology</strong>

    <h3><a href="https://kytos-ng.github.io/api/topology.html">OpenAPI Docs</a></h3>
  </div>


Overview
========

This NApp is responsible for tracking the network topology and supplying
network topology information to any NApp that requires it.

This NApp intends to be protocol agnostic. Therefore, if you want to provide
network topology data from any network protocol, check the listened events
section and generate them from your NApp.

Installing
==========

To install this NApp, first, make sure to have the same venv activated as you have ``kytos`` installed on:

.. code:: shell

   $ git clone https://github.com/kytos-ng/topology.git
   $ cd topology
   $ python setup.py develop

Requirements
============

- `kytos/of_core <https://github.com/kytos-ng/of_core.git>`_
- `MongoDB <https://github.com/kytos-ng/kytos#how-to-use-with-mongodb>`_

Events
======

Subscribed
----------

- ``.*.switch.(new|reconnected)``
- ``.*.connection.lost``
- ``.*.switch.interface.created``
- ``.*.switch.interface.deleted``
- ``.*.switch.interface.link_up``
- ``.*.switch.interface.link_down``
- ``.*.switch.port.created``
- ``.*.switch.port.modified``
- ``.*.switch.port.deleted``
- ``.*.interface.is.nni``
- ``.*.network_status.updated``
- ``kytos/core.interface_tags``
- ``kytos/maintenance.start_link``
- ``kytos/maintenance.end_link``
- ``kytos/maintenance.start_switch``
- ``kytos/maintenance.end_switch``
- ``kytos/.*.liveness.(up|down)``
- ``kytos/.*.liveness.disabled``
- ``kytos/topology.notify_link_up_if_status``


Published
---------

kytos/topology.topology_loaded
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Event reporting that the topology was loaded from the database. It contains the
most updated topology.

Content:

.. code-block:: python3

   {
     'topology': <Topology object>,
     'failed_switches': {<description of failed switches>},
     'failed_links': {<description of failed links>}
   }

kytos/topology.updated
~~~~~~~~~~~~~~~~~~~~~~

Event reporting that the topology was updated. It contains the most updated
topology.

Content:

.. code-block:: python3

   {
     'topology': <Topology object>
   }

kytos/topology.switch.enabled
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Event reporting that the switch was enabled. It contains the switch id.

Content:

.. code-block:: python3

   {
     'dpid': <switch.id>
   }

kytos/topology.switch.disabled
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Event reporting that the switch was disabled. It contains the switch id.

Content:

.. code-block:: python3

   {
     'dpid': <switch.id>
   }

kytos/topology.link.up
~~~~~~~~~~~~~~~~~~~~~~

Event reporting that the link was changed to 'up'. It contains the link instance.

Content:

.. code-block:: python3

   {
     'link': <Link object>
   }


kytos/topology.link.down
~~~~~~~~~~~~~~~~~~~~~~~~

Event reporting that the link was changed to 'down'. It contains the link instance.

Content:

.. code-block:: python3

   {
     'link': <Link object>
   }


kytos/topology.(switches|interfaces|links).(added|removed)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Event reporting metadata changes. 

Content:

.. code-block:: python3

   {
     'switch|interface|link': <object>,
     'metadata': object's metadata dict
   }


.. |License| image:: https://img.shields.io/github/license/kytos-ng/kytos.svg
   :target: https://github.com/kytos-ng/topology/blob/master/LICENSE
.. |Build| image:: https://scrutinizer-ci.com/g/kytos-ng/topology/badges/build.png?b=master
  :alt: Build status
  :target: https://scrutinizer-ci.com/g/kytos-ng/topology/?branch=master
.. |Coverage| image:: https://scrutinizer-ci.com/g/kytos-ng/topology/badges/coverage.png?b=master
  :alt: Code coverage
  :target: https://scrutinizer-ci.com/g/kytos-ng/topology/?branch=master
.. |Quality| image:: https://scrutinizer-ci.com/g/kytos-ng/topology/badges/quality-score.png?b=master
  :alt: Code-quality score
  :target: https://scrutinizer-ci.com/g/kytos-ng/topology/?branch=master
.. |Stable| image:: https://img.shields.io/badge/stability-stable-green.svg
   :target: https://github.com/kytos-ng/topology
.. |Tag| image:: https://img.shields.io/github/tag/kytos-ng/topology.svg
   :target: https://github.com/kytos-ng/topology/tags


kytos/topology.notify_link_up_if_status
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Event reporting that the link was changed to 'down'. It contains the link instance.

Content:

.. code-block:: python3

   {
     'reason': 'link enabled'
     'link': <Link object>
   }


kytos/topology.link.deleted
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Event reporting that a link was deleted. It contains the link instance.

Content:

.. code-block:: python3
  {
    'link': <Link object>
  }


kytos/topology.switch.deleted
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Event reporting that a switch was deleted. It contains the switch instance.

Content:

.. code-block:: python3
  {
    'switch': <switch object>
  }
