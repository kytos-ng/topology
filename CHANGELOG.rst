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
