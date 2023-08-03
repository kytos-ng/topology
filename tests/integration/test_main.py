"""Module to test the main napp file."""
from unittest.mock import Mock, patch, MagicMock

# pylint: disable=import-error,no-name-in-module
from kytos.core.events import KytosEvent
from kytos.core.buffers import KytosBuffers
from kytos.lib.helpers import get_controller_mock, get_test_client
from tests.integration.helpers import (get_interface_mock, get_switch_mock)


# pylint: disable=import-outside-toplevel
class TestMain:
    """Test the Main class."""

    def setup_method(self):
        """Execute steps before each tests.

        Set the server_name_url from kytos/topology
        """
        patch('kytos.core.helpers.run_on_thread', lambda x: x).start()
        from napps.kytos.topology.main import Main
        Main.get_topo_controller = MagicMock()
        controller = get_controller_mock()
        self.napp = Main(controller)
        _ = self.napp.controller.buffers.app.get()
        self.api_client = get_test_client(controller, self.napp)
        self.base_endpoint = "kytos/topology/v3"

    def test_get_switches_dict(self):
        """Basic test for switch listing."""
        # pylint: disable=protected-access,
        # pylint: disable=use-implicit-booleaness-not-comparison
        switches = self.napp._get_switches_dict()
        assert isinstance(switches['switches'], dict)
        assert switches['switches'] == {}

    def test_get_event_listeners(self):
        """Verify all event listeners registered."""
        actual_events = self.napp.listeners()
        expected_events = [
            'kytos/core.shutdown',
            'kytos/core.shutdown.kytos/topology',
            'kytos/.*.link_available_tags',
            'kytos/.*.liveness.(up|down)',
            'kytos/.*.liveness.disabled',
            '.*.topo_controller.upsert_switch',
            '.*.of_lldp.network_status.updated',
            '.*.interface.is.nni',
            '.*.connection.lost',
            '.*.switch.interfaces.created',
            '.*.topology.switch.interface.created',
            '.*.switch.interface.deleted',
            '.*.switch.interface.link_down',
            '.*.switch.interface.link_up',
            '.*.switch.(new|reconnected)',
            '.*.switch.port.created',
            'kytos/topology.notify_link_up_if_status',
            'topology.interruption.start',
            'topology.interruption.end',
            'topology.interruption.*',
        ]
        assert sorted(expected_events) == sorted(actual_events)

    async def test_get_interfaces(self):
        """test_get_interfaces."""
        dpid = "00:00:00:00:00:00:00:01"
        switch = get_switch_mock(0x04, dpid=dpid)
        switch.dpid = dpid
        switch.metadata = {"lat": 0, "lng": 0}
        switch.interfaces = {f"{dpid}:1": f"{dpid}:1"}
        switch.as_dict = lambda: {"dpid": dpid, "metadata": switch.metadata,
                                  "interfaces": switch.interfaces}
        self.napp.controller.switches = {dpid: switch}
        endpoint = f"{self.base_endpoint}/interfaces"
        response = await self.api_client.get(endpoint)
        assert response.status_code == 200
        data = response.json()
        assert "interfaces" in data
        assert len(data["interfaces"]) == 1
        assert data["interfaces"][f"{dpid}:1"]

    async def test_handle_new_switch(self):
        """Test handle new switch."""
        self.napp.controller._buffers = KytosBuffers()
        event_name = '.*.switch.(new|reconnected)'
        switch = get_switch_mock(0x04)
        event = KytosEvent(name=event_name,
                           content={'switch': switch})
        self.napp.handle_new_switch(event)
        event_response = self.napp.controller.buffers.app.get()
        assert event_response.name == 'kytos/topology.updated'

    async def test_handle_interface_deleted(self):
        """Test handle interface deleted."""
        self.napp.controller._buffers = KytosBuffers()
        event_name = '.*.switch.interface.deleted'
        interface = get_interface_mock("interface1", 7)
        interface.switch.dpid = "00:00:00:00:00:00:00:01"
        stats_event = KytosEvent(name=event_name,
                                 content={'interface': interface})
        self.napp.handle_interface_deleted(stats_event)
        event_updated_response = self.napp.controller.buffers.app.get()
        assert event_updated_response.name == 'kytos/topology.updated'

    async def test_handle_connection_lost(self):
        """Test handle connection lost."""
        self.napp.controller._buffers = KytosBuffers()
        event_name = '.*.connection.lost'
        source = Mock()
        stats_event = KytosEvent(name=event_name,
                                 content={'source': source})
        self.napp.handle_connection_lost(stats_event)
        event_updated_response = self.napp.controller.buffers.app.get()
        assert event_updated_response.name == 'kytos/topology.updated'
