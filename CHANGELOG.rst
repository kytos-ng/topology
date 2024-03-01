#########
Changelog
#########

All notable changes to the ``topology`` project will be documented in this file.

[UNRELEASED] - Under development
********************************

Added
=====
- Added endpoint ``POST v3/interfaces/{interface_id}/tag_ranges`` to set ``tag_ranges`` to interfaces.
- Added endpoint ``DELETE v3/interfaces/{interface_id}/tag_ranges`` to delete ``tag_ranges`` from interfaces.
- Added endpoint ``GET v3/interfaces/{interface_id}/tag_ranges`` to get ``available_tags`` and ``tag_ranges`` from an interface.
- Added endpoint ``GET v3/interfaces/tag_ranges`` to get ``available_tags`` and ``tag_ranges`` from all interfaces.
- Added ``Tag_ranges`` documentation to openapi.yml
- Added API request POST and DELETE to modify ``Interface.tag_ranges``
- Added listener for ``kytos/core.interface_tags`` event to save any changes made to ``Interface`` attributes ``tag_ranges`` and ``available_tags``
- Added script ``special_vlan_allocation.py`` to add ``special_available_tags`` and ``special_tags`` fields to ``interface_details`` collection.
- Added endpoint ``POST v3/interfaces/{interface_id}/special_tags`` to set ``special_tags`` to interfaces.
- Added endpoint ``DELETE v3/links/{link_id}`` to delete a disabled link. To avoid rediscovery, the link needs to be physically disconnected or both interface ends (switches) need to be disabled.
- Added endpoint ``DELETE /v3/switches/{dpid}`` to delete a disabled switch. This endpoint is for decommissioned switches. The switch will get rediscovered if it reconnects to the controller. So, after deleting a switch on ``topology``, you're expected to also remove the TCP connection configuration on the switch.
- Added ``Delete`` button to delete switch in the switch panel UI interface.
- Added ``Delete`` button to delete link in the link panel UI interface.

Deprecated
==========
- Deleted event listener for ``kytos/.*.link_available_tags`` event

Removed
=======

Fixed
=====
- An interface cannot be enabled if its switch is disabled.
- Handled deactivated interfaces when an interface gets created.

Security
========

Changed
=======
- An interface can't be enabled if its switch is disabled.
- A link can't be enabled if its interface is disabled.
- Enabling interface can't not longer enabled its link. To enable a link, the endpoint ``POST v3/links/{link_id}/enable`` should be used.
- If a KytosEvent can't be put on ``buffers.app`` during ``setup()``, it'll make the NApp to fail to start

General Information
===================
- ``scripts/vlan_pool.py`` can be used to change the collection ``interface_details`` to have ``available_tags`` and ``tag_ranges``

[2023.1.0] - 2023-06-26
***********************

Added
=====
 - Info on status and status_reason to UI for Switches and Interfaces
 - Listener for service interruptions through ``topology.interruption.(start|end)``
 - Publishes ``kytos/topology.update`` when changing link metadata

Fixed
=====
- Fixed interface and link activation/deactivation race condition
- Rejected unordered late preempted interface events to avoid state inconsistencies

Changed
=======
- Stopped storing interface and link ``active`` field in the DB
- Removed ``active`` from the application DB models

Removed
=======
- Removed old maintenance listeners ``kytos/maintenance.*``
- Removed ``kytos/topology.get``

General Information
===================
- ``@rest`` endpoints are now run by ``starlette/uvicorn`` instead of ``flask/werkzeug``.
- Added ``scripts/unset_active.py`` to ``$unset`` ``active`` from ``links`` and ``switches`` collections that will no longer be in the database. If you are upgrading to ``2023.1`` you should run this script, however, if you don't, it'll still work as intended since the application won't read from or update these ``active`` values

[2022.3.0] - 2022-12-15
***********************

Added
=====
- Publish event ``kytos/topology.current`` for topology reconciliation
- Subscribed to event ``kytos/topology.get`` to publish the current topology
- Added ``notified_up_at`` internal reserved metadata
- Enabling/disabling a switch or an interface will send ``link_up`` and ``link_down`` notifications

Changed
=======
- Hooked ``link_status_hook_link_up_timer`` to update ``status`` accordingly.

Fixed
=====
- Fixed link up to only notify when ``LINK_UP_TIMER`` has passed
- Load interfaces as inactive
- Created interface should only be activated if it's active
- Fixed ``last_status_is_active`` when both interfaces go down to notify only once

[2022.2.0] - 2022-08-05
***********************

Added
=====
- UI table on ``k-info-panel/switch_info`` to display switch metadata
- UI functionality to add and remove metadata from a switch on ``k-info-panel/switch-info``
- UI table of links to ``k-info-panel/switch_info``
- UI ``k-info-panel/link_info`` to display link attributes
- UI toggle button to enable and disable a switch in the ``k-info-panel/switch_info`` component
- UI accordion to ``k-info-panel/switch_info`` to enable and disable LLDP on interfaces
- UI toggle button to enable and disable a link in the ``k-info-panel/link_info`` component
- UI functionality to add and remove metadata from a link on ``k-info-panel/link-info``
- MongoDB integration with ``pymongo``
- TopoController and DB models
- Retries to handle database ``AutoReconnect`` exception
- Topology now reacts to link liveness detection events

Changed
=======
- Refactored API and event handlers to also update MongoDB accordingly.
- ``kytos/topology.link_up`` is only published if link.status is EntityStatus.UP, which takes into account other protocol logical states.

Deprecated
==========
- Storehouse file system backend

Removed
=======
- Storehouse backend

Fixed
=====
- Send topology.switches and topology.links shallow copy on ``kytos/topology.topology_loaded`` and ``kytos/topology.updated`` events
- Send object metadata shallow copy on ``kytos/topology.{entities}.metadata.{action}`` event
- Shallow copy shared iterables that are used on REST endpoints

General Information
===================
- ``scripts/storehouse_to_mongo.py`` can be used to migrate data from storehouse to MongoDB

[2022.1.0] - 2022-01-25
***********************

Changed
=======
- Hooked ``notify_topology_update`` to be called at least once if an interface goes up or down
- Updated rest endpoints that disable entities to notify topology update
- Updated rest endpoints that enable entities to notify topology update
- Changed status code from 409 to 404 when interfaces aren't found

[3.10.1] - 2022-01-20
*********************

Changed
=======
- ``handle_link_down`` to publish link_down
- ``add_links`` to also notify link_up
- ``last_status_is_active`` metadata to ensure single notification


[3.10.0] - 2022-01-19
*********************

Changed
=======
- Changed ``_load_link`` to try to also load interface available tags
- Changed ``save_status_on_storehouse`` to also store interface available_tags

Added
=====
- Subscribed to ``kytos/.*.link_available_tags`` events
- Added ``_load_intf_available_tags`` to try to load and set available_Tags
- Added ``_get_links_dict_with_tags`` to also have interface available_tags
- Hooked ``_load_intf_available_tags`` to be called for interface_created

[3.9.0] - 2021-12-22
********************

Changed
=======
- Changed ``on_interface_created`` to try also handle as a link up
- Changed ``add_links`` to update the interface object reference.
- Changed ``handle_link_up`` to first activate an interface, and used the ``_links_lock``

Added
=====
- Added ``_links_lock`` to avoid race conditions on ``links`` dict


[3.8.0] - 2021-12-22
********************

Changed
=======
- Fixed ``handle_link_down`` to also deactivate the interface

[3.7.3] - 2021-12.21
********************

Changed
=======
- Changed ``add_links`` to only notify a topology update if a link has been created. 
- Changed ``_get_link_or_create`` to also return whether or not a new link has been created.


[3.7.2] - 2021-04-01
********************

Added
=====
- Added event to notify if the switch is enabled at startup.
- Added event to notify when link is enabled or disabled.
- Added new switch/link events to README.
- New input validation to metadata sent through the REST API.


[3.7.1] - 2020-11-23
********************

Added
=====
- Added events to notify when a switch has been administratively
  enabled/disabled.


[3.7.0] - 2020-11-20
********************

Changed
=======
- Restore of administrative statuses is now automatic.

[3.6.3] - 2020-10-26
********************

Changed
=======
- Changed setup.py to alert when Travis fails.

Fixed
=====
- Fixed ``Link`` metadata persistence.
- Fixed ``Interface`` metadata persistence.
- Fixed integration tests.


[3.6.2] - 2020-07-24
********************

Added
=====
- Added persistence for Link and LLDP administrative status.
- Added unit tests, increasing coverage to 85%.
- Added tags decorator to run tests by type and size.


[3.6.1] - 2020-05-21
********************

Added
=====
- Added persistence endpoint to openapi.yml.

Changed
=======
- [persistence] Changed storehouse key to `network_status` instead of `0`.


[3.6] - 2020-05-19
******************

Added
=====
- Added persistence for switches and interfaces administrative
  status (enabled/disabled).
- Added method to enable/disable all interfaces from a switch.
- Added support for automated tests and CI with Travis.
- Added integration tests and unit tests (from 39% to 57%).
- Added listeners for events from the Maintenance NApp.

Fixed
=====
- Avoid using flapping links: now a link is considered up only
  after a specific amount of time (default: 10 seconds).
- Fixed switches coordinates on the map (fix kytos#923)


[3.5.1] - 2020-03-11
********************

Added
=====
- Added event to notify when a new port is created: ``topology.port.created``

Fixed
=====
- Fixed unit tests / coverage / linter issues


[3.5.0] - 2019-03-15
********************

Added
=====
- Added method to trigger an event when a link goes up/down.
- Continuous integration enabled at scrutinizer.

Fixed
=====
- Fixed link up/down events.
- Fixed some linter issues.

Removed
=======
- Removed interface.(up|down). Fix kytos/of_core#32

[3.4.0] - 2018-12-14
*********************

- Fixed activation/deactivation of links on interface up/down events

[3.3.0] - 2018-10-15
********************

- Added support for automated tests and CI with Scrutinizer
- Fixed undefined interface link NameError
- Fixed linter warnings

[3.2.0] - 2018-06-15
********************
- Added persistence support with the NApp ``kytos/storehouse``.
- Added KytosEvent named `kytos/topology.{entities}.metadata.{action}` when the
  metadata changes.The `entities` could be `switches`, `links` or `interfaces`
  and the `action` could be `removed` or `added`.

[3.1.0] - 2018-04-20
********************
Added
=====
- Added method to send KytosEvent when a metadata changes.
- Added ui component to search switch and show switch info.

Changed
=======
- (origin/add_action_menu) Improve search_switch switch_info.

Fixed
=====
- Fixed search switch component.

[3.0.0] - 2018-03-08
********************
Added
=====
- Add 'enable' and 'disable' endpoints.
- Add methods to handle basic metadata operations.
- Add description as switch name.
- Listen to switch reconect.
- Added method to notify topology update when interface is removed.
- Added circuit example and remove $$ref.
- Added mimetype='application/json' on return of response.
- Added custom properties to dpids.
- Added 'circuit' as a property of Topology.
- Added custom property definition for circuits.

Changed
=======
- Change endpoints to represent new topology model.
- Change how the NApp deals with events.
- Change 'links' dictionary keys.
- Change LINKS to CIRCUITS in settings.
- Change custom_properties to be a dict in openapi.

Removed
=======
- Removed links from topology.
- Removed unnecessary code.
- Removed unavailable elements from the topology.
- Remove host from topology.

Fixed
=====
- Fixed topology event and link serialization.
- Fixed somes typo.

[2.0.0] - 2017-10-23
******************************************

Added
======
- Added api version.
- Added interface from openapi.yml.

Changed
=======
- Change aliases to circuits in the output json.

Fixed
=====
- Fixed when custom_links_path does not exists.
- Remove "lists" models from openapi.yml.

[1.0.0] - 2017-10-23
******************************************
Added
=====

- Added model for Topology classes/entities.
- Added topology events.
- Added method that listen to reachable.mac.
- Added method to getting port alias from port properties
- Added aliases to Port and Device.
- Added NApp dependencies.
- Added Rest API section.
- Added NApp dependencies.
- Added openapi.yml file to document the rest endpoint.
- Added a method to remove a port from a device.
- Added listener of new created switches.
- Added method to notify about topology updates.
- Added REST endpoints.
- Handle event to set an interface as NNI.
- Handle port deleted event.
- Handle modified port event.
- Handle new port added on a device.
