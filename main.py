"""Main module of kytos/topology Kytos Network Application.

Manage the network topology
"""
# pylint: disable=wrong-import-order

import time
from collections import defaultdict
from datetime import timezone
from threading import Lock
from typing import List, Optional

from flask import jsonify, request
from werkzeug.exceptions import BadRequest, UnsupportedMediaType

from kytos.core import KytosEvent, KytosNApp, log, rest
from kytos.core.common import EntityStatus
from kytos.core.exceptions import KytosLinkCreationError
from kytos.core.helpers import listen_to, now
from kytos.core.interface import Interface
from kytos.core.link import Link
from kytos.core.switch import Switch
from napps.kytos.topology import settings

from .controllers import TopoController
from .exceptions import RestoreError
from .models import Topology

DEFAULT_LINK_UP_TIMER = 10


class Main(KytosNApp):  # pylint: disable=too-many-public-methods
    """Main class of kytos/topology NApp.

    This class is the entry point for this napp.
    """

    def setup(self):
        """Initialize the NApp's links list."""
        self.links = {}
        self.intf_available_tags = {}
        self.link_up_timer = getattr(settings, 'LINK_UP_TIMER',
                                     DEFAULT_LINK_UP_TIMER)

        self._links_lock = Lock()
        self._links_notify_lock = defaultdict(Lock)
        self.topo_controller = self.get_topo_controller()
        Link.register_status_func(f"{self.napp_id}_link_up_timer",
                                  self.link_status_hook_link_up_timer)
        self.topo_controller.bootstrap_indexes()
        self.load_topology()

    @staticmethod
    def get_topo_controller() -> TopoController:
        """Get TopoController."""
        return TopoController()

    def execute(self):
        """Execute once when the napp is running."""
        pass

    def shutdown(self):
        """Do nothing."""
        log.info('NApp kytos/topology shutting down.')

    @staticmethod
    def _get_metadata():
        """Return a JSON with metadata."""
        try:
            metadata = request.get_json()
            content_type = request.content_type
        except BadRequest as err:
            result = 'The request body is not a well-formed JSON.'
            raise BadRequest(result) from err
        if content_type is None:
            result = 'The request body is empty.'
            raise BadRequest(result)
        if metadata is None:
            if content_type != 'application/json':
                result = ('The content type must be application/json '
                          f'(received {content_type}).')
            else:
                result = 'Metadata is empty.'
            raise UnsupportedMediaType(result)
        return metadata

    def _get_link_or_create(self, endpoint_a, endpoint_b):
        """Get an existing link or create a new one.

        Returns:
            Tuple(Link, bool): Link and a boolean whether it has been created.
        """
        new_link = Link(endpoint_a, endpoint_b)

        for link in self.links.values():
            if new_link == link:
                return (link, False)

        self.links[new_link.id] = new_link
        return (new_link, True)

    def _get_switches_dict(self):
        """Return a dictionary with the known switches."""
        switches = {'switches': {}}
        for idx, switch in enumerate(self.controller.switches.copy().values()):
            switch_data = switch.as_dict()
            if not all(key in switch_data['metadata']
                       for key in ('lat', 'lng')):
                # Switches are initialized somewhere in the ocean
                switch_data['metadata']['lat'] = str(0.0)
                switch_data['metadata']['lng'] = str(-30.0+idx*10.0)
            switches['switches'][switch.id] = switch_data
        return switches

    def _get_links_dict(self):
        """Return a dictionary with the known links."""
        return {'links': {link.id: link.as_dict() for link in
                          self.links.copy().values()}}

    def _get_topology_dict(self):
        """Return a dictionary with the known topology."""
        return {'topology': {**self._get_switches_dict(),
                             **self._get_links_dict()}}

    def _get_topology(self):
        """Return an object representing the topology."""
        return Topology(self.controller.switches.copy(), self.links.copy())

    def _get_link_from_interface(self, interface):
        """Return the link of the interface, or None if it does not exist."""
        with self._links_lock:
            for link in self.links.values():
                if interface in (link.endpoint_a, link.endpoint_b):
                    return link
            return None

    def _load_link(self, link_att):
        endpoint_a = link_att['endpoint_a']['id']
        endpoint_b = link_att['endpoint_b']['id']
        link_str = link_att['id']
        log.info(f"Loading link: {link_str}")
        interface_a = self.controller.get_interface_by_id(endpoint_a)
        interface_b = self.controller.get_interface_by_id(endpoint_b)

        error = f"Fail to load endpoints for link {link_str}. "
        if not interface_a:
            raise RestoreError(f"{error}, endpoint_a {endpoint_a} not found")
        if not interface_b:
            raise RestoreError(f"{error}, endpoint_b {endpoint_b} not found")

        with self._links_lock:
            link, _ = self._get_link_or_create(interface_a, interface_b)

        if link_att['enabled']:
            link.enable()
        else:
            link.disable()

        link.extend_metadata(link_att["metadata"])
        interface_a.update_link(link)
        interface_b.update_link(link)
        interface_a.nni = True
        interface_b.nni = True

    def _load_switch(self, switch_id, switch_att):
        log.info(f'Loading switch dpid: {switch_id}')
        switch = self.controller.get_switch_or_create(switch_id)
        if switch_att['enabled']:
            switch.enable()
        else:
            switch.disable()
        switch.description['manufacturer'] = switch_att.get('manufacturer', '')
        switch.description['hardware'] = switch_att.get('hardware', '')
        switch.description['software'] = switch_att.get('software')
        switch.description['serial'] = switch_att.get('serial', '')
        switch.description['data_path'] = switch_att.get('data_path', '')
        switch.extend_metadata(switch_att["metadata"])

        for iface_id, iface_att in switch_att.get('interfaces', {}).items():
            log.info(f'Loading interface iface_id={iface_id}')
            interface = switch.update_or_create_interface(
                            port_no=iface_att['port_number'],
                            name=iface_att['name'],
                            address=iface_att.get('mac', None),
                            speed=iface_att.get('speed', None))
            if iface_att['enabled']:
                interface.enable()
            else:
                interface.disable()
            interface.lldp = iface_att['lldp']
            interface.extend_metadata(iface_att["metadata"])
            interface.deactivate()
            name = 'kytos/topology.port.created'
            event = KytosEvent(name=name, content={
                                              'switch': switch_id,
                                              'port': interface.port_number,
                                              'port_description': {
                                                  'alias': interface.name,
                                                  'mac': interface.address,
                                                  'state': interface.state
                                                  }
                                              })
            self.controller.buffers.app.put(event)

        intf_ids = [v["id"] for v in switch_att.get("interfaces", {}).values()]
        intf_details = self.topo_controller.get_interfaces_details(intf_ids)
        with self._links_lock:
            self.load_interfaces_available_tags(switch, intf_details)

    # pylint: disable=attribute-defined-outside-init
    def load_topology(self):
        """Load network topology from DB."""
        topology = self.topo_controller.get_topology()
        switches = topology["topology"]["switches"]
        links = topology["topology"]["links"]

        failed_switches = {}
        log.debug(f"_load_network_status switches={switches}")
        for switch_id, switch_att in switches.items():
            try:
                self._load_switch(switch_id, switch_att)
            # pylint: disable=broad-except
            except Exception as err:
                failed_switches[switch_id] = err
                log.error(f'Error loading switch: {err}')

        failed_links = {}
        log.debug(f"_load_network_status links={links}")
        for link_id, link_att in links.items():
            try:
                self._load_link(link_att)
            # pylint: disable=broad-except
            except Exception as err:
                failed_links[link_id] = err
                log.error(f'Error loading link {link_id}: {err}')

        name = 'kytos/topology.topology_loaded'
        event = KytosEvent(
            name=name,
            content={
                'topology': self._get_topology(),
                'failed_switches': failed_switches,
                'failed_links': failed_links
            })
        self.controller.buffers.app.put(event)

    @rest('v3/')
    def get_topology(self):
        """Return the latest known topology.

        This topology is updated when there are network events.
        """
        return jsonify(self._get_topology_dict())

    # Switch related methods
    @rest('v3/switches')
    def get_switches(self):
        """Return a json with all the switches in the topology."""
        return jsonify(self._get_switches_dict())

    @rest('v3/switches/<dpid>/enable', methods=['POST'])
    def enable_switch(self, dpid):
        """Administratively enable a switch in the topology."""
        try:
            switch = self.controller.switches[dpid]
            self.topo_controller.enable_switch(dpid)
            switch.enable()
        except KeyError:
            return jsonify("Switch not found"), 404

        self.notify_switch_enabled(dpid)
        self.notify_topology_update()
        return jsonify("Operation successful"), 201

    @rest('v3/switches/<dpid>/disable', methods=['POST'])
    def disable_switch(self, dpid):
        """Administratively disable a switch in the topology."""
        try:
            switch = self.controller.switches[dpid]
            self.topo_controller.disable_switch(dpid)
            switch.disable()
        except KeyError:
            return jsonify("Switch not found"), 404

        self.notify_switch_disabled(dpid)
        self.notify_topology_update()
        return jsonify("Operation successful"), 201

    @rest('v3/switches/<dpid>/metadata')
    def get_switch_metadata(self, dpid):
        """Get metadata from a switch."""
        try:
            return jsonify({"metadata":
                            self.controller.switches[dpid].metadata}), 200
        except KeyError:
            return jsonify("Switch not found"), 404

    @rest('v3/switches/<dpid>/metadata', methods=['POST'])
    def add_switch_metadata(self, dpid):
        """Add metadata to a switch."""
        metadata = self._get_metadata()

        try:
            switch = self.controller.switches[dpid]
        except KeyError:
            return jsonify("Switch not found"), 404

        self.topo_controller.add_switch_metadata(dpid, metadata)
        switch.extend_metadata(metadata)
        self.notify_metadata_changes(switch, 'added')
        return jsonify("Operation successful"), 201

    @rest('v3/switches/<dpid>/metadata/<key>', methods=['DELETE'])
    def delete_switch_metadata(self, dpid, key):
        """Delete metadata from a switch."""
        try:
            switch = self.controller.switches[dpid]
        except KeyError:
            return jsonify("Switch not found"), 404

        try:
            _ = switch.metadata[key]
        except KeyError:
            return jsonify("Metadata not found"), 404

        self.topo_controller.delete_switch_metadata_key(dpid, key)
        switch.remove_metadata(key)
        self.notify_metadata_changes(switch, 'removed')
        return jsonify("Operation successful"), 200

    # Interface related methods
    @rest('v3/interfaces')
    def get_interfaces(self):
        """Return a json with all the interfaces in the topology."""
        interfaces = {}
        switches = self._get_switches_dict()
        for switch in switches['switches'].values():
            for interface_id, interface in switch['interfaces'].items():
                interfaces[interface_id] = interface

        return jsonify({'interfaces': interfaces})

    @rest('v3/interfaces/switch/<dpid>/enable', methods=['POST'])
    @rest('v3/interfaces/<interface_enable_id>/enable', methods=['POST'])
    def enable_interface(self, interface_enable_id=None, dpid=None):
        """Administratively enable interfaces in the topology."""
        if dpid is None:
            dpid = ":".join(interface_enable_id.split(":")[:-1])
        try:
            switch = self.controller.switches[dpid]
        except KeyError as exc:
            return jsonify(f"Switch not found: {exc}"), 404

        if interface_enable_id:
            interface_number = int(interface_enable_id.split(":")[-1])

            try:
                interface = switch.interfaces[interface_number]
                self.topo_controller.enable_interface(interface.id)
                interface.enable()
            except KeyError:
                msg = f"Switch {dpid} interface {interface_number} not found"
                return jsonify(msg), 404
        else:
            for interface in switch.interfaces.copy().values():
                interface.enable()
            self.topo_controller.upsert_switch(switch.id, switch.as_dict())
        self.notify_topology_update()
        return jsonify("Operation successful"), 200

    @rest('v3/interfaces/switch/<dpid>/disable', methods=['POST'])
    @rest('v3/interfaces/<interface_disable_id>/disable', methods=['POST'])
    def disable_interface(self, interface_disable_id=None, dpid=None):
        """Administratively disable interfaces in the topology."""
        if dpid is None:
            dpid = ":".join(interface_disable_id.split(":")[:-1])
        try:
            switch = self.controller.switches[dpid]
        except KeyError as exc:
            return jsonify(f"Switch not found: {exc}"), 404

        if interface_disable_id:
            interface_number = int(interface_disable_id.split(":")[-1])

            try:
                interface = switch.interfaces[interface_number]
                self.topo_controller.disable_interface(interface.id)
                interface.disable()
            except KeyError:
                msg = f"Switch {dpid} interface {interface_number} not found"
                return jsonify(msg), 404
        else:
            for interface in switch.interfaces.copy().values():
                interface.disable()
            self.topo_controller.upsert_switch(switch.id, switch.as_dict())
        self.notify_topology_update()
        return jsonify("Operation successful"), 200

    @rest('v3/interfaces/<interface_id>/metadata')
    def get_interface_metadata(self, interface_id):
        """Get metadata from an interface."""
        switch_id = ":".join(interface_id.split(":")[:-1])
        interface_number = int(interface_id.split(":")[-1])
        try:
            switch = self.controller.switches[switch_id]
        except KeyError:
            return jsonify("Switch not found"), 404

        try:
            interface = switch.interfaces[interface_number]
        except KeyError:
            return jsonify("Interface not found"), 404

        return jsonify({"metadata": interface.metadata}), 200

    @rest('v3/interfaces/<interface_id>/metadata', methods=['POST'])
    def add_interface_metadata(self, interface_id):
        """Add metadata to an interface."""
        metadata = self._get_metadata()
        switch_id = ":".join(interface_id.split(":")[:-1])
        interface_number = int(interface_id.split(":")[-1])
        try:
            switch = self.controller.switches[switch_id]
        except KeyError:
            return jsonify("Switch not found"), 404

        try:
            interface = switch.interfaces[interface_number]
            self.topo_controller.add_interface_metadata(interface.id, metadata)
        except KeyError:
            return jsonify("Interface not found"), 404

        interface.extend_metadata(metadata)
        self.notify_metadata_changes(interface, 'added')
        return jsonify("Operation successful"), 201

    @rest('v3/interfaces/<interface_id>/metadata/<key>', methods=['DELETE'])
    def delete_interface_metadata(self, interface_id, key):
        """Delete metadata from an interface."""
        switch_id = ":".join(interface_id.split(":")[:-1])
        interface_number = int(interface_id.split(":")[-1])

        try:
            switch = self.controller.switches[switch_id]
        except KeyError:
            return jsonify("Switch not found"), 404

        try:
            interface = switch.interfaces[interface_number]
        except KeyError:
            return jsonify("Interface not found"), 404

        try:
            _ = interface.metadata[key]
        except KeyError:
            return jsonify("Metadata not found"), 404

        self.topo_controller.delete_interface_metadata_key(interface.id, key)
        interface.remove_metadata(key)
        self.notify_metadata_changes(interface, 'removed')
        return jsonify("Operation successful"), 200

    # Link related methods
    @rest('v3/links')
    def get_links(self):
        """Return a json with all the links in the topology.

        Links are connections between interfaces.
        """
        return jsonify(self._get_links_dict()), 200

    @rest('v3/links/<link_id>/enable', methods=['POST'])
    def enable_link(self, link_id):
        """Administratively enable a link in the topology."""
        try:
            with self._links_lock:
                link = self.links[link_id]
                self.topo_controller.enable_link(link_id)
                link.enable()
        except KeyError:
            return jsonify("Link not found"), 404
        self.notify_link_status_change(
            self.links[link_id],
            reason='link enabled'
        )
        self.notify_topology_update()
        return jsonify("Operation successful"), 201

    @rest('v3/links/<link_id>/disable', methods=['POST'])
    def disable_link(self, link_id):
        """Administratively disable a link in the topology."""
        try:
            with self._links_lock:
                link = self.links[link_id]
                self.topo_controller.disable_link(link_id)
                link.disable()
        except KeyError:
            return jsonify("Link not found"), 404
        self.notify_link_status_change(
            self.links[link_id],
            reason='link disabled'
        )
        self.notify_topology_update()
        return jsonify("Operation successful"), 201

    @rest('v3/links/<link_id>/metadata')
    def get_link_metadata(self, link_id):
        """Get metadata from a link."""
        try:
            return jsonify({"metadata": self.links[link_id].metadata}), 200
        except KeyError:
            return jsonify("Link not found"), 404

    @rest('v3/links/<link_id>/metadata', methods=['POST'])
    def add_link_metadata(self, link_id):
        """Add metadata to a link."""
        metadata = self._get_metadata()
        try:
            link = self.links[link_id]
        except KeyError:
            return jsonify("Link not found"), 404

        self.topo_controller.add_link_metadata(link_id, metadata)
        link.extend_metadata(metadata)
        self.notify_metadata_changes(link, 'added')
        return jsonify("Operation successful"), 201

    @rest('v3/links/<link_id>/metadata/<key>', methods=['DELETE'])
    def delete_link_metadata(self, link_id, key):
        """Delete metadata from a link."""
        try:
            link = self.links[link_id]
        except KeyError:
            return jsonify("Link not found"), 404

        try:
            _ = link.metadata[key]
        except KeyError:
            return jsonify("Metadata not found"), 404

        self.topo_controller.delete_link_metadata_key(link.id, key)
        link.remove_metadata(key)
        self.notify_metadata_changes(link, 'removed')
        return jsonify("Operation successful"), 200

    def notify_current_topology(self) -> None:
        """Notify current topology."""
        name = "kytos/topology.current"
        event = KytosEvent(name=name, content={"topology":
                                               self._get_topology()})
        self.controller.buffers.app.put(event)

    @listen_to("kytos/topology.get")
    def on_get_topology(self, _event) -> None:
        """Handle kytos/topology.get."""
        self.notify_current_topology()

    @listen_to("kytos/.*.liveness.(up|down)")
    def on_link_liveness_status(self, event) -> None:
        """Handle link liveness up|down status event."""
        link = Link(event.content["interface_a"], event.content["interface_b"])
        try:
            link = self.links[link.id]
        except KeyError:
            log.error(f"Link id {link.id} not found, {link}")
            return
        liveness_status = event.name.split(".")[-1]
        self.handle_link_liveness_status(self.links[link.id], liveness_status)

    def handle_link_liveness_status(self, link, liveness_status) -> None:
        """Handle link liveness."""
        metadata = {"liveness_status": liveness_status}
        log.info(f"Link liveness {liveness_status}: {link}")
        self.topo_controller.add_link_metadata(link.id, metadata)
        link.extend_metadata(metadata)
        self.notify_topology_update()
        if link.status == EntityStatus.UP and liveness_status == "up":
            self.notify_link_status_change(link, reason="liveness_up")
        if link.status == EntityStatus.DOWN and liveness_status == "down":
            self.notify_link_status_change(link, reason="liveness_down")

    @listen_to("kytos/.*.liveness.disabled")
    def on_link_liveness_disabled(self, event) -> None:
        """Handle link liveness disabled event."""
        interfaces = event.content["interfaces"]
        self.handle_link_liveness_disabled(interfaces)

    def get_links_from_interfaces(self, interfaces) -> dict:
        """Get links from interfaces."""
        links_found = {}
        with self._links_lock:
            for interface in interfaces:
                for link in self.links.values():
                    if any((
                        interface.id == link.endpoint_a.id,
                        interface.id == link.endpoint_b.id,
                    )):
                        links_found[link.id] = link
        return links_found

    def handle_link_liveness_disabled(self, interfaces) -> None:
        """Handle link liveness disabled."""
        log.info(f"Link liveness disabled interfaces: {interfaces}")

        key = "liveness_status"
        links = self.get_links_from_interfaces(interfaces)
        for link in links.values():
            link.remove_metadata(key)
        link_ids = list(links.keys())
        self.topo_controller.bulk_delete_link_metadata_key(link_ids, key)
        self.notify_topology_update()
        for link in links.values():
            self.notify_link_status_change(link, reason="liveness_disabled")

    @listen_to("kytos/.*.link_available_tags")
    def on_link_available_tags(self, event):
        """Handle on_link_available_tags."""
        with self._links_lock:
            self.handle_on_link_available_tags(event.content.get("link"))

    def handle_on_link_available_tags(self, link):
        """Handle on_link_available_tags."""
        if link.id not in self.links:
            return
        endpoint_a = self.links[link.id].endpoint_a
        endpoint_b = self.links[link.id].endpoint_b
        values_a = [tag.value for tag in endpoint_a.available_tags]
        values_b = [tag.value for tag in endpoint_b.available_tags]
        ids_details = [
            (endpoint_a.id, {"_id": endpoint_a.id,
                             "available_vlans": values_a}),
            (endpoint_b.id, {"_id": endpoint_b.id,
                             "available_vlans": values_b})
        ]
        self.topo_controller.bulk_upsert_interface_details(ids_details)

    @listen_to('.*.switch.(new|reconnected)')
    def on_new_switch(self, event):
        """Create a new Device on the Topology.

        Handle the event of a new created switch and update the topology with
        this new device. Also notify if the switch is enabled.
        """
        self.handle_new_switch(event)

    def handle_new_switch(self, event):
        """Create a new Device on the Topology."""
        switch = event.content['switch']
        switch.activate()
        self.topo_controller.upsert_switch(switch.id, switch.as_dict())
        log.debug('Switch %s added to the Topology.', switch.id)
        self.notify_topology_update()
        if switch.is_enabled():
            self.notify_switch_enabled(switch.id)

    @listen_to('.*.connection.lost')
    def on_connection_lost(self, event):
        """Remove a Device from the topology.

        Remove the disconnected Device and every link that has one of its
        interfaces.
        """
        self.handle_connection_lost(event)

    def handle_connection_lost(self, event):
        """Remove a Device from the topology."""
        switch = event.content['source'].switch
        if switch:
            switch.deactivate()
            self.topo_controller.deactivate_switch(switch.id)
            log.debug('Switch %s removed from the Topology.', switch.id)
            self.notify_topology_update()

    def handle_interfaces_created(self, event):
        """Update the topology based on the interfaces created."""
        interfaces = event.content["interfaces"]
        if not interfaces:
            return
        switch = interfaces[0].switch
        self.topo_controller.upsert_switch(switch.id, switch.as_dict())
        name = "kytos/topology.switch.interface.created"
        for interface in interfaces:
            event = KytosEvent(name=name, content={'interface': interface})
            self.controller.buffers.app.put(event)

    def handle_interface_created(self, event):
        """Update the topology based on an interface created event.

        It's handled as a link_up in case a switch send a
        created event again and it can be belong to a link.
        """
        interface = event.content['interface']
        self.handle_interface_link_up(interface)

    @listen_to('.*.topology.switch.interface.created')
    def on_interface_created(self, event):
        """Handle individual interface create event.

        It's handled as a link_up in case a switch send a
        created event it can belong to an existign link.
        """
        self.handle_interface_created(event)

    @listen_to('.*.switch.interfaces.created')
    def on_interfaces_created(self, event):
        """Update the topology based on a list of created interfaces."""
        self.handle_interfaces_created(event)

    def handle_interface_down(self, event):
        """Update the topology based on a Port Modify event.

        The event notifies that an interface was changed to 'down'.
        """
        interface = event.content['interface']
        interface.deactivate()
        self.topo_controller.deactivate_interface(interface.id)
        self.handle_interface_link_down(interface)

    @listen_to('.*.switch.interface.deleted')
    def on_interface_deleted(self, event):
        """Update the topology based on a Port Delete event."""
        self.handle_interface_deleted(event)

    def handle_interface_deleted(self, event):
        """Update the topology based on a Port Delete event."""
        self.handle_interface_down(event)

    @listen_to('.*.switch.interface.link_up')
    def on_interface_link_up(self, event):
        """Update the topology based on a Port Modify event.

        The event notifies that an interface's link was changed to 'up'.
        """
        interface = event.content['interface']
        self.handle_interface_link_up(interface)

    def handle_interface_link_up(self, interface):
        """Update the topology based on a Port Modify event."""
        self.handle_link_up(interface)

    @listen_to('kytos/maintenance.end_switch')
    def on_switch_maintenance_end(self, event):
        """Handle the end of the maintenance of a switch."""
        self.handle_switch_maintenance_end(event)

    def handle_switch_maintenance_end(self, event):
        """Handle the end of the maintenance of a switch."""
        switches = event.content['switches']
        for switch in switches:
            switch.enable()
            switch.activate()
            for interface in switch.interfaces.values():
                interface.enable()
                self.handle_link_up(interface)

    def link_status_hook_link_up_timer(self, link) -> Optional[EntityStatus]:
        """Link status hook link up timer."""
        tnow = time.time()
        if (
            link.is_active()
            and link.is_enabled()
            and "last_status_change" in link.metadata
            and tnow - link.metadata['last_status_change'] < self.link_up_timer
        ):
            return EntityStatus.DOWN
        return None

    def notify_link_up_if_status(self, link) -> None:
        """Tries to notify link up and topology changes based on its status

        Currently, it needs to wait up to a timer."""
        time.sleep(self.link_up_timer)
        if link.status != EntityStatus.UP:
            return
        with self._links_notify_lock[link.id]:
            notified_at = link.get_metadata("notified_up_at")
            if (
                notified_at
                and (now() - notified_at.replace(tzinfo=timezone.utc)).seconds
                < self.link_up_timer
            ):
                return
            key, notified_at = "notified_up_at", now()
            link.update_metadata(key, now())
            self.topo_controller.add_link_metadata(link.id, {key: notified_at})
            self.notify_topology_update()
            self.notify_link_status_change(link, reason="link up")

    def handle_link_up(self, interface):
        """Handle link up for an interface."""
        interface.activate()
        self.topo_controller.activate_interface(interface.id)
        self.notify_topology_update()
        link = self._get_link_from_interface(interface)
        if not link:
            return
        if link.endpoint_a == interface:
            other_interface = link.endpoint_b
        else:
            other_interface = link.endpoint_a
        if other_interface.is_active() is False:
            return
        metadata = {
            'last_status_change': time.time(),
            'last_status_is_active': True
        }
        link.extend_metadata(metadata)
        link.activate()
        self.topo_controller.activate_link(link.id, **metadata)
        self.notify_link_up_if_status(link)

    @listen_to('.*.switch.interface.link_down')
    def on_interface_link_down(self, event):
        """Update the topology based on a Port Modify event.

        The event notifies that an interface's link was changed to 'down'.
        """
        interface = event.content['interface']
        self.handle_interface_link_down(interface)

    def handle_interface_link_down(self, interface):
        """Update the topology based on an interface."""
        self.handle_link_down(interface)

    @listen_to('kytos/maintenance.start_switch')
    def on_switch_maintenance_start(self, event):
        """Handle the start of the maintenance of a switch."""
        self.handle_switch_maintenance_start(event)

    def handle_switch_maintenance_start(self, event):
        """Handle the start of the maintenance of a switch."""
        switches = event.content['switches']
        for switch in switches:
            switch.disable()
            switch.deactivate()
            for interface in switch.interfaces.values():
                interface.disable()
                if interface.is_active():
                    self.handle_link_down(interface)

    def handle_link_down(self, interface):
        """Notify a link is down."""
        link = self._get_link_from_interface(interface)
        if link and link.is_active():
            link.deactivate()
            last_status_change = time.time()
            last_status_is_active = False
            metadata = {
                "last_status_change": last_status_change,
                "last_status_is_active": last_status_is_active,
            }
            link.extend_metadata(metadata)
            self.topo_controller.deactivate_link(link.id, last_status_change,
                                                 last_status_is_active)
            self.notify_link_status_change(link, reason="link down")
        if link and not link.is_active():
            with self._links_lock:
                last_status = link.get_metadata('last_status_is_active')
                last_status_change = link.get_metadata('last_status_change')
                metadata = {
                    "last_status_change": last_status_change,
                    "last_status_is_active": last_status,
                }
                if last_status:
                    link.extend_metadata(metadata)
                    self.topo_controller.deactivate_link(link.id,
                                                         last_status_change,
                                                         last_status)
                    self.notify_link_status_change(link, reason='link down')
        interface.deactivate()
        self.topo_controller.deactivate_interface(interface.id)
        self.notify_topology_update()

    @listen_to('.*.interface.is.nni')
    def on_add_links(self, event):
        """Update the topology with links related to the NNI interfaces."""
        self.add_links(event)

    def add_links(self, event):
        """Update the topology with links related to the NNI interfaces."""
        interface_a = event.content['interface_a']
        interface_b = event.content['interface_b']

        try:
            with self._links_lock:
                link, created = self._get_link_or_create(interface_a,
                                                         interface_b)
                interface_a.update_link(link)
                interface_b.update_link(link)

                link.endpoint_a = interface_a
                link.endpoint_b = interface_b

                interface_a.nni = True
                interface_b.nni = True

        except KytosLinkCreationError as err:
            log.error(f'Error creating link: {err}.')
            return

        if not created:
            return

        self.notify_topology_update()
        if not link.is_active():
            return

        metadata = {
            'last_status_change': time.time(),
            'last_status_is_active': True
        }
        link.extend_metadata(metadata)
        self.topo_controller.upsert_link(link.id, link.as_dict())
        self.notify_link_up_if_status(link)

    @listen_to('.*.of_lldp.network_status.updated')
    def on_lldp_status_updated(self, event):
        """Handle of_lldp.network_status.updated from of_lldp."""
        self.handle_lldp_status_updated(event)

    @listen_to(".*.topo_controller.upsert_switch")
    def on_topo_controller_upsert_switch(self, event) -> None:
        """Listen to topo_controller_upsert_switch."""
        self.handle_topo_controller_upsert_switch(event.content["switch"])

    def handle_topo_controller_upsert_switch(self, switch) -> Optional[dict]:
        """Handle topo_controller_upsert_switch."""
        return self.topo_controller.upsert_switch(switch.id, switch.as_dict())

    def handle_lldp_status_updated(self, event) -> None:
        """Handle .*.network_status.updated events from of_lldp."""
        content = event.content
        interface_ids = content["interface_ids"]
        switches = set()
        for interface_id in interface_ids:
            dpid = ":".join(interface_id.split(":")[:-1])
            switch = self.controller.get_switch_by_dpid(dpid)
            if switch:
                switches.add(switch)

        name = "kytos/topology.topo_controller.upsert_switch"
        for switch in switches:
            event = KytosEvent(name=name, content={"switch": switch})
            self.controller.buffers.app.put(event)

    def notify_switch_enabled(self, dpid):
        """Send an event to notify that a switch is enabled."""
        name = 'kytos/topology.switch.enabled'
        event = KytosEvent(name=name, content={'dpid': dpid})
        self.controller.buffers.app.put(event)

    def notify_switch_disabled(self, dpid):
        """Send an event to notify that a switch is disabled."""
        name = 'kytos/topology.switch.disabled'
        event = KytosEvent(name=name, content={'dpid': dpid})
        self.controller.buffers.app.put(event)

    def notify_topology_update(self):
        """Send an event to notify about updates on the topology."""
        name = 'kytos/topology.updated'
        event = KytosEvent(name=name, content={'topology':
                                               self._get_topology()})
        self.controller.buffers.app.put(event)

    def notify_link_status_change(self, link, reason='not given'):
        """Send an event to notify about a status change on a link."""
        name = 'kytos/topology.'
        if link.status == EntityStatus.UP:
            status = 'link_up'
        else:
            status = 'link_down'
        event = KytosEvent(
            name=name+status,
            content={
                'link': link,
                'reason': reason
            })
        self.controller.buffers.app.put(event)

    def notify_metadata_changes(self, obj, action):
        """Send an event to notify about metadata changes."""
        if isinstance(obj, Switch):
            entity = 'switch'
            entities = 'switches'
        elif isinstance(obj, Interface):
            entity = 'interface'
            entities = 'interfaces'
        elif isinstance(obj, Link):
            entity = 'link'
            entities = 'links'
        else:
            raise ValueError(
                'Invalid object, supported: Switch, Interface, Link'
            )

        name = f'kytos/topology.{entities}.metadata.{action}'
        content = {entity: obj, 'metadata': obj.metadata.copy()}
        event = KytosEvent(name=name, content=content)
        self.controller.buffers.app.put(event)
        log.debug(f'Metadata from {obj.id} was {action}.')

    @listen_to('.*.switch.port.created')
    def on_notify_port_created(self, event):
        """Notify when a port is created."""
        self.notify_port_created(event)

    def notify_port_created(self, event):
        """Notify when a port is created."""
        name = 'kytos/topology.port.created'
        event = KytosEvent(name=name, content=event.content)
        self.controller.buffers.app.put(event)

    @staticmethod
    def load_interfaces_available_tags(switch: Switch,
                                       interfaces_details: List[dict]) -> None:
        """Load interfaces available tags (vlans)."""
        if not interfaces_details:
            return
        for interface_details in interfaces_details:
            available_vlans = interface_details["available_vlans"]
            if not available_vlans:
                continue
            log.debug(f"Interface id {interface_details['id']} loading "
                      f"{len(interface_details['available_vlans'])} "
                      "available tags")
            port_number = int(interface_details["id"].split(":")[-1])
            interface = switch.interfaces[port_number]
            interface.set_available_tags(interface_details['available_vlans'])

    @listen_to('kytos/maintenance.start_link')
    def on_link_maintenance_start(self, event):
        """Deals with the start of links maintenance."""
        with self._links_lock:
            self.handle_link_maintenance_start(event)

    def handle_link_maintenance_start(self, event):
        """Deals with the start of links maintenance."""
        notify_links = []
        maintenance_links = event.content['links']
        for maintenance_link in maintenance_links:
            try:
                link = self.links[maintenance_link.id]
            except KeyError:
                continue
            notify_links.append(link)
        for link in notify_links:
            link.disable()
            link.deactivate()
            link.endpoint_a.deactivate()
            link.endpoint_b.deactivate()
            link.endpoint_a.disable()
            link.endpoint_b.disable()
            self.notify_link_status_change(link, reason='maintenance')

    @listen_to('kytos/maintenance.end_link')
    def on_link_maintenance_end(self, event):
        """Deals with the end of links maintenance."""
        with self._links_lock:
            self.handle_link_maintenance_end(event)

    def handle_link_maintenance_end(self, event):
        """Deals with the end of links maintenance."""
        notify_links = []
        maintenance_links = event.content['links']
        for maintenance_link in maintenance_links:
            try:
                link = self.links[maintenance_link.id]
            except KeyError:
                continue
            notify_links.append(link)
        for link in notify_links:
            link.enable()
            link.activate()
            link.endpoint_a.activate()
            link.endpoint_b.activate()
            link.endpoint_a.enable()
            link.endpoint_b.enable()
            self.notify_link_status_change(link, reason='maintenance')
