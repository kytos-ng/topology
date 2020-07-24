"""Main module of kytos/topology Kytos Network Application.

Manage the network topology
"""
import time

from flask import jsonify, request

from kytos.core import KytosEvent, KytosNApp, log, rest
from kytos.core.helpers import listen_to
from kytos.core.interface import Interface
from kytos.core.link import Link
from kytos.core.switch import Switch
from napps.kytos.topology import settings
from napps.kytos.topology.models import Topology
from napps.kytos.topology.storehouse import StoreHouse

DEFAULT_LINK_UP_TIMER = 10


class Main(KytosNApp):  # pylint: disable=too-many-public-methods
    """Main class of kytos/topology NApp.

    This class is the entry point for this napp.
    """

    def setup(self):
        """Initialize the NApp's links list."""
        self.links = {}
        self.store_items = {}
        self.switches_state = {}
        self.interfaces_state = {}
        self.links_state = {}
        self.link_up_timer = getattr(settings, 'LINK_UP_TIMER',
                                     DEFAULT_LINK_UP_TIMER)

        self.verify_storehouse('switches')
        self.verify_storehouse('interfaces')
        self.verify_storehouse('links')

        self.storehouse = StoreHouse(self.controller)

    def execute(self):
        """Do nothing."""

    def shutdown(self):
        """Do nothing."""
        log.info('NApp kytos/topology shutting down.')

    def _get_link_or_create(self, endpoint_a, endpoint_b):
        new_link = Link(endpoint_a, endpoint_b)

        for link in self.links.values():
            if new_link == link:
                return link

        self.links[new_link.id] = new_link
        return new_link

    def _get_switches_dict(self):
        """Return a dictionary with the known switches."""
        switches = {'switches': {}}
        for idx, switch in enumerate(self.controller.switches.values()):
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
        return {'links': {l.id: l.as_dict() for l in
                          self.links.values()}}

    def _get_topology_dict(self):
        """Return a dictionary with the known topology."""
        return {'topology': {**self._get_switches_dict(),
                             **self._get_links_dict()}}

    def _get_topology(self):
        """Return an object representing the topology."""
        return Topology(self.controller.switches, self.links)

    def _get_link_from_interface(self, interface):
        """Return the link of the interface, or None if it does not exist."""
        for link in self.links.values():
            if interface in (link.endpoint_a, link.endpoint_b):
                return link
        return None

    def _restore_links(self):
        """Restore link saved in StoreHouse."""
        for link_id, state, in self.links_state.items():
            dpid_a = state['endpoint_a']['switch']
            iface_id_a = int(state['endpoint_a']['id'][-1])
            dpid_b = state['endpoint_b']['switch']
            iface_id_b = int(state['endpoint_b']['id'][-1])
            try:
                endpoint_a = self.controller.switches[dpid_a].interfaces[
                    iface_id_a]
                endpoint_b = self.controller.switches[dpid_b].interfaces[
                    iface_id_b]
            except KeyError as error:
                error_msg = (f"Error restoring link endpoint: {error}")
                raise KeyError(error_msg)

            link = self._get_link_or_create(endpoint_a, endpoint_b)
            endpoint_a.update_link(link)
            endpoint_b.update_link(link)

            endpoint_a.nni = True
            endpoint_b.nni = True

            self.notify_topology_update()

            try:
                if state['enabled']:
                    self.links[link_id].enable()
                else:
                    self.links[link_id].disable()
            except KeyError:
                error = ('Error restoring link status.'
                         f'The link {link} does not exist.')
                raise KeyError(error)

    def _restore_status(self):
        """Restore the network administrative status saved in StoreHouse."""
        # restore Switches
        for switch_id, state in self.switches_state.items():
            try:
                if state:
                    self.controller.switches[switch_id].enable()
                else:
                    self.controller.switches[switch_id].disable()
            except KeyError:
                error = ('Error while restoring switches status. The '
                         f'{switch_id} does not exist.')
                raise KeyError(error)
        # restore interfaces
        for interface_id, state in self.interfaces_state.items():
            switch_id = ":".join(interface_id.split(":")[:-1])
            interface_number = int(interface_id.split(":")[-1])
            interface_status, lldp_status = state
            try:
                switch = self.controller.switches[switch_id]
                if interface_status:
                    switch.interfaces[interface_number].enable()
                else:
                    switch.interfaces[interface_number].disable()
                switch.interfaces[interface_number].lldp = lldp_status
            except KeyError:
                error = ('Error while restoring interface status. The '
                         f'interface {interface_id} does not exist.')
                raise KeyError(error)
        # restore links
        self._restore_links()

    # pylint: disable=attribute-defined-outside-init
    def _load_network_status(self):
        """Load network status saved in storehouse."""
        status = self.storehouse.get_data()
        if status:
            switches = status['network_status']['switches']
            self.links_state = status['network_status']['links']

            for switch, switch_attributes in switches.items():
                # get swicthes status
                self.switches_state[switch] = switch_attributes['enabled']
                interfaces = switch_attributes['interfaces']
                # get interface status
                for interface, interface_attributes in interfaces.items():
                    enabled_value = interface_attributes['enabled']
                    lldp_value = interface_attributes['lldp']
                    self.interfaces_state[interface] = (enabled_value,
                                                        lldp_value)

        else:
            error = 'There is no status saved to restore.'
            log.info(error)
            raise FileNotFoundError(error)

    @rest('v3/')
    def get_topology(self):
        """Return the latest known topology.

        This topology is updated when there are network events.
        """
        return jsonify(self._get_topology_dict())

    @rest('v3/restore')
    def restore_network_status(self):
        """Restore the network administrative status saved in StoreHouse."""
        try:
            self._load_network_status()
            self._restore_status()
        except (KeyError, FileNotFoundError) as exc:
            return jsonify(f'{str(exc)}'), 404
        log.info('Network status restored.')
        return jsonify('Administrative status restored.'), 200

    # Switch related methods
    @rest('v3/switches')
    def get_switches(self):
        """Return a json with all the switches in the topology."""
        return jsonify(self._get_switches_dict())

    @rest('v3/switches/<dpid>/enable', methods=['POST'])
    def enable_switch(self, dpid):
        """Administratively enable a switch in the topology."""
        try:
            self.controller.switches[dpid].enable()
            log.info(f"Storing administrative state from switch {dpid}"
                     " to enabled.")
            self.save_status_on_storehouse()
            return jsonify("Operation successful"), 201
        except KeyError:
            return jsonify("Switch not found"), 404

    @rest('v3/switches/<dpid>/disable', methods=['POST'])
    def disable_switch(self, dpid):
        """Administratively disable a switch in the topology."""
        try:
            self.controller.switches[dpid].disable()
            log.info(f"Storing administrative state from switch {dpid}"
                     " to disabled.")
            self.save_status_on_storehouse()
            return jsonify("Operation successful"), 201
        except KeyError:
            return jsonify("Switch not found"), 404

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
        metadata = request.get_json()
        try:
            switch = self.controller.switches[dpid]
        except KeyError:
            return jsonify("Switch not found"), 404

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
        error_list = []  # List of interfaces that were not activated.
        msg_error = "Some interfaces couldn't be found and activated: "
        if dpid is None:
            dpid = ":".join(interface_enable_id.split(":")[:-1])
        try:
            switch = self.controller.switches[dpid]
        except KeyError as exc:
            return jsonify(f"Switch not found: {exc}"), 404

        if interface_enable_id:
            interface_number = int(interface_enable_id.split(":")[-1])

            try:
                switch.interfaces[interface_number].enable()
            except KeyError as exc:
                error_list.append(f"Switch {dpid} Interface {exc}")
        else:
            for interface in switch.interfaces.values():
                interface.enable()
        if not error_list:
            log.info(f"Storing administrative state for enabled interfaces.")
            self.save_status_on_storehouse()
            return jsonify("Operation successful"), 200
        return jsonify({msg_error:
                        error_list}), 409

    @rest('v3/interfaces/switch/<dpid>/disable', methods=['POST'])
    @rest('v3/interfaces/<interface_disable_id>/disable', methods=['POST'])
    def disable_interface(self, interface_disable_id=None, dpid=None):
        """Administratively disable interfaces in the topology."""
        error_list = []  # List of interfaces that were not deactivated.
        msg_error = "Some interfaces couldn't be found and deactivated: "
        if dpid is None:
            dpid = ":".join(interface_disable_id.split(":")[:-1])
        try:
            switch = self.controller.switches[dpid]
        except KeyError as exc:
            return jsonify(f"Switch not found: {exc}"), 404

        if interface_disable_id:
            interface_number = int(interface_disable_id.split(":")[-1])

            try:
                switch.interfaces[interface_number].disable()
            except KeyError as exc:
                error_list.append(f"Switch {dpid} Interface {exc}")
        else:
            for interface in switch.interfaces.values():
                interface.disable()
        if not error_list:
            log.info(f"Storing administrative state for disabled interfaces.")
            self.save_status_on_storehouse()
            return jsonify("Operation successful"), 200
        return jsonify({msg_error:
                        error_list}), 409

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
        metadata = request.get_json()

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

        if interface.remove_metadata(key) is False:
            return jsonify("Metadata not found"), 404

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
            self.links[link_id].enable()
        except KeyError:
            return jsonify("Link not found"), 404
        self.save_status_on_storehouse()
        return jsonify("Operation successful"), 201

    @rest('v3/links/<link_id>/disable', methods=['POST'])
    def disable_link(self, link_id):
        """Administratively disable a link in the topology."""
        try:
            self.links[link_id].disable()
        except KeyError:
            return jsonify("Link not found"), 404
        self.save_status_on_storehouse()
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
        metadata = request.get_json()
        try:
            link = self.links[link_id]
        except KeyError:
            return jsonify("Link not found"), 404

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

        if link.remove_metadata(key) is False:
            return jsonify("Metadata not found"), 404

        self.notify_metadata_changes(link, 'removed')
        return jsonify("Operation successful"), 200

    @listen_to('.*.switch.(new|reconnected)')
    def handle_new_switch(self, event):
        """Create a new Device on the Topology.

        Handle the event of a new created switch and update the topology with
        this new device.
        """
        switch = event.content['switch']
        switch.activate()
        log.debug('Switch %s added to the Topology.', switch.id)
        self.notify_topology_update()
        self.update_instance_metadata(switch)

    @listen_to('.*.connection.lost')
    def handle_connection_lost(self, event):
        """Remove a Device from the topology.

        Remove the disconnected Device and every link that has one of its
        interfaces.
        """
        switch = event.content['source'].switch
        if switch:
            switch.deactivate()
            log.debug('Switch %s removed from the Topology.', switch.id)
            self.notify_topology_update()

    def handle_interface_up(self, event):
        """Update the topology based on a Port Modify event.

        The event notifies that an interface was changed to 'up'.
        """
        interface = event.content['interface']
        interface.activate()
        self.notify_topology_update()
        self.update_instance_metadata(interface)

    @listen_to('.*.switch.interface.created')
    def handle_interface_created(self, event):
        """Update the topology based on a Port Create event."""
        self.handle_interface_up(event)

    def handle_interface_down(self, event):
        """Update the topology based on a Port Modify event.

        The event notifies that an interface was changed to 'down'.
        """
        interface = event.content['interface']
        interface.deactivate()
        self.handle_interface_link_down(event)
        self.notify_topology_update()

    @listen_to('.*.switch.interface.deleted')
    def handle_interface_deleted(self, event):
        """Update the topology based on a Port Delete event."""
        self.handle_interface_down(event)

    @listen_to('.*.switch.interface.link_up')
    def handle_interface_link_up(self, event):
        """Update the topology based on a Port Modify event.

        The event notifies that an interface's link was changed to 'up'.
        """
        interface = event.content['interface']
        self.handle_link_up(interface)

    @listen_to('kytos/maintenance.end_switch')
    def handle_switch_maintenance_end(self, event):
        """Handle the end of the maintenance of a switch."""
        switches = event.content['switches']
        for switch in switches:
            switch.enable()
            switch.activate()
            for interface in switch.interfaces.values():
                interface.enable()
                self.handle_link_up(interface)

    def handle_link_up(self, interface):
        """Notify a link is up."""
        link = self._get_link_from_interface(interface)
        if not link:
            return
        if link.endpoint_a == interface:
            other_interface = link.endpoint_b
        else:
            other_interface = link.endpoint_a
        interface.activate()
        if other_interface.is_active() is False:
            return
        if link.is_active() is False:
            link.update_metadata('last_status_change', time.time())
            link.activate()

            # As each run of this method uses a different thread,
            # there is no risk this sleep will lock the NApp.
            time.sleep(self.link_up_timer)

            last_status_change = link.get_metadata('last_status_change')
            now = time.time()
            if link.is_active() and \
                    now - last_status_change >= self.link_up_timer:
                self.notify_topology_update()
                self.update_instance_metadata(link)
                self.notify_link_status_change(link)

    @listen_to('.*.switch.interface.link_down')
    def handle_interface_link_down(self, event):
        """Update the topology based on a Port Modify event.

        The event notifies that an interface's link was changed to 'down'.
        """
        interface = event.content['interface']
        self.handle_link_down(interface)

    @listen_to('kytos/maintenance.start_switch')
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
            link.update_metadata('last_status_change', time.time())
            self.notify_topology_update()
            self.notify_link_status_change(link)

    @listen_to('.*.interface.is.nni')
    def add_links(self, event):
        """Update the topology with links related to the NNI interfaces."""
        interface_a = event.content['interface_a']
        interface_b = event.content['interface_b']

        link = self._get_link_or_create(interface_a, interface_b)
        interface_a.update_link(link)
        interface_b.update_link(link)

        interface_a.nni = True
        interface_b.nni = True

        self.notify_topology_update()

    # def add_host(self, event):
    #    """Update the topology with a new Host."""

    #    interface = event.content['port']
    #    mac = event.content['reachable_mac']

    #    host = Host(mac)
    #    link = self.topology.get_link(interface.id)
    #    if link is not None:
    #        return

    #    self.topology.add_link(interface.id, host.id)
    #    self.topology.add_device(host)

    #    if settings.DISPLAY_FULL_DUPLEX_LINKS:
    #        self.topology.add_link(host.id, interface.id)

    # pylint: disable=unused-argument
    @listen_to('.*.network_status.updated')
    def save_status_on_storehouse(self, event=None):
        """Save the network administrative status using storehouse."""
        status = self._get_switches_dict()
        status['id'] = 'network_status'
        if event:
            content = event.content
            log.info(f"Storing the administrative state of the"
                     f" {content['attribute']} attribute to"
                     f" {content['state']} in the interfaces"
                     f" {content['interface_ids']}")
        status.update(self._get_links_dict())
        self.storehouse.save_status(status)

    def notify_topology_update(self):
        """Send an event to notify about updates on the topology."""
        name = 'kytos/topology.updated'
        event = KytosEvent(name=name, content={'topology':
                                               self._get_topology()})
        self.controller.buffers.app.put(event)

    def notify_link_status_change(self, link):
        """Send an event to notify about a status change on a link."""
        name = 'kytos/topology.'
        if link.is_active():
            status = 'link_up'
        else:
            status = 'link_down'
        event = KytosEvent(name=name+status, content={'link': link})
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

        name = f'kytos/topology.{entities}.metadata.{action}'
        event = KytosEvent(name=name, content={entity: obj,
                                               'metadata': obj.metadata})
        self.controller.buffers.app.put(event)
        log.debug(f'Metadata from {obj.id} was {action}.')

    @listen_to('.*.switch.port.created')
    def notify_port_created(self, original_event):
        """Notify when a port is created."""
        name = 'kytos/topology.port.created'
        event = KytosEvent(name=name, content=original_event.content)
        self.controller.buffers.app.put(event)

    @listen_to('kytos/topology.*.metadata.*')
    def save_metadata_on_store(self, event):
        """Send to storehouse the data updated."""
        name = 'kytos.storehouse.update'
        if 'switch' in event.content:
            store = self.store_items.get('switches')
            obj = event.content.get('switch')
            namespace = 'kytos.topology.switches.metadata'
        elif 'interface' in event.content:
            store = self.store_items.get('interfaces')
            obj = event.content.get('interface')
            namespace = 'kytos.topology.iterfaces.metadata'
        elif 'link' in event.content:
            store = self.store_items.get('links')
            obj = event.content.get('link')
            namespace = 'kytos.topology.links.metadata'

        store.data[obj.id] = obj.metadata
        content = {'namespace': namespace,
                   'box_id': store.box_id,
                   'data': store.data,
                   'callback': self.update_instance}

        event = KytosEvent(name=name, content=content)
        self.controller.buffers.app.put(event)

    @staticmethod
    def update_instance(event, _data, error):
        """Display in Kytos console if the data was updated."""
        entities = event.content.get('namespace', '').split('.')[-2]
        if error:
            log.error(f'Error trying to update storehouse {entities}.')
        else:
            log.debug(f'Storehouse update to entities: {entities}.')

    def verify_storehouse(self, entities):
        """Request a list of box saved by specific entity."""
        name = 'kytos.storehouse.list'
        content = {'namespace': f'kytos.topology.{entities}.metadata',
                   'callback': self.request_retrieve_entities}
        event = KytosEvent(name=name, content=content)
        self.controller.buffers.app.put(event)
        log.info(f'verify data in storehouse for {entities}.')

    def request_retrieve_entities(self, event, data, _error):
        """Create a box or retrieve an existent box from storehouse."""
        msg = ''
        content = {'namespace': event.content.get('namespace'),
                   'callback': self.load_from_store,
                   'data': {}}

        if not data:
            name = 'kytos.storehouse.create'
            msg = 'Create new box in storehouse'
        else:
            name = 'kytos.storehouse.retrieve'
            content['box_id'] = data[0]
            msg = 'Retrieve data from storeohouse.'

        event = KytosEvent(name=name, content=content)
        self.controller.buffers.app.put(event)
        log.debug(msg)

    def load_from_store(self, event, box, error):
        """Save the data retrived from storehouse."""
        entities = event.content.get('namespace', '').split('.')[-2]
        if error:
            log.error('Error while get a box from storehouse.')
        else:
            self.store_items[entities] = box
            log.debug('Data updated')

    def update_instance_metadata(self, obj):
        """Update object instance with saved metadata."""
        metadata = None
        if isinstance(obj, Interface):
            all_metadata = self.store_items.get('interfaces', None)
            if all_metadata:
                metadata = all_metadata.data.get(obj.id)
        elif isinstance(obj, Switch):
            all_metadata = self.store_items.get('switches', None)
            if all_metadata:
                metadata = all_metadata.data.get(obj.id)
        elif isinstance(obj, Link):
            all_metadata = self.store_items.get('links', None)
            if all_metadata:
                metadata = all_metadata.data.get(obj.id)

        if metadata:
            obj.extend_metadata(metadata)
            log.debug(f'Metadata to {obj.id} was updated')

    @listen_to('kytos/maintenance.start_link')
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
            self.notify_link_status_change(link)

    @listen_to('kytos/maintenance.end_link')
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
            self.notify_link_status_change(link)
