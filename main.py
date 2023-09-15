"""Main module of kytos/topology Kytos Network Application.

Manage the network topology
"""
# pylint: disable=wrong-import-order
import pathlib
import time
from collections import defaultdict
from datetime import timezone
from threading import Lock
from typing import List, Optional

from kytos.core import KytosEvent, KytosNApp, log, rest
from kytos.core.common import EntityStatus
from kytos.core.exceptions import (KytosLinkCreationError,
                                   KytosSetTagRangeError,
                                   KytosTagtypeNotSupported)
from kytos.core.helpers import listen_to, load_spec, now, validate_openapi
from kytos.core.interface import Interface
from kytos.core.link import Link
from kytos.core.rest_api import (HTTPException, JSONResponse, Request,
                                 content_type_json_or_415, get_json_or_400)
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

    spec = load_spec(pathlib.Path(__file__).parent / "openapi.yml")

    def setup(self):
        """Initialize the NApp's links list."""
        self.links = {}
        self.intf_available_tags = {}
        self.link_up_timer = getattr(settings, 'LINK_UP_TIMER',
                                     DEFAULT_LINK_UP_TIMER)

        self._links_lock = Lock()
        self._interface_lock = Lock()
        self._links_notify_lock = defaultdict(Lock)
        # to keep track of potential unorded scheduled interface events
        self._intfs_lock = defaultdict(Lock)
        self._intfs_updated_at = {}
        self._intfs_tags_updated_at = {}
        self.link_up = set()
        self.link_status_lock = Lock()
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

    def _get_metadata(self, request: Request) -> dict:
        """Return a JSON with metadata."""
        content_type_json_or_415(request)
        metadata = get_json_or_400(request, self.controller.loop)
        if not isinstance(metadata, dict):
            raise HTTPException(400, "Invalid metadata value: {metadata}")
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
        for link in list(self.links.values()):
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

        # These ones are just runtime active southbound protocol data
        # It won't be stored in the future, only kept in the runtime.
        # Also network operators can follow logs to track this state changes
        for key in (
            "last_status_is_active", "last_status_change", "notified_up_at"
        ):
            link_att["metadata"].pop(key, None)

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
        with self._interface_lock:
            self.load_interfaces_tags_values(switch, intf_details)

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
    def get_topology(self, _request: Request) -> JSONResponse:
        """Return the latest known topology.

        This topology is updated when there are network events.
        """
        return JSONResponse(self._get_topology_dict())

    # Switch related methods
    @rest('v3/switches')
    def get_switches(self, _request: Request) -> JSONResponse:
        """Return a json with all the switches in the topology."""
        return JSONResponse(self._get_switches_dict())

    @rest('v3/switches/{dpid}/enable', methods=['POST'])
    def enable_switch(self, request: Request) -> JSONResponse:
        """Administratively enable a switch in the topology."""
        dpid = request.path_params["dpid"]
        try:
            switch = self.controller.switches[dpid]
            self.topo_controller.enable_switch(dpid)
            switch.enable()
        except KeyError:
            raise HTTPException(404, detail="Switch not found")

        self.notify_switch_enabled(dpid)
        self.notify_topology_update()
        self.notify_switch_links_status(switch, "link enabled")
        return JSONResponse("Operation successful", status_code=201)

    @rest('v3/switches/{dpid}/disable', methods=['POST'])
    def disable_switch(self, request: Request) -> JSONResponse:
        """Administratively disable a switch in the topology."""
        dpid = request.path_params["dpid"]
        try:
            switch = self.controller.switches[dpid]
            self.topo_controller.disable_switch(dpid)
            switch.disable()
        except KeyError:
            raise HTTPException(404, detail="Switch not found")

        self.notify_switch_disabled(dpid)
        self.notify_topology_update()
        self.notify_switch_links_status(switch, "link disabled")
        return JSONResponse("Operation successful", status_code=201)

    @rest('v3/switches/{dpid}/metadata')
    def get_switch_metadata(self, request: Request) -> JSONResponse:
        """Get metadata from a switch."""
        dpid = request.path_params["dpid"]
        try:
            metadata = self.controller.switches[dpid].metadata
            return JSONResponse({"metadata": metadata})
        except KeyError:
            raise HTTPException(404, detail="Switch not found")

    @rest('v3/switches/{dpid}/metadata', methods=['POST'])
    def add_switch_metadata(self, request: Request) -> JSONResponse:
        """Add metadata to a switch."""
        dpid = request.path_params["dpid"]
        metadata = self._get_metadata(request)
        try:
            switch = self.controller.switches[dpid]
        except KeyError:
            raise HTTPException(404, detail="Switch not found")

        self.topo_controller.add_switch_metadata(dpid, metadata)
        switch.extend_metadata(metadata)
        self.notify_metadata_changes(switch, 'added')
        return JSONResponse("Operation successful", status_code=201)

    @rest('v3/switches/{dpid}/metadata/{key}', methods=['DELETE'])
    def delete_switch_metadata(self, request: Request) -> JSONResponse:
        """Delete metadata from a switch."""
        dpid = request.path_params["dpid"]
        key = request.path_params["key"]
        try:
            switch = self.controller.switches[dpid]
        except KeyError:
            raise HTTPException(404, detail="Switch not found")

        try:
            _ = switch.metadata[key]
        except KeyError:
            raise HTTPException(404, "Metadata not found")

        self.topo_controller.delete_switch_metadata_key(dpid, key)
        switch.remove_metadata(key)
        self.notify_metadata_changes(switch, 'removed')
        return JSONResponse("Operation successful")

    # Interface related methods
    @rest('v3/interfaces')
    def get_interfaces(self, _request: Request) -> JSONResponse:
        """Return a json with all the interfaces in the topology."""
        interfaces = {}
        switches = self._get_switches_dict()
        for switch in switches['switches'].values():
            for interface_id, interface in switch['interfaces'].items():
                interfaces[interface_id] = interface

        return JSONResponse({'interfaces': interfaces})

    @rest('v3/interfaces/switch/{dpid}/enable', methods=['POST'])
    @rest('v3/interfaces/{interface_enable_id}/enable', methods=['POST'])
    def enable_interface(self, request: Request) -> JSONResponse:
        """Administratively enable interfaces in the topology."""
        interface_enable_id = request.path_params.get("interface_enable_id")
        dpid = request.path_params.get("dpid")
        if dpid is None:
            dpid = ":".join(interface_enable_id.split(":")[:-1])
        try:
            switch = self.controller.switches[dpid]
        except KeyError:
            raise HTTPException(404, detail="Switch not found")

        if interface_enable_id:
            interface_number = int(interface_enable_id.split(":")[-1])

            try:
                interface = switch.interfaces[interface_number]
                self.topo_controller.enable_interface(interface.id)
                interface.enable()
                self.notify_interface_link_status(interface, "link enabled")
            except KeyError:
                msg = f"Switch {dpid} interface {interface_number} not found"
                raise HTTPException(404, detail=msg)
        else:
            for interface in switch.interfaces.copy().values():
                interface.enable()
                self.notify_interface_link_status(interface, "link enabled")
            self.topo_controller.upsert_switch(switch.id, switch.as_dict())
        self.notify_topology_update()
        return JSONResponse("Operation successful")

    @rest('v3/interfaces/switch/{dpid}/disable', methods=['POST'])
    @rest('v3/interfaces/{interface_disable_id}/disable', methods=['POST'])
    def disable_interface(self, request: Request) -> JSONResponse:
        """Administratively disable interfaces in the topology."""
        interface_disable_id = request.path_params.get("interface_disable_id")
        dpid = request.path_params.get("dpid")
        if dpid is None:
            dpid = ":".join(interface_disable_id.split(":")[:-1])
        try:
            switch = self.controller.switches[dpid]
        except KeyError:
            raise HTTPException(404, detail="Switch not found")

        if interface_disable_id:
            interface_number = int(interface_disable_id.split(":")[-1])

            try:
                interface = switch.interfaces[interface_number]
                self.topo_controller.disable_interface(interface.id)
                interface.disable()
                self.notify_interface_link_status(interface, "link disabled")
            except KeyError:
                msg = f"Switch {dpid} interface {interface_number} not found"
                raise HTTPException(404, detail=msg)
        else:
            for interface in switch.interfaces.copy().values():
                interface.disable()
                self.notify_interface_link_status(interface, "link disabled")
            self.topo_controller.upsert_switch(switch.id, switch.as_dict())
        self.notify_topology_update()
        return JSONResponse("Operation successful")

    @rest('v3/interfaces/{interface_id}/metadata')
    def get_interface_metadata(self, request: Request) -> JSONResponse:
        """Get metadata from an interface."""
        interface_id = request.path_params["interface_id"]
        switch_id = ":".join(interface_id.split(":")[:-1])
        interface_number = int(interface_id.split(":")[-1])
        try:
            switch = self.controller.switches[switch_id]
        except KeyError:
            raise HTTPException(404, detail="Switch not found")

        try:
            interface = switch.interfaces[interface_number]
        except KeyError:
            raise HTTPException(404, detail="Interface not found")

        return JSONResponse({"metadata": interface.metadata})

    @rest('v3/interfaces/{interface_id}/metadata', methods=['POST'])
    def add_interface_metadata(self, request: Request) -> JSONResponse:
        """Add metadata to an interface."""
        interface_id = request.path_params["interface_id"]
        metadata = self._get_metadata(request)
        switch_id = ":".join(interface_id.split(":")[:-1])
        interface_number = int(interface_id.split(":")[-1])
        try:
            switch = self.controller.switches[switch_id]
        except KeyError:
            raise HTTPException(404, detail="Switch not found")

        try:
            interface = switch.interfaces[interface_number]
            self.topo_controller.add_interface_metadata(interface.id, metadata)
        except KeyError:
            raise HTTPException(404, detail="Interface not found")

        interface.extend_metadata(metadata)
        self.notify_metadata_changes(interface, 'added')
        return JSONResponse("Operation successful", status_code=201)

    @rest('v3/interfaces/{interface_id}/metadata/{key}', methods=['DELETE'])
    def delete_interface_metadata(self, request: Request) -> JSONResponse:
        """Delete metadata from an interface."""
        interface_id = request.path_params["interface_id"]
        key = request.path_params["key"]
        switch_id = ":".join(interface_id.split(":")[:-1])
        try:
            interface_number = int(interface_id.split(":")[-1])
        except ValueError:
            detail = f"Invalid interface_id {interface_id}"
            raise HTTPException(400, detail=detail)

        try:
            switch = self.controller.switches[switch_id]
        except KeyError:
            raise HTTPException(404, detail="Switch not found")

        try:
            interface = switch.interfaces[interface_number]
        except KeyError:
            raise HTTPException(404, detail="Interface not found")

        try:
            _ = interface.metadata[key]
        except KeyError:
            raise HTTPException(404, detail="Metadata not found")

        self.topo_controller.delete_interface_metadata_key(interface.id, key)
        interface.remove_metadata(key)
        self.notify_metadata_changes(interface, 'removed')
        return JSONResponse("Operation successful")

    @staticmethod
    def map_singular_values(tag_range):
        """Change integer or singular interger list to
        list[int, int] when necessary"""
        if isinstance(tag_range, int):
            tag_range = [tag_range] * 2
        elif len(tag_range) == 1:
            tag_range = [tag_range[0]] * 2
        return tag_range

    def _get_tag_ranges(self, content: dict):
        """Get tag_ranges and check validity:
        - It should be ordered
        - Not unnecessary partition (eg. [[10,20],[20,30]])
        - Singular intergers are changed to ranges (eg. [10] to [[10, 10]])
        The ranges are understood as [inclusive, inclusive]"""
        ranges = content["tag_ranges"]
        if len(ranges) < 1:
            detail = "tag_ranges is empty"
            raise HTTPException(400, detail=detail)
        last_tag = 0
        ranges_n = len(ranges)
        for i in range(0, ranges_n):
            ranges[i] = self.map_singular_values(ranges[i])
            if ranges[i][0] > ranges[i][1]:
                detail = f"The range {ranges[i]} is not ordered"
                raise HTTPException(400, detail=detail)
            if last_tag and last_tag > ranges[i][0]:
                detail = f"tag_ranges is not ordered. {last_tag}"\
                         f" is higher than {ranges[i][0]}"
                raise HTTPException(400, detail=detail)
            if last_tag and last_tag == ranges[i][0] - 1:
                detail = f"tag_ranges has an unnecessary partition. "\
                         f"{last_tag} is before to {ranges[i][0]}"
                raise HTTPException(400, detail=detail)
            if last_tag and last_tag == ranges[i][0]:
                detail = f"tag_ranges has repetition. {ranges[i-1]}"\
                         f" have same values as {ranges[i]}"
                raise HTTPException(400, detail=detail)
            last_tag = ranges[i][1]
        if ranges[-1][1] > 4095:
            detail = "Maximum value for tag_ranges is 4095"
            raise HTTPException(400, detail=detail)
        if ranges[0][0] < 1:
            detail = "Minimum value for tag_ranges is 1"
            raise HTTPException(400, detail=detail)
        return ranges

    @rest('v3/interfaces/{interface_id}/tag_ranges', methods=['POST'])
    @validate_openapi(spec)
    def set_tag_range(self, request: Request) -> JSONResponse:
        """Set tag range"""
        content_type_json_or_415(request)
        content = get_json_or_400(request, self.controller.loop)
        tag_type = content.get("tag_type")
        ranges = self._get_tag_ranges(content)
        interface_id = request.path_params["interface_id"]
        interface = self.controller.get_interface_by_id(interface_id)
        if not interface:
            raise HTTPException(404, detail="Interface not found")
        try:
            interface.set_tag_ranges(ranges, tag_type)
            interface.notify_interface_tags(self.controller)
        except KytosSetTagRangeError as err:
            detail = f"The new tag_ranges cannot be applied {err}"
            raise HTTPException(400, detail=detail)
        except KytosTagtypeNotSupported as err:
            detail = f"Error with tag_type. {err}"
            raise HTTPException(400, detail=detail)
        raise HTTPException(200, detail="Operation Successful")

    @rest('v3/interfaces/{interface_id}/tag_ranges', methods=['DELETE'])
    @validate_openapi(spec)
    def delete_tag_range(self, request: Request) -> JSONResponse:
        """Set tag_range from tag_type to default value [1, 4095]"""
        interface_id = request.path_params["interface_id"]
        params = request.query_params
        tag_type = params.get("tag_type", 'vlan')
        interface = self.controller.get_interface_by_id(interface_id)
        if not interface:
            raise HTTPException(404, detail="Interface not found")
        try:
            interface.remove_tag_ranges(tag_type)
        except KytosTagtypeNotSupported as err:
            detail = f"Error with tag_type. {err}"
            raise HTTPException(400, detail=detail)
        interface.notify_interface_tags(self.controller)
        raise HTTPException(200, detail="Operation Successful")

    # Link related methods
    @rest('v3/links')
    def get_links(self, _request: Request) -> JSONResponse:
        """Return a json with all the links in the topology.

        Links are connections between interfaces.
        """
        return JSONResponse(self._get_links_dict())

    @rest('v3/links/{link_id}/enable', methods=['POST'])
    def enable_link(self, request: Request) -> JSONResponse:
        """Administratively enable a link in the topology."""
        link_id = request.path_params["link_id"]
        try:
            with self._links_lock:
                link = self.links[link_id]
                self.topo_controller.enable_link(link_id)
                link.enable()
        except KeyError:
            raise HTTPException(404, detail="Link not found")
        self.notify_link_status_change(
            self.links[link_id],
            reason='link enabled'
        )
        self.notify_topology_update()
        return JSONResponse("Operation successful", status_code=201)

    @rest('v3/links/{link_id}/disable', methods=['POST'])
    def disable_link(self, request: Request) -> JSONResponse:
        """Administratively disable a link in the topology."""
        link_id = request.path_params["link_id"]
        try:
            with self._links_lock:
                link = self.links[link_id]
                self.topo_controller.disable_link(link_id)
                link.disable()
        except KeyError:
            raise HTTPException(404, detail="Link not found")
        self.notify_link_status_change(
            self.links[link_id],
            reason='link disabled'
        )
        self.notify_topology_update()
        return JSONResponse("Operation successful", status_code=201)

    @rest('v3/links/{link_id}/metadata')
    def get_link_metadata(self, request: Request) -> JSONResponse:
        """Get metadata from a link."""
        link_id = request.path_params["link_id"]
        try:
            return JSONResponse({"metadata": self.links[link_id].metadata})
        except KeyError:
            raise HTTPException(404, detail="Link not found")

    @rest('v3/links/{link_id}/metadata', methods=['POST'])
    def add_link_metadata(self, request: Request) -> JSONResponse:
        """Add metadata to a link."""
        link_id = request.path_params["link_id"]
        metadata = self._get_metadata(request)
        try:
            link = self.links[link_id]
        except KeyError:
            raise HTTPException(404, detail="Link not found")

        self.topo_controller.add_link_metadata(link_id, metadata)
        link.extend_metadata(metadata)
        self.notify_metadata_changes(link, 'added')
        self.notify_topology_update()
        return JSONResponse("Operation successful", status_code=201)

    @rest('v3/links/{link_id}/metadata/{key}', methods=['DELETE'])
    def delete_link_metadata(self, request: Request) -> JSONResponse:
        """Delete metadata from a link."""
        link_id = request.path_params["link_id"]
        key = request.path_params["key"]
        try:
            link = self.links[link_id]
        except KeyError:
            raise HTTPException(404, detail="Link not found")

        try:
            _ = link.metadata[key]
        except KeyError:
            raise HTTPException(404, detail="Metadata not found")

        self.topo_controller.delete_link_metadata_key(link.id, key)
        link.remove_metadata(key)
        self.notify_metadata_changes(link, 'removed')
        self.notify_topology_update()
        return JSONResponse("Operation successful")

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

    @listen_to("kytos/core.interface_tags")
    def on_interface_tags(self, event):
        """Handle on_interface_tags."""
        interface = event.content['interface']
        with self._intfs_lock[interface.id]:
            if (
                interface.id in self._intfs_tags_updated_at
                and self._intfs_tags_updated_at[interface.id] > event.timestamp
            ):
                return
            self._intfs_tags_updated_at[interface.id] = event.timestamp
        self.handle_on_interface_tags(interface)

    def handle_on_interface_tags(self, interface):
        """Update interface details"""
        intf_id = interface.id
        self.topo_controller.upsert_interface_details(
            intf_id, interface.available_tags, interface.tag_ranges
        )

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
        if not interface.is_active():
            return
        self.handle_interface_link_up(interface, event)

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
        with self._intfs_lock[interface.id]:
            if (
                interface.id in self._intfs_updated_at
                and self._intfs_updated_at[interface.id] > event.timestamp
            ):
                return
            self._intfs_updated_at[interface.id] = event.timestamp
        interface.deactivate()
        self.handle_interface_link_down(interface, event)

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
        self.handle_interface_link_up(interface, event)

    def handle_interface_link_up(self, interface, event):
        """Update the topology based on a Port Modify event."""
        with self._intfs_lock[interface.id]:
            if (
                interface.id in self._intfs_updated_at
                and self._intfs_updated_at[interface.id] > event.timestamp
            ):
                return
            self._intfs_updated_at[interface.id] = event.timestamp
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

    def notify_link_up_if_status(self, link, reason="link up") -> None:
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
            self.notify_topology_update()
            self.notify_link_status_change(link, reason)

    def handle_link_up(self, interface):
        """Handle link up for an interface."""
        with self._links_lock:
            link = self._get_link_from_interface(interface)
            if not link:
                self.notify_topology_update()
                return
            other_interface = (
                link.endpoint_b if link.endpoint_a == interface
                else link.endpoint_a
            )
            if other_interface.is_active() is False:
                self.notify_topology_update()
                return
            metadata = {
                'last_status_change': time.time(),
                'last_status_is_active': True
            }
            link.extend_metadata(metadata)
            link.activate()
            self.notify_topology_update()
        self.notify_link_up_if_status(link, "link up")

    @listen_to('.*.switch.interface.link_down')
    def on_interface_link_down(self, event):
        """Update the topology based on a Port Modify event.

        The event notifies that an interface's link was changed to 'down'.
        """
        interface = event.content['interface']
        self.handle_interface_link_down(interface, event)

    def handle_interface_link_down(self, interface, event):
        """Update the topology based on an interface."""
        with self._intfs_lock[interface.id]:
            if (
                interface.id in self._intfs_updated_at
                and self._intfs_updated_at[interface.id] > event.timestamp
            ):
                return
            self._intfs_updated_at[interface.id] = event.timestamp
        self.handle_link_down(interface)

    def handle_link_down(self, interface):
        """Notify a link is down."""
        with self._links_lock:
            link = self._get_link_from_interface(interface)
            if not link or not link.get_metadata("last_status_is_active"):
                self.notify_topology_update()
                return
            link.deactivate()
            metadata = {
                "last_status_change": time.time(),
                "last_status_is_active": False,
            }
            link.extend_metadata(metadata)
            self.notify_link_status_change(link, reason="link down")
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
        self.notify_link_up_if_status(link, "link up")

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

    def notify_switch_links_status(self, switch, reason):
        """Send an event to notify the status of a link in a switch"""
        with self._links_lock:
            for link in self.links.values():
                if switch in (link.endpoint_a.switch, link.endpoint_b.switch):
                    if reason == "link enabled":
                        name = 'kytos/topology.notify_link_up_if_status'
                        content = {'reason': reason, "link": link}
                        event = KytosEvent(name=name, content=content)
                        self.controller.buffers.app.put(event)
                    else:
                        self.notify_link_status_change(link, reason)

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

    def notify_interface_link_status(self, interface, reason):
        """Send an event to notify the status of a link from
        an interface."""
        link = self._get_link_from_interface(interface)
        if link:
            if reason == "link enabled":
                name = 'kytos/topology.notify_link_up_if_status'
                content = {'reason': reason, "link": link}
                event = KytosEvent(name=name, content=content)
                self.controller.buffers.app.put(event)
            else:
                self.notify_link_status_change(link, reason)

    def notify_link_status_change(self, link, reason='not given'):
        """Send an event to notify about a status change on a link."""
        link_id = link.id
        with self.link_status_lock:
            if (
                (not link.status_reason and link.status == EntityStatus.UP)
                and link_id not in self.link_up
            ):
                self.link_up.add(link_id)
                event = KytosEvent(
                    name='kytos/topology.link_up',
                    content={
                        'link': link,
                        'reason': reason
                    },
                )
            elif (
                (link.status_reason or link.status != EntityStatus.UP)
                and link_id in self.link_up
            ):
                self.link_up.remove(link_id)
                event = KytosEvent(
                    name='kytos/topology.link_down',
                    content={
                        'link': link,
                        'reason': reason
                    },
                )
            else:
                return
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

    @listen_to('kytos/topology.notify_link_up_if_status')
    def on_notify_link_up_if_status(self, event):
        """Tries to notify link up and topology changes"""
        link = event.content["link"]
        reason = event.content["reason"]
        self.notify_link_up_if_status(link, reason)

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
    def load_interfaces_tags_values(switch: Switch,
                                    interfaces_details: List[dict]) -> None:
        """Load interfaces available tags (vlans)."""
        if not interfaces_details:
            return
        for interface_details in interfaces_details:
            available_tags = interface_details['available_tags']
            if not available_tags:
                continue
            log.debug(f"Interface id {interface_details['id']} loading "
                      f"{len(available_tags)} "
                      "available tags")
            port_number = int(interface_details["id"].split(":")[-1])
            interface = switch.interfaces[port_number]
            interface.set_available_tags_tag_ranges(
                available_tags,
                interface_details['tag_ranges']
            )

    @listen_to('topology.interruption.start')
    def on_interruption_start(self, event: KytosEvent):
        """Deals with the start of service interruption."""
        with self._links_lock:
            self.handle_interruption_start(event)

    def handle_interruption_start(self, event: KytosEvent):
        """Deals with the start of service interruption."""
        interrupt_type = event.content['type']
        switches = event.content.get('switches', [])
        interfaces = event.content.get('interfaces', [])
        links = event.content.get('links', [])
        log.info(
            'Received interruption start of type \'%s\' '
            'affecting switches %s, interfaces %s, links %s',
            interrupt_type,
            switches,
            interfaces,
            links
        )
        # for switch_id in switches:
        #     pass
        # for interface_id in interfaces:
        #     pass
        for link_id in links:
            link = self.links.get(link_id)
            if link is None:
                log.error(
                    "Invalid link id '%s' for interruption of type '%s;",
                    link_id,
                    interrupt_type
                )
            else:
                self.notify_link_status_change(link, interrupt_type)
        self.notify_topology_update()

    @listen_to('topology.interruption.end')
    def on_interruption_end(self, event: KytosEvent):
        """Deals with the end of service interruption."""
        with self._links_lock:
            self.handle_interruption_end(event)

    def handle_interruption_end(self, event: KytosEvent):
        """Deals with the end of service interruption."""
        interrupt_type = event.content['type']
        switches = event.content.get('switches', [])
        interfaces = event.content.get('interfaces', [])
        links = event.content.get('links', [])
        log.info(
            'Received interruption end of type \'%s\' '
            'affecting switches %s, interfaces %s, links %s',
            interrupt_type,
            switches,
            interfaces,
            links
        )
        # for switch_id in switches:
        #     pass
        # for interface_id in interfaces:
        #     pass
        for link_id in links:
            link = self.links.get(link_id)
            if link is None:
                log.error(
                    "Invalid link id '%s' for interruption of type '%s;",
                    link_id,
                    interrupt_type
                )
            else:
                self.notify_link_status_change(link, interrupt_type)
        self.notify_topology_update()
