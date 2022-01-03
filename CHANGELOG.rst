#########
Changelog
#########

All notable changes to the ``topology`` project will be documented in this file.

[UNRELEASED] - Under development
********************************
Added
=====

Changed
=======

Deprecated
==========

Removed
=======

Fixed
=====

Security
========


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
