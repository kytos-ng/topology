########
Overview
########

**WARNING: As previously announced on our communication channels, the Kytos
project will enter the "shutdown" phase on May 31, 2021. After this date,
only critical patches (security and core bug fixes) will be accepted, and the
project will be in "critical-only" mode for another six months (until November
30, 2021). For more information visit the FAQ at <https://kytos.io/faq>. We'll
have eternal gratitude to the entire community of developers and users that made
the project so far.**

|License| |Build| |Coverage| |Quality|

.. attention::

    THIS NAPP IS STILL EXPERIMENTAL AND IT'S EVENTS, METHODS AND STRUCTURES MAY
    CHANGE A LOT ON THE NEXT FEW DAYS/WEEKS, USE IT AT YOUR OWN DISCERNEMENT

This NApp is responsible for tracking the network topology and supplying
network topology information to any NApp that requires it.

This NApp intends to be protocol agnostic. Therefore, if you want to provide
network topology data from any network protocol, check the listened events
section and generate them from your NApp.

##########
Installing
##########

All of the Kytos Network Applications are located in the NApps online
repository. To install this NApp, run:

.. code:: shell

   $ kytos napps install kytos/topology

############
Requirements
############

- kytos/of_core
- kytos/of_lldp
- kytos/storehouse

###########
Configuring
###########

You have few options to configure the behaviour of this NApp in the
`settings.py` file. Please take a look in this file.

You can customize circuits in the topology using a JSON configuration file. See
`etc/circuits.json.sample` for an example.

Circuits can have a name, a list of hops and as many numeric custom properties
as the user wants.

We are working to deliver methods and resources to extend the custom properties
in the future.

######
Events
######

********
Listened
********

.*.switch.new
==================
Event reporting that a new switch was created/added on the network.

Content
-------

.. code-block:: python3

   {
     'switch': <Switch object>  # kytos.core.switch.Switch class
   }

.*.switch.port.created
======================
Event reporting that a port was created/added in the switch/datapath.

Content
-------

.. code-block:: python3

   {
     'switch': <switch id>,
     'port': <port number>,
     'port_description': {<description of the port>}  # port description dict
   }

.*.switch.port.modified
=======================
Event reporting that a port was modified in the datapath.

Content
-------

.. code-block:: python3

   {
     'switch': <switch id>,
     'port': <port number>,
     'port_description': {<description of the port>}  # port description dict
   }

.*.switch.port.deleted
======================
Event reporting that a port was deleted from the datapath.

Content
-------

.. code-block:: python3

   {
     'switch': <switch id>,
     'port': <port number>,
     'port_description': {<description of the port>}  # port description dict
   }

.*.interface.is.nni
===================
Event reporting that two interfaces were identified as NNI interfaces.

Content
-------

.. code-block:: python3

   {
     'interface_a': {
        'switch': <switch id>,
        'port': <port number>
     },
     'interface_b': {
        'switch': <switch id>,
        'port': <port number>
     }
   }

.*.reachable.mac
================
Event reporting that a mac address is reachable from a specific switch/port.

Content
-------

.. code-block:: python3

    {
        'switch': <switch id>,
        'port': <port number>,
        'reachable_mac': <mac address>
    }

*********
Generated
*********

kytos/topology.updated
======================
Event reporting that the topology was updated. It contains the most updated
topology.

Content
-------

.. code-block:: python3

   {
     'topology': <Topology object>
   }

kytos/topology.switch.enabled
=============================
Event reporting that the switch was enabled. It contains the switch id.

Content
-------

.. code-block:: python3

   {
     'dpid': <switch.id>
   }

kytos/topology.switch.disabled
==============================
Event reporting that the switch was disabled. It contains the switch id.

Content
-------

.. code-block:: python3

   {
     'dpid': <switch.id>
   }

kytos/topology.link.up
======================
Event reporting that the link was changed to 'up'. It contains the link instance.

Content
-------

.. code-block:: python3

   {
     'link': <Link object>
   }

kytos/topology.link.down
========================
Event reporting that the link was changed to 'down'. It contains the link instance.

Content
-------

.. code-block:: python3

   {
     'link': <Link object>
   }

########
Rest API
########

You can find a list of the available endpoints and example input/output in the
'REST API' tab in this NApp's webpage in the `Kytos NApps Server
<https://napps.kytos.io/kytos/topology>`_.

.. |License| image:: https://img.shields.io/github/license/kytos/kytos.svg
   :target: https://github.com/kytos/topology/blob/master/LICENSE
.. |Build| image:: https://scrutinizer-ci.com/g/kytos/topology/badges/build.png?b=master
  :alt: Build status
  :target: https://scrutinizer-ci.com/g/kytos/topology/?branch=master
.. |Coverage| image:: https://scrutinizer-ci.com/g/kytos/topology/badges/coverage.png?b=master
  :alt: Code coverage
  :target: https://scrutinizer-ci.com/g/kytos/topology/?branch=master
.. |Quality| image:: https://scrutinizer-ci.com/g/kytos/topology/badges/quality-score.png?b=master
  :alt: Code-quality score
  :target: https://scrutinizer-ci.com/g/kytos/topology/?branch=master
.. |FAQ| replace:: *FAQ*
.. _FAQ: http://#