"""Main module of kytos/topology Kytos Network Application.

Manage the network topology
"""
# pylint: disable=wrong-import-order
import pathlib
import time
from collections import defaultdict
from contextlib import ExitStack
from copy import deepcopy
from datetime import timezone
from threading import Lock
from typing import Iterable, Optional

import httpx
import tenacity
from tenacity import (retry_if_exception_type, stop_after_attempt,
                      wait_combine, wait_fixed, wait_random)

from kytos.core import KytosEvent, KytosNApp, log, rest
from kytos.core.common import EntityStatus, GenericEntity
from kytos.core.exceptions import (KytosInvalidTagRanges,
                                   KytosLinkCreationError, KytosTagError)
from kytos.core.helpers import listen_to, load_spec, now, validate_openapi
from kytos.core.interface import Interface
from kytos.core.link import Link
from kytos.core.rest_api import (HTTPException, JSONResponse, Request,
                                 content_type_json_or_415, get_json_or_400)
from kytos.core.retry import before_sleep
from kytos.core.switch import Switch
from kytos.core.tag_capable import TAGCapable
from kytos.core.tag_ranges import (get_tag_ranges, range_addition,
                                   range_difference, range_intersection)
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
        self.link_up_timer = getattr(settings, 'LINK_UP_TIMER',
                                     DEFAULT_LINK_UP_TIMER)

        # to keep track of potential unorded scheduled interface events
        self._intfs_lock = defaultdict(Lock)
        self._intfs_updated_at = {}
        self._intfs_tags_updated_at = {}
        self._link_tags_updated_at = {}
        self.link_up = set()
        self.link_status_lock = Lock()
        self._switch_lock = defaultdict(Lock)
        self.topo_controller = self.get_topo_controller()

        # Track when we last received a link up, that resulted in
        # activating a deactivated link.
        self.link_status_change = defaultdict[str, dict](dict)
        Link.register_status_func(f"{self.napp_id}_link_up_timer",
                                  self.link_status_hook_link_up_timer)
        Link.register_status_reason_func(f"{self.napp_id}_mismatched_reason",
                                         self.detect_mismatched_link)
        Link.register_status_func(f"{self.napp_id}_mismatched_status",
                                  self.link_status_mismatched)
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
                          self.controller.links.copy().values()}}

    def _get_topology_dict(self):
        """Return a dictionary with the known topology."""
        return {'topology': {**self._get_switches_dict(),
                             **self._get_links_dict()}}

    def _get_topology(self):
        """Return an object representing the topology."""
        return Topology(self.controller.switches.copy(),
                        self.controller.links.copy())

    def _load_links(
        self,
        links_att: dict[str, dict]
    ) -> tuple[dict[str, Switch], dict[str, Exception]]:
        link_success = {}
        link_failure = {}
        log.debug(f"_load_network_status links={links_att}")
        for link_id, link_att in links_att.items():
            try:
                endpoint_a = link_att['endpoint_a']['id']
                endpoint_b = link_att['endpoint_b']['id']
                log.info(f"Loading link: {link_id}")
                interface_a = self.controller.get_interface_by_id(endpoint_a)
                interface_b = self.controller.get_interface_by_id(endpoint_b)

                error = f"Fail to load endpoints for link {link_id}. "
                if not interface_a:
                    raise RestoreError(
                        f"{error}, endpoint_a {endpoint_a} not found"
                    )
                if not interface_b:
                    raise RestoreError(
                        f"{error}, endpoint_b {endpoint_b} not found"
                    )

                link, _ = self.controller.get_link_or_create(
                    interface_a,
                    interface_b,
                    link_att,
                )
                link_success[link_id] = link
            except (KeyError, AttributeError, TypeError) as err:
                link_failure[link_id] = err
                log.error(f'Error loading link {link_id}: {err}')
        return link_success, link_failure

    def _load_switches(
        self,
        switches_att: dict[str, dict]
    ) -> tuple[dict[str, Switch], dict[str, Exception]]:
        switch_success = {}
        switch_err = {}
        log.debug(f"_load_network_status switches={switches_att}")
        for switch_id, switch_att in switches_att.items():
            try:
                log.info(f'Loading switch dpid: {switch_id}')
                switch = self.controller.get_switch_or_create(switch_id)
                if switch_att['enabled']:
                    switch.enable()
                else:
                    switch.disable()
                switch.description['manufacturer'] = switch_att.get(
                    'manufacturer', ''
                )
                switch.description['hardware'] = switch_att.get('hardware', '')
                switch.description['software'] = switch_att.get('software')
                switch.description['serial'] = switch_att.get('serial', '')
                switch.description['data_path'] = switch_att.get(
                    'data_path', ''
                )
                switch.extend_metadata(switch_att["metadata"])

                self._load_interfaces(
                    switch,
                    switch_att.get('interfaces', {})
                )

                switch_success[switch_id] = switch
            except (KeyError, AttributeError, TypeError) as err:
                switch_err[switch_id] = err
                log.error(f'Error loading switch: {err}')
        return switch_success, switch_err

    def _load_interfaces(
        self,
        switch: Switch,
        interfaces_att: dict[str, dict]
    ):
        for iface_id, iface_att in interfaces_att.items():
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
            event = KytosEvent(
                name=name,
                content={
                    'switch': switch.id,
                    'port': interface.port_number,
                    'port_description': {
                        'alias': interface.name,
                        'mac': interface.address,
                        'state': interface.state
                    }
                }
            )
            self.controller.buffers.app.put(event, timeout=1)

    def _load_interface_details(
        self,
        interfaces: dict[str, Interface]
    ):
        intf_details = self.topo_controller.get_interfaces_details(
            list(interfaces)
        )
        self._load_details(
            interfaces,
            intf_details
        )

    def _load_link_details(
        self,
        links: dict[str, Link]
    ):
        link_details = self.topo_controller.get_links_details(
            list(links)
        )
        self._load_details(
            links,
            link_details
        )

    # pylint: disable=attribute-defined-outside-init
    def load_topology(self):
        """Load network topology from DB."""
        topology = self.topo_controller.get_topology()
        switches = topology["topology"]["switches"]
        links = topology["topology"]["links"]

        success_switches, failed_switches = self._load_switches(switches)
        success_links, failed_links = self._load_links(links)

        interfaces = {}
        for switch in success_switches.values():
            interfaces.update(
                {
                    interface.id: interface
                    for interface in switch.interfaces.values()
                }
            )

        self._load_interface_details(interfaces)
        self._load_link_details(success_links)

        next_topology = self._get_topology()
        name = 'kytos/topology.topology_loaded'
        event = KytosEvent(
            name=name,
            content={
                'topology': next_topology,
                'failed_switches': failed_switches,
                'failed_links': failed_links
            })
        self.controller.buffers.app.put(event, timeout=1)
        self.last_pushed_topology = next_topology

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

        self.notify_topology_update()
        self.notify_switch_enabled(dpid)
        self.notify_switch_links_status(switch, "link enabled")
        return JSONResponse("Operation successful", status_code=201)

    @rest('v3/switches/{dpid}/disable', methods=['POST'])
    def disable_switch(self, request: Request) -> JSONResponse:
        """Administratively disable a switch in the topology."""
        dpid = request.path_params["dpid"]
        try:
            switch = self.controller.switches[dpid]
        except KeyError:
            raise HTTPException(404, detail="Switch not found")
        disabled_links = set()
        with ExitStack() as stack:
            stack.enter_context(self.controller.switches_lock)

            stack.enter_context(switch.lock)
            links_to_disable = dict[str, Link]()
            for _, interface in switch.interfaces.copy().items():
                link = interface.link
                if link:
                    links_to_disable[link.id] = link

            for link in links_to_disable.values():
                stack.enter_context(link.lock)
                if link.is_enabled():
                    disabled_links.add(link.id)
                    link.disable()
                    self.notify_link_enabled_state(
                        link, "disabled"
                    )
            self.topo_controller.bulk_disable_links(disabled_links)
            self.topo_controller.disable_switch(dpid)
            switch.disable()
        self.notify_topology_update()
        self.notify_switch_disabled(dpid)
        self.notify_switch_links_status(switch, "link disabled")
        return JSONResponse("Operation successful", status_code=201)

    @rest('v3/switches/{dpid}', methods=['DELETE'])
    def delete_switch(self, request: Request) -> JSONResponse:
        """Delete a switch.

        Requirements:
            - There should not be installed flows related to switch.
            - The switch should be disabled.
            - All tags from switch interfaces should be available.
            - The switch should not have links.
        """
        dpid = request.path_params["dpid"]
        with ExitStack() as stack:
            stack.enter_context(self.controller.switches_lock)
            try:
                switch: Switch = self.controller.switches[dpid]
            except KeyError:
                raise HTTPException(404, detail="Switch not found.")

            stack.enter_context(switch.lock)
            if switch.status != EntityStatus.DISABLED:
                raise HTTPException(
                    409, detail="Switch should be disabled."
                )

            for intf_id, interface in switch.interfaces.items():
                stack.enter_context(interface.tag_lock)
                if not interface.all_tags_available():
                    detail = f"Interface {intf_id} vlans are being used."\
                                " Delete any service using vlans."
                    raise HTTPException(409, detail=detail)
                link = interface.link
                if link is not None:
                    raise HTTPException(
                        409, detail=f"Switch should not have links. "
                                    f"Link found {link.id}."
                    )
            try:
                flows = self.get_flows_by_switch(dpid)
            except tenacity.RetryError as err:
                detail = "Error while getting flows: "\
                            f"{err.last_attempt.exception()}."
                raise HTTPException(409, detail=detail)
            if flows:
                raise HTTPException(409, detail="Switch has flows. Verify"
                                                " if a switch is used.")
            switch = self.controller.switches.pop(dpid)
            self.topo_controller.delete_switch_data(dpid)
        name = 'kytos/topology.switch.deleted'
        event = KytosEvent(name=name, content={'switch': switch})
        self.controller.buffers.app.put(event)
        self.notify_topology_update()
        return JSONResponse("Operation successful")

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
        with switch.lock:
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
        with switch.lock:
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
        reason = 'interface enabled'
        if dpid is None:
            dpid, _, interface_number = interface_enable_id.rpartition(":")
            interface_number = int(interface_number)

        with ExitStack() as stack:
            with self.controller.switches_lock:
                try:
                    switch = self.controller.switches[dpid]
                except KeyError:
                    raise HTTPException(404, detail="Switch not found")
                stack.enter_context(switch.lock)

            if not switch.is_enabled():
                raise HTTPException(409, detail="Enable Switch first")

            interfaces = list[Interface]()

            if interface_enable_id:
                try:
                    interface = switch.interfaces[interface_number]
                except KeyError:
                    msg = f"Switch {dpid} interface {interface_number} not found"
                    raise HTTPException(404, detail=msg)
                interfaces.append(interface)
            else:
                for interface in switch.interfaces.values():
                    interfaces.append(interface)

            affected_links = dict[str, Link]()
            for interface in interfaces:
                interface.enable()
                link = interface.link
                if link:
                    affected_links[link.id] = link
                self.notify_interface_status(interface, "enabled", reason)

            self._notify_interface_link_status(
                affected_links.values(),
                "link enabled"
            )

            if not interface_enable_id:
                self.topo_controller.enable_interfaces(
                    switch.id,
                    [interface.port_number for interface in interfaces]
                )
            else:
                self.topo_controller.enable_interface(interface.id)

        self.notify_topology_update()
        return JSONResponse("Operation successful")

    @rest('v3/interfaces/switch/{dpid}/disable', methods=['POST'])
    @rest('v3/interfaces/{interface_disable_id}/disable', methods=['POST'])
    def disable_interface(self, request: Request) -> JSONResponse:
        """Administratively disable interfaces in the topology."""
        interface_disable_id: str = request.path_params.get(
            "interface_disable_id"
        )
        dpid = request.path_params.get("dpid")
        reason = 'interface disabled'
        if dpid is None:
            dpid, _, interface_number = interface_disable_id.rpartition(":")
            interface_number = int(interface_number)

        with ExitStack() as stack:
            stack.enter_context(self.controller.switches_lock)
            try:
                switch = self.controller.switches[dpid]
            except KeyError:
                raise HTTPException(404, detail="Switch not found")
            stack.enter_context(switch.lock)

            interfaces = list[Interface]()

            if interface_disable_id:
                try:
                    interface = switch.interfaces[interface_number]
                except KeyError:
                    msg = f"Switch {dpid} interface {interface_number} not found"
                    raise HTTPException(404, detail=msg)
                interfaces.append(interface)
            else:
                for interface in switch.interfaces.values():
                    interfaces = switch.interfaces.copy().values()

            links_to_update = dict[str, Link]()

            for interface in interfaces:
                link = interface.link
                if link:
                    links_to_update[link.id] = link

            link_ids = set[str]()

            for link in links_to_update.values():
                stack.enter_context(link.lock)
                if link.is_enabled():
                    link.disable()
                    self.notify_link_enabled_state(
                        link,
                        "disabled"
                    )
                    link_ids.add(link.id)

            for interface in interfaces:
                interface.disable()
                self.notify_interface_status(interface, "disabled", reason)

            self._notify_interface_link_status(
                links_to_update.values(),
                "link disabled"
            )
            self.topo_controller.bulk_disable_links(link_ids)

            if not interface_disable_id:
                self.topo_controller.disable_interfaces(
                    switch.id,
                    [interface.port_number for interface in interfaces]
                )
            else:
                self.topo_controller.disable_interface(interface.id)

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

        with switch.lock:
            try:
                interface = switch.interfaces[interface_number]
            except KeyError:
                raise HTTPException(404, detail="Interface not found")
            self.topo_controller.add_interface_metadata(interface.id, metadata)
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

        with switch.lock:
            try:
                interface = switch.interfaces[interface_number]
            except KeyError:
                raise HTTPException(404, detail="Interface not found")
            try:
                _ = interface.metadata[key]
            except KeyError:
                raise HTTPException(404, detail="Metadata not found")

            self.topo_controller.delete_interface_metadata_key(
                interface.id,
                key
            )
            interface.remove_metadata(key)
            self.notify_metadata_changes(interface, 'removed')
        return JSONResponse("Operation successful")

    @rest('v3/interfaces/{interface_id}/tag_ranges', methods=['POST'])
    @validate_openapi(spec)
    def set_tag_range(self, request: Request) -> JSONResponse:
        """Set tag range"""
        content_type_json_or_415(request)
        content = get_json_or_400(request, self.controller.loop)
        tag_type = content.get("tag_type", "vlan")
        try:
            ranges = get_tag_ranges(content["tag_ranges"])
        except KytosInvalidTagRanges as err:
            raise HTTPException(400, detail=str(err))
        interface_id = request.path_params["interface_id"]
        interface = self.controller.get_interface_by_id(interface_id)
        if not interface:
            raise HTTPException(404, detail="Interface not found")
        try:
            with ExitStack() as stack:
                link = None
                with self.controller.switches_lock:
                    if interface.link:
                        link = interface.link
                        stack.enter_context(link.tag_lock)
                        endpoints = {
                            link.endpoint_a.id: link.endpoint_a,
                            link.endpoint_b.id: link.endpoint_b,
                        }
                        for endpoint in endpoints.values():
                            stack.enter_context(endpoint.tag_lock)
                    else:
                        stack.enter_context(interface.tag_lock)

                if link and link.is_tag_type_supported(tag_type):
                    tags_in_link = range_intersection(
                        link.default_tag_ranges[tag_type],
                        ranges
                    )
                    if tags_in_link:
                        tags_used_by_link = range_intersection(
                            link.tag_ranges[tag_type],
                            tags_in_link
                        )
                        if tags_used_by_link:
                            raise HTTPException(
                                400,
                                detail=f"Tags {tags_used_by_link} in use by link {link}."
                            )
                        for endpoint in endpoints.values():
                            endpoint_defaults = endpoint.default_tag_ranges[tag_type]
                            new_defaults, conflict = range_addition(
                                endpoint_defaults,
                                tags_in_link
                            )
                            endpoint.default_tag_ranges[tag_type] = new_defaults
                            if conflict:
                                log.warning(
                                    f"{tag_type} default tags {conflict} "
                                    f"already present in endpoint {endpoint}."
                                )
                            self.handle_on_interface_tags(endpoint)
                        new_defaults = range_difference(
                            link.default_tag_ranges[tag_type],
                            tags_in_link
                        )
                        link.default_tag_ranges[tag_type] = new_defaults
                        self.handle_on_link_tags(link)
                interface.set_tag_ranges(tag_type, ranges)
                self.handle_on_interface_tags(interface)
        except KytosTagError as err:
            raise HTTPException(400, detail=str(err))
        return JSONResponse("Operation Successful", status_code=200)

    @rest('v3/interfaces/{interface_id}/tag_ranges', methods=['DELETE'])
    @validate_openapi(spec)
    def delete_tag_range(self, request: Request) -> JSONResponse:
        """Set tag_range from tag_type to default value."""
        interface_id = request.path_params["interface_id"]
        params = request.query_params
        tag_type = params.get("tag_type", 'vlan')
        interface = self.controller.get_interface_by_id(interface_id)
        if not interface:
            raise HTTPException(404, detail="Interface not found")
        try:
            with interface.tag_lock:
                interface.reset_tag_ranges(tag_type)
                self.handle_on_interface_tags(interface)
        except KytosTagError as err:
            raise HTTPException(400, detail=str(err))
        return JSONResponse("Operation Successful", status_code=200)

    @rest('v3/interfaces/{interface_id}/special_tags', methods=['POST'])
    @validate_openapi(spec)
    def set_special_tags(self, request: Request) -> JSONResponse:
        """Set special_tags"""
        content_type_json_or_415(request)
        content = get_json_or_400(request, self.controller.loop)
        tag_type = content.get("tag_type", "vlan")
        special_tags = content["special_tags"]
        interface_id = request.path_params["interface_id"]
        interface = self.controller.get_interface_by_id(interface_id)
        if not interface:
            raise HTTPException(404, detail="Interface not found")
        try:
            with interface.tag_lock:
                interface.set_special_tags(tag_type, special_tags)
                self.handle_on_interface_tags(interface)
        except KytosTagError as err:
            raise HTTPException(400, detail=str(err))
        return JSONResponse("Operation Successful", status_code=200)

    @rest('v3/interfaces/tag_ranges', methods=['GET'])
    @validate_openapi(spec)
    def get_all_tag_ranges(self, _: Request) -> JSONResponse:
        """Get all tag_ranges, available_tags, special_tags
         and special_available_tags from interfaces"""
        result = {}
        for switch in self.controller.switches.copy().values():
            for interface in switch.interfaces.copy().values():
                result[interface.id] = {
                    "default_tag_ranges": interface.default_tag_ranges,
                    "available_tags": interface.available_tags,
                    "tag_ranges": interface.tag_ranges,
                    "default_special_tags": interface.default_special_tags,
                    "special_tags": interface.special_tags,
                    "special_available_tags": interface.special_available_tags,
                }
        return JSONResponse(result, status_code=200)

    @rest('v3/interfaces/{interface_id}/tag_ranges', methods=['GET'])
    @validate_openapi(spec)
    def get_tag_ranges_by_intf(self, request: Request) -> JSONResponse:
        """Get tag_ranges, available_tags, special_tags
         and special_available_tags from an interface"""
        interface_id = request.path_params["interface_id"]
        interface = self.controller.get_interface_by_id(interface_id)
        if not interface:
            raise HTTPException(404, detail="Interface not found")
        result = {
            interface_id: {
                "default_tag_ranges": interface.default_tag_ranges,
                "available_tags": interface.available_tags,
                "tag_ranges": interface.tag_ranges,
                "default_special_tags": interface.default_special_tags,
                "special_tags": interface.special_tags,
                "special_available_tags": interface.special_available_tags,
            }
        }
        return JSONResponse(result, status_code=200)

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
        link = self.controller.get_link(link_id)
        if not link:
            raise HTTPException(404, detail="Link not found")

        endpoints = {
            endpoint.id: endpoint
            for endpoint in (
                link.endpoint_a,
                link.endpoint_b
            )
        }
        switches: dict[str, Switch] = {
            endpoint.switch.id: endpoint.switch
            for endpoint in endpoints.values()
        }

        with ExitStack() as stack:
            with self.controller.switches_lock:
                for switch in switches.values():
                    stack.enter_context(switch.lock)
                stack.enter_context(link.lock)
            for endpoint in endpoints.values():
                if not endpoint.is_enabled():
                    detail = f"{link.endpoint_a.id} needs enabling."
                    raise HTTPException(409, detail=detail)
            if not link.is_enabled():
                self.topo_controller.enable_link(link.id)
                link.enable()
                self.notify_link_enabled_state(link, "enabled")
            self.notify_link_status_change(link, reason='link enabled')
        self.notify_topology_update()
        return JSONResponse("Operation successful", status_code=201)

    @rest('v3/links/{link_id}/disable', methods=['POST'])
    def disable_link(self, request: Request) -> JSONResponse:
        """Administratively disable a link in the topology."""
        link_id = request.path_params["link_id"]
        link = self.controller.get_link(link_id)
        if not link:
            raise HTTPException(404, detail="Link not found")

        with link.lock:
            if link.is_enabled():
                self.topo_controller.disable_link(link.id)
                link.disable()
                self.notify_link_enabled_state(link, "disabled")
            self.notify_link_status_change(link, reason='link disabled')
        self.notify_topology_update()
        return JSONResponse("Operation successful", status_code=201)

    def notify_link_enabled_state(self, link: Link, action: str):
        """Send a KytosEvent whether a link status (enabled/disabled)
         has changed its status."""
        name = f'kytos/topology.link.{action}'
        content = {'link': link}
        event = KytosEvent(name=name, content=content)
        self.controller.buffers.app.put(event)

    @rest('v3/links/{link_id}/metadata')
    def get_link_metadata(self, request: Request) -> JSONResponse:
        """Get metadata from a link."""
        link_id = request.path_params["link_id"]
        link = self.controller.get_link(link_id)
        if not link:
            raise HTTPException(404, detail="Link not found")
        return JSONResponse({"metadata": link.metadata})

    @rest('v3/links/{link_id}/metadata', methods=['POST'])
    def add_link_metadata(self, request: Request) -> JSONResponse:
        """Add metadata to a link."""
        link_id = request.path_params["link_id"]
        metadata = self._get_metadata(request)
        link = self.controller.get_link(link_id)
        if not link:
            raise HTTPException(404, detail="Link not found")

        with link.lock:
            self.topo_controller.add_link_metadata(link_id, metadata)
            link.extend_metadata(metadata)
            self.notify_metadata_changes(link, 'added')
        self.notify_topology_update()
        return JSONResponse("Operation successful", status_code=201)

    @rest('v3/links/{link_id}/tag_ranges', methods=['POST'])
    @validate_openapi(spec)
    def set_link_tag_range(self, request: Request) -> JSONResponse:
        """Set tag range"""
        content_type_json_or_415(request)
        content = get_json_or_400(request, self.controller.loop)
        tag_type = content.get("tag_type", "vlan")
        try:
            ranges = get_tag_ranges(content["tag_ranges"])
        except KytosInvalidTagRanges as err:
            raise HTTPException(400, detail=str(err))
        link_id = request.path_params["link_id"]
        link = self.controller.links.get(link_id)
        if not link:
            raise HTTPException(404, detail="Link not found")
        try:
            with ExitStack() as stack:
                with self.controller.switches_lock:
                    stack.enter_context(link.tag_lock)
                    endpoints = {
                        link.endpoint_a.id: link.endpoint_a,
                        link.endpoint_b.id: link.endpoint_b,
                    }
                    for endpoint in endpoints.values():
                        stack.enter_context(endpoint.tag_lock)

                link.assert_tag_type_supported(
                    tag_type
                )
                tags_not_in_link = range_difference(
                    ranges,
                    link.default_tag_ranges[tag_type]
                )
                if tags_not_in_link:
                    for endpoint in endpoints.values():
                        tags_used_by_interface = range_intersection(
                            endpoint.tag_ranges[tag_type],
                            tags_not_in_link
                        )
                        if tags_used_by_interface:
                            raise HTTPException(
                                400,
                                detail=f"Tags {tags_used_by_interface} "
                                    f"in use by interface {endpoint}."
                            )
                    for endpoint in endpoints.values():
                        endpoint_defaults = endpoint.default_tag_ranges[tag_type]
                        new_defaults = range_difference(
                            endpoint_defaults,
                            tags_not_in_link
                        )
                        missing = range_difference(
                            tags_not_in_link,
                            endpoint_defaults
                        )
                        endpoint.default_tag_ranges[tag_type] = new_defaults
                        if missing:
                            log.warning(
                                f"{tag_type} default tags {missing} "
                                f"missing from endpoint {endpoint}."
                            )
                        self.handle_on_interface_tags(endpoint)
                    new_defaults, conflict = range_addition(
                        link.default_tag_ranges[tag_type],
                        tags_not_in_link
                    )
                    link.default_tag_ranges[tag_type] = new_defaults
                    if conflict:
                        log.warning(
                            f"{tag_type} default tags {missing} "
                            f"already present in link {link}."
                        )
                link.set_tag_ranges(tag_type, ranges)
                self.handle_on_link_tags(link)
        except KytosTagError as err:
            raise HTTPException(400, detail=str(err))
        return JSONResponse("Operation Successful", status_code=200)

    @rest('v3/links/{link_id}/tag_ranges', methods=['DELETE'])
    @validate_openapi(spec)
    def delete_link_tag_range(self, request: Request) -> JSONResponse:
        """Set tag_range from tag_type to default value."""
        link_id = request.path_params["link_id"]
        params = request.query_params
        tag_type = params.get("tag_type", 'vlan')
        link = self.controller.links.get(link_id)
        if not link:
            raise HTTPException(404, detail="Link not found")
        try:
            with link.tag_lock:
                link.reset_tag_ranges(tag_type)
                self.handle_on_interface_tags(link)
        except KytosTagError as err:
            raise HTTPException(400, detail=str(err))
        return JSONResponse("Operation Successful", status_code=200)

    @rest('v3/links/{link_id}/special_tags', methods=['POST'])
    @validate_openapi(spec)
    def set_link_special_tags(self, request: Request) -> JSONResponse:
        """Set special_tags"""
        content_type_json_or_415(request)
        content = get_json_or_400(request, self.controller.loop)
        tag_type = content.get("tag_type", "vlan")
        special_tags = content["special_tags"]
        link_id = request.path_params["link_id"]
        link = self.controller.links.get(link_id)
        if not link:
            raise HTTPException(404, detail="Link not found")
        try:
            with link.tag_lock:
                link.set_special_tags(tag_type, special_tags)
                self.handle_on_interface_tags(link)
        except KytosTagError as err:
            raise HTTPException(400, detail=str(err))
        return JSONResponse("Operation Successful", status_code=200)

    @rest('v3/links/tag_ranges', methods=['GET'])
    @validate_openapi(spec)
    def get_all_link_tag_ranges(self, _: Request) -> JSONResponse:
        """Get all tag_ranges, available_tags, special_tags
         and special_available_tags from links"""
        result = {}
        for link in self.controller.links.copy().values():
            link: Link
            result[link.id] = {
                "available_tags": link.available_tags,
                "tag_ranges": link.tag_ranges,
                "special_tags": link.special_tags,
                "special_available_tags": link.special_available_tags,
                "default_tag_ranges": link.default_tag_ranges,
                "default_special_tags": link.default_special_tags,
            }
        return JSONResponse(result, status_code=200)

    @rest('v3/links/{link_id}/tag_ranges', methods=['GET'])
    @validate_openapi(spec)
    def get_tag_ranges_by_link(self, request: Request) -> JSONResponse:
        """Get tag_ranges, available_tags, special_tags
         and special_available_tags from an interface"""
        link_id = request.path_params["link_id"]
        link = self.controller.links.get(link_id)
        if not link:
            raise HTTPException(404, detail="Interface not found")
        result = {
            link_id: {
                "available_tags": link.available_tags,
                "tag_ranges": link.tag_ranges,
                "special_tags": link.special_tags,
                "special_available_tags": link.special_available_tags,
                "default_tag_ranges": link.default_tag_ranges,
                "default_special_tags": link.default_special_tags,
            }
        }
        return JSONResponse(result, status_code=200)

    @rest('v3/links/{link_id}/metadata/{key}', methods=['DELETE'])
    def delete_link_metadata(self, request: Request) -> JSONResponse:
        """Delete metadata from a link."""
        link_id = request.path_params["link_id"]
        key = request.path_params["key"]
        link = self.controller.get_link(link_id)
        if not link:
            raise HTTPException(404, detail="Link not found")

        with link.lock:
            try:
                _ = link.metadata[key]
            except KeyError:
                raise HTTPException(404, detail="Metadata not found")
            self.topo_controller.delete_link_metadata_key(link.id, key)
            link.remove_metadata(key)
            self.notify_metadata_changes(link, 'removed')
        self.notify_topology_update()
        return JSONResponse("Operation successful")

    @rest('v3/links/{link_id}', methods=['DELETE'])
    def delete_link(self, request: Request) -> JSONResponse:
        """Delete a disabled link from topology.
         It won't work for link with other statuses.
        """
        link_id = request.path_params["link_id"]
        link = self.controller.get_link(link_id)
        if not link:
            raise HTTPException(404, detail="Link not found.")

        endpoints = {
            endpoint.id: endpoint
            for endpoint in (
                link.endpoint_a,
                link.endpoint_b
            )
        }
        switches: dict[str, Switch] = {
            endpoint.switch.id: endpoint.switch
            for endpoint in endpoints.values()
        }
        with ExitStack() as stack:
            stack.enter_context(self.controller.switches_lock)
            for switch in switches.values():
                stack.enter_context(switch.lock)
            stack.enter_context(link.lock)
            stack.enter_context(link.tag_lock)
            for endpoint in endpoints.values():
                stack.enter_context(endpoint.tag_lock)

            if link.status != EntityStatus.DISABLED:
                raise HTTPException(409, detail="Link is not disabled.")

            link_tag_ranges = link.default_tag_ranges
            link_special_tags = link.default_special_tags

            for endpoint in endpoints.values():
                endpoint.link = None
                endpoint.nni = False

                for tag_type in link_tag_ranges:
                    new_tag_ranges, conflict_ranges = range_addition(
                        endpoint.default_tag_ranges.get(tag_type, []),
                        link_tag_ranges[tag_type]
                    )
                    new_special_tags = list(
                        set(endpoint.default_special_tags.get(tag_type, [])) |
                        set(link_special_tags[tag_type])
                    )
                    conflict_special_tags = list(
                        set(endpoint.default_special_tags.get(tag_type, [])) &
                        set(link_special_tags[tag_type])
                    )

                    if conflict_ranges:
                        log.warning(
                            f"{tag_type} default tags {conflict_ranges} "
                            f"already present in endpoint {endpoint}."
                        )
                    if conflict_special_tags:
                        log.warning(
                            f"{tag_type} default special tags {conflict_special_tags} "
                            f"already present in endpoint {endpoint}."
                        )

                    endpoint.set_default_tag_ranges(
                        tag_type,
                        new_tag_ranges,
                        ignore_missing=True
                    )
                    endpoint.set_default_special_tags(
                        tag_type,
                        new_special_tags,
                        ignore_missing=True
                    )

                self.handle_on_interface_tags(endpoint)

            for switch in switches.values():
                self.topo_controller.upsert_switch(
                    switch.id, switch.as_dict()
                )

            # Make tags unusable.
            link.set_available_tags_tag_ranges(
                {}, {}, {}, {}, {}, {},
                link.supported_tag_types
            )

            self.topo_controller.delete_link_from_details(link_id)
            self.topo_controller.delete_link(link_id)
            link = self.controller.links.pop(link_id)
        self.notify_topology_update()
        name = 'kytos/topology.link.deleted'
        event = KytosEvent(name=name, content={'link': link})
        self.controller.buffers.app.put(event)
        return JSONResponse("Operation successful")

    @rest('v3/interfaces/{intf_id}', methods=['DELETE'])
    def delete_interface(self, request: Request) -> JSONResponse:
        """Delete an interface only if it is not used."""
        intf_id = request.path_params.get("intf_id")
        intf_split = intf_id.split(":")
        switch_id = ":".join(intf_split[:-1])
        try:
            intf_port = int(intf_split[-1])
        except ValueError:
            raise HTTPException(400, detail="Invalid interface id.")

        with ExitStack() as stack:
            with self.controller.switches_lock:
                try:
                    switch = self.controller.switches[switch_id]
                except KeyError:
                    raise HTTPException(404, detail="Switch not found.")
                stack.enter_context(switch.lock)
            try:
                interface = switch.interfaces[intf_port]
            except KeyError:
                raise HTTPException(404, detail="Interface not found.")

            usage = self.get_intf_usage(interface)
            if usage:
                raise HTTPException(409, detail=f"Interface could not be "
                                                f"deleted. Reason: {usage}")
            self._delete_interface(interface)
        name = "kytos/topology.interface.deleted"
        event = KytosEvent(name=name, content={"interface": interface})
        self.controller.buffers.app.put(event)
        return JSONResponse("Operation Successful", status_code=200)

    @listen_to(
        "kytos/.*.liveness.(up|down|disabled)",
        pool="dynamic_single"
    )
    def on_link_liveness(self, event) -> None:
        """Handle link liveness up|down|disabled event."""
        liveness_status = event.name.split(".")[-1]
        if liveness_status == "disabled":
            interfaces = event.content["interfaces"]
            self.handle_link_liveness_disabled(interfaces)
        elif liveness_status in ("up", "down"):
            intf_a: Interface = event.content["interface_a"]
            intf_b: Interface = event.content["interface_b"]
            if (intf_a.link is None or
                    intf_b.link is None or
                    intf_a.link != intf_b.link):
                log.error("Link from interfaces "
                          f"{intf_a}, {intf_b}"
                          "not found.")
                return
            self.handle_link_liveness_status(intf_a.link, liveness_status)

    def handle_link_liveness_status(
        self,
        link: Link,
        liveness_status: str
    ) -> None:
        """Handle link liveness."""
        with link.lock:
            metadata = {"liveness_status": liveness_status}
            log.info(f"Link liveness {liveness_status}: {link}")
            link.extend_metadata(metadata)
            self.notify_topology_update()
            if link.status == EntityStatus.UP and liveness_status == "up":
                self.notify_link_status_change(link, reason="liveness_up")
            if link.status == EntityStatus.DOWN and liveness_status == "down":
                self.notify_link_status_change(link, reason="liveness_down")

    def handle_link_liveness_disabled(
        self,
        interfaces: list[Interface]
    ) -> None:
        """Handle link liveness disabled."""
        log.info(f"Link liveness disabled interfaces: {interfaces}")

        key = "liveness_status"

        with ExitStack() as stack:
            stack.enter_context(self.controller.switches_lock)
            switches: dict[str, Switch] = {
                interface.switch.id: interface.switch
                for interface in interfaces
            }

            for switch in switches.values():
                stack.enter_context(switch.lock)

            links = {
                interface.link.id: interface.link
                for interface in interfaces if interface.link is not None
            }

            for link in links.values():
                stack.enter_context(link.lock)
                link.remove_metadata(key)
            self.notify_topology_update()
            for link in links.values():
                self.notify_link_status_change(
                    link, reason="liveness_disabled"
                )

    @listen_to("kytos/core.interface_tags")
    def on_interface_tags(self, event):
        """Handle on_interface_tags."""
        interface: Interface = event.content['interface']
        with interface.tag_lock:
            if (
                interface.id in self._intfs_tags_updated_at
                and self._intfs_tags_updated_at[interface.id] > event.timestamp
            ):
                return
            self._intfs_tags_updated_at[interface.id] = event.timestamp
            self.handle_on_interface_tags(interface)

    def handle_on_interface_tags(
        self,
        interface: Interface
    ):
        """Update interface details"""
        intf_id = interface.id
        self.topo_controller.upsert_interface_details(
            intf_id,
            interface.available_tags,
            interface.tag_ranges,
            interface.default_tag_ranges,
            interface.special_available_tags,
            interface.special_tags,
            interface.default_special_tags,
            interface.supported_tag_types,
        )

    @listen_to("kytos/core.link_tags")
    def on_link_tags(self, event):
        """Handle on_link_tags."""
        link = event.content["link"]
        with link.tag_lock:
            if (
                link.id in self._link_tags_updated_at
                and self._link_tags_updated_at[link.id] > event.timestamp
            ):
                self._link_tags_updated_at[link.id] = event.timestamp
                self.handle_on_link_tags(link)

    def handle_on_link_tags(
        self,
        link: Link
    ):
        """Update link details"""
        link_id = link.id
        self.topo_controller.upsert_link_details(
            link_id,
            link.available_tags,
            link.tag_ranges,
            link.default_tag_ranges,
            link.special_available_tags,
            link.special_tags,
            link.default_special_tags,
            link.supported_tag_types,
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
        switch: Switch = event.content['switch']
        with switch.lock:
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
        with switch.lock:
            # NOTE: Has potential to bring back switch from dead
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
        interface: Interface = event.content['interface']
        switch = interface.switch
        with switch.lock:
            if not interface.is_active():
                self.handle_interface_link_down(interface, event)
            else:
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
        switch = interface.switch
        with switch.lock:
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
        interface: Interface = event.content['interface']
        usage = self.get_intf_usage(interface)
        if usage:
            log.info(f"Interface {interface.id} could not be safely removed."
                     f" Reason: {usage}")
            return
        with interface.switch.lock:
            self._delete_interface(interface)

    def get_intf_usage(self, interface: Interface) -> Optional[str]:
        """Determines how an interface is used explained in a string,
        returns None if unused."""
        if interface.is_enabled() or interface.is_active():
            return "It is enabled or active."

        link = interface.link
        if link:
            return f"It has a link, {link.id}."

        flow_id = self.get_flow_id_by_intf(interface)
        if flow_id:
            return f"There is a flow installed, {flow_id}."

        return None

    def get_flow_id_by_intf(self, interface: Interface) -> str:
        """Return flow_id from first found flow used by interface."""
        flows = self.get_flows_by_switch(interface.switch.id)
        port_n = int(interface.id.split(":")[-1])
        for flow in flows:
            in_port = flow["flow"].get("match", {}).get("in_port")
            if in_port == port_n:
                return flow["flow_id"]

            instructions = flow["flow"].get("instructions", [])
            for instruction in instructions:
                if instruction["instruction_type"] == "apply_actions":
                    actions = instruction["actions"]
                    for action in actions:
                        if (action["action_type"] == "output"
                                and action.get("port") == port_n):
                            return flow["flow_id"]

            actions = flow["flow"].get("actions", [])
            for action in actions:
                if (action["action_type"] == "output"
                        and action.get("port") == port_n):
                    return flow["flow_id"]
        return None

    def _delete_interface(self, interface: Interface):
        """Delete any trace of an interface. Only use this method when
         it was confirmed that the interface is not used."""
        switch: Switch = interface.switch
        switch.remove_interface(interface)
        self.topo_controller.delete_interface(interface.id)
        self.topo_controller.delete_interface_from_details(interface.id)

    @listen_to('.*.switch.interface.link_up')
    def on_interface_link_up(self, event):
        """Update the topology based on a Port Modify event.

        The event notifies that an interface's link was changed to 'up'.
        """
        interface: Interface = event.content['interface']
        switch = interface.switch
        with switch.lock:
            self.handle_interface_link_up(interface, event)

    def handle_interface_link_up(self, interface, event):
        """Update the topology based on a Port Modify event."""
        if (
            interface.id in self._intfs_updated_at
            and self._intfs_updated_at[interface.id] > event.timestamp
        ):
            return
        self._intfs_updated_at[interface.id] = event.timestamp
        self.handle_link_up(interface)

    @tenacity.retry(
        stop=stop_after_attempt(3),
        wait=wait_combine(wait_fixed(3), wait_random(min=2, max=7)),
        before_sleep=before_sleep,
        retry=retry_if_exception_type(httpx.RequestError),
    )
    def get_flows_by_switch(self, dpid: str) -> list:
        """Get installed flows by switch from flow_manager."""
        endpoint = settings.FLOW_MANAGER_URL +\
            f'/stored_flows?state=installed&dpid={dpid}'
        res = httpx.get(endpoint)
        if res.is_server_error or res.status_code in (404, 400):
            raise httpx.RequestError(res.text)
        return res.json().get(dpid, [])

    def link_status_hook_link_up_timer(
        self,
        link: Link
    ) -> Optional[EntityStatus]:
        """Link status hook link up timer."""
        tnow = time.time()
        if link.id not in self.link_status_change:
            return None
        link_status_info = self.link_status_change[link.id]
        tdelta = tnow - link_status_info['last_status_change']
        if tdelta < self.link_up_timer:
            return EntityStatus.DOWN
        return None

    @staticmethod
    def detect_mismatched_link(link: Link) -> frozenset[str]:
        """Check if a link is mismatched."""
        if (link.endpoint_a.link and link.endpoint_b
                and link.endpoint_a.link == link.endpoint_b.link):
            return frozenset()
        return frozenset(["mismatched_link"])

    def link_status_mismatched(self, link: Link) -> Optional[EntityStatus]:
        """Check if a link is mismatched and return a status."""
        if self.detect_mismatched_link(link):
            return EntityStatus.DOWN
        return None

    def notify_link_up_if_status(self, link: Link, reason="link up") -> None:
        """Tries to notify link up and topology changes based on its status

        Currently, it needs to wait up to a timer."""
        time.sleep(self.link_up_timer)
        if link.status != EntityStatus.UP:
            return
        with link.lock:
            status_change_info = self.link_status_change[link.id]
            notified_at = status_change_info.get("notified_up_at")
            if (
                notified_at
                and (now() - notified_at.replace(tzinfo=timezone.utc)).seconds
                < self.link_up_timer
            ):
                return
            status_change_info["notified_up_at"] = now()
            self.notify_topology_update()
            self.notify_link_status_change(link, reason)

    def handle_link_up(self, interface: Interface):
        """Handle link up for an interface."""
        with ExitStack() as stack:
            stack.enter_context(self.controller.switches_lock)
            link = interface.link
            if not link:
                self.notify_topology_update()
                return
            stack.enter_context(link.lock)
            interfaces = {
                iface.id: iface
                for iface in (link.endpoint_a, link.endpoint_b)
            }
            switches = {
                iface.switch.id: iface.switch
                for iface in interfaces.values()
            }
            for switch in switches.values():
                stack.enter_context(switch.lock)
            if (
                link.id not in self.link_status_change or
                not link.is_active()
            ):
                status_change_info = self.link_status_change[link.id]
                status_change_info['last_status_change'] = time.time()
                link.activate()
            self.notify_topology_update()
            link_dependencies: list[GenericEntity] = [
                *switches.values(),
                *interfaces.values(),
            ]
            for dependency in link_dependencies:
                if not dependency.is_active():
                    log.info(
                        f"{link} dependency {dependency} was not active yet."
                    )
                    return
            event = KytosEvent(
                name="kytos/topology.notify_link_up_if_status",
                content={"reason": "link up", "link": link}
            )
            self.controller.buffers.app.put(event)

    @listen_to('.*.switch.interface.link_down')
    def on_interface_link_down(self, event: KytosEvent):
        """Update the topology based on a Port Modify event.

        The event notifies that an interface's link was changed to 'down'.
        """
        interface = event.content['interface']
        switch = interface.switch
        with switch.lock:
            self.handle_interface_link_down(interface, event)

    def handle_interface_link_down(
        self,
        interface: Interface,
        event: KytosEvent
    ):
        """Update the topology based on an interface."""
        if (
            interface.id in self._intfs_updated_at
            and self._intfs_updated_at[interface.id] > event.timestamp
        ):
            return
        self._intfs_updated_at[interface.id] = event.timestamp
        self.handle_link_down(interface)

    def handle_link_down(self, interface: Interface):
        """Notify a link is down."""
        link = interface.link
        if link:
            with link.lock:
                link.deactivate()
                self.notify_link_status_change(link, reason="link down")
        self.notify_topology_update()

    @listen_to('.*.interface.is.nni')
    def on_add_links(self, event):
        """Update the topology with links related to the NNI interfaces."""
        self.add_links(event)

    def add_links(self, event):
        """Update the topology with links related to the NNI interfaces."""
        interface_a: Interface = event.content['interface_a']
        interface_b: Interface = event.content['interface_b']

        with ExitStack() as stack:
            stack.enter_context(self.controller.switches_lock)
            # TODO: Maybe setup acquiring the interface/switch locks before creating the link
            try:
                link, created = self.controller.get_link_or_create(
                    interface_a,
                    interface_b
                )
            except KytosLinkCreationError as err:
                log.error(f'Error creating link: {err}.')
                return
            # NOTE: Other things could have acquired
            # the lock between link creation and now.
            stack.enter_context(link.lock)
            stack.enter_context(link.tag_lock)

            if not created:
                return
            self.notify_topology_update()

            endpoints: dict[str, Interface] = {
                interface.id: interface
                for interface in (
                    interface_a,
                    interface_b
                )
            }

            # TODO: Are we sure we don't need to udpate the switches?
            # switches = {
            #     endpoint.switch.id: endpoint.switch
            #     for endpoint in endpoints.values()
            # }

            endpoints_list = list(endpoints.values())

            endpoints_head = endpoints_list[0]
            endpoints_tail = endpoints_list[1:]

            stack.enter_context(endpoints_head.tag_lock)

            supported_tag_types = endpoints_head.supported_tag_types
            shared_tag_ranges = deepcopy(
                endpoints_head.available_tags
            )
            shared_special_tags = deepcopy(
                endpoints_head.special_available_tags
            )

            for endpoint in endpoints_tail:
                stack.enter_context(endpoint.tag_lock)
                supported_tag_types = supported_tag_types & endpoint.supported_tag_types
                for tag_type in supported_tag_types:
                    shared_tag_ranges[tag_type] = range_intersection(
                        shared_tag_ranges[tag_type],
                        endpoint.available_tags[tag_type]
                    )
                    shared_special_tags[tag_type] = list(
                        set(shared_special_tags[tag_type]) &
                        set(endpoint.special_available_tags[tag_type])
                    )

            for tag_type in shared_tag_ranges.keys() - supported_tag_types:
                del shared_tag_ranges[tag_type]
                del shared_special_tags[tag_type]

            for endpoint in endpoints_list:
                for tag_type in supported_tag_types:
                    remove_tag_ranges = shared_tag_ranges[tag_type]
                    remove_special_tags = shared_special_tags[tag_type]

                    new_default_tag_ranges = range_difference(
                        endpoint.default_tag_ranges[tag_type],
                        remove_tag_ranges
                    )
                    new_default_special_tags = list(
                        set(endpoint.default_special_tags[tag_type]) -
                        set(remove_special_tags)
                    )
                    endpoint.set_default_tag_ranges(
                        tag_type,
                        new_default_tag_ranges
                    )
                    endpoint.set_default_special_tags(
                        tag_type,
                        new_default_special_tags
                    )
                self.handle_on_interface_tags(endpoint)

            # for switch_id, switch in switches.items():
            #     self.topo_controller.upsert_switch(
            #         switch_id, switch.as_dict()
            #     )

            link.set_available_tags_tag_ranges(
                shared_tag_ranges,
                shared_tag_ranges,
                shared_tag_ranges,
                shared_special_tags,
                shared_special_tags,
                shared_special_tags,
                supported_tag_types,
            )
            self.handle_on_link_tags(link)

            if link.is_active() and link.id not in self.link_status_change:
                status_change_info = self.link_status_change[link.id]
                status_change_info['last_status_change'] = time.time()
            self.topo_controller.upsert_link(link.id, link.as_dict())
        self.notify_link_up_if_status(link, "link up")

    @listen_to(
        '.*.of_lldp.network_status.updated',
        pool="dynamic_single"
    )
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
        ports_by_switch = defaultdict(set)
        for interface_id in interface_ids:
            dpid, _, port = interface_id.rpartition(":")
            port = int(port)
            ports_by_switch[dpid].add(port)

        for dpid, ports in ports_by_switch.items():
            # Ideally this would be done using the same lock
            # as that used by of_lldp
            switch = self.controller.get_switch_by_dpid(dpid)
            enabled_interfaces = [
                port
                for port in ports
                if switch.interfaces[port].lldp
            ]
            disabled_interfaces = [
                port
                for port in ports
                if not switch.interfaces[port].lldp
            ]
            self.topo_controller.enable_interfaces_lldp(
                dpid,
                enabled_interfaces
            )
            self.topo_controller.disable_interfaces_lldp(
                dpid,
                disabled_interfaces
            )

    def notify_switch_enabled(self, dpid):
        """Send an event to notify that a switch is enabled."""
        name = 'kytos/topology.switch.enabled'
        event = KytosEvent(name=name, content={'dpid': dpid})
        self.controller.buffers.app.put(event)

    def notify_switch_links_status(self, switch: Switch, reason):
        """Send an event to notify the status of a link in a switch"""
        with ExitStack() as stack:
            stack.enter_context(self.controller.switches_lock)
            stack.enter_context(switch.lock)
            for interface in switch.interfaces.values():
                link = interface.link
                if link is None:
                    continue
                with link.lock:
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
        next_topology = self._get_topology()
        event = KytosEvent(
            name=name, content={'topology': self._get_topology()}
        )
        self.controller.buffers.app.put(event)
        self.last_pushed_topology = next_topology

    def _notify_interface_link_status(
        self,
        links: Iterable[Link],
        reason
    ):
        """Send an event to notify the status of a link from interfaces."""
        for link in links:
            if reason == "link enabled":
                name = 'kytos/topology.notify_link_up_if_status'
                content = {'reason': reason, "link": link}
                event = KytosEvent(name=name, content=content)
                self.controller.buffers.app.put(event)
            else:
                self.notify_link_status_change(link, reason)

    def notify_link_status_change(self, link: Link, reason='not given'):
        """Send an event to notify (up/down) from a status change on
         a link."""
        link_id = link.id
        with self.link_status_lock:
            if (
                (not link.status_reason and link.status == EntityStatus.UP)
                and link_id not in self.link_up
            ):
                log.info(f"{link} changed status {link.status}, "
                         f"reason: {reason}")
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
                log.info(f"{link} changed status {link.status}, "
                         f"reason: {reason}")
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

    def notify_interface_status(
        self,
        interface: Interface,
        status: str,
        reason: str
    ):
        """Send an event to notify if an interface is enabled/disabled."""
        name = f'kytos/topology.interface.{status}'
        event = KytosEvent(
            name=name, content={'interface': interface, 'reason': reason}
        )
        self.controller.buffers.app.put(event)

    @staticmethod
    def _load_details(
        tag_capable_dict: dict[str, TAGCapable],
        tag_details_list: list[dict]
    ):
        for tag_details in tag_details_list:
            object_id = tag_details["id"]
            tag_capable = tag_capable_dict[object_id]
            with tag_capable.tag_lock:
                tag_capable.set_available_tags_tag_ranges(
                    tag_details["available_tags"],
                    tag_details["tag_ranges"],
                    tag_details["default_tag_ranges"],
                    tag_details["special_available_tags"],
                    tag_details["special_tags"],
                    tag_details["default_special_tags"],
                    frozenset(tag_details["supported_tag_types"]),
                )

    @listen_to(
        'topology.interruption.(start|end)',
        pool="dynamic_single"
    )
    def on_interruption(self, event: KytosEvent):
        """Deals with service interruptions."""
        _, _, interrupt_type = event.name.rpartition(".")
        if interrupt_type == "start":
            self.handle_interruption_start(event)
        elif interrupt_type == "end":
            self.handle_interruption_end(event)

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
        for interface_id in interfaces:
            interface = self.controller.get_interface_by_id(interface_id)
            if interface:
                self.notify_interface_status(interface, 'down', interrupt_type)
        for link_id in links:
            link = self.controller.get_link(link_id)
            if link is None:
                log.error(
                    "Invalid link id '%s' for interruption of type '%s;",
                    link_id,
                    interrupt_type
                )
            else:
                with link.lock:
                    self.notify_link_status_change(link, interrupt_type)
        self.notify_topology_update()

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
        for interface_id in interfaces:
            interface = self.controller.get_interface_by_id(interface_id)
            if interface:
                self.notify_interface_status(interface, 'up', interrupt_type)
        for link_id in links:
            link = self.controller.get_link(link_id)
            if link is None:
                log.error(
                    "Invalid link id '%s' for interruption of type '%s;",
                    link_id,
                    interrupt_type
                )
            else:
                with link.lock:
                    self.notify_link_status_change(link, interrupt_type)
        self.notify_topology_update()

    def get_latest_topology(self):
        """Get the latest topology."""
        with self.controller.switches_lock:
            return self.last_pushed_topology
