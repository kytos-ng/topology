"""Module to test the main napp file."""
import json
from unittest import TestCase
from unittest.mock import MagicMock, create_autospec, patch

from kytos.core.switch import Switch
from kytos.core.interface import Interface
from kytos.core.link import Link


from tests.unit.helpers import (get_controller_mock, get_napp_urls,
                                get_app_test_client)


class TestMain(TestCase):
    """Test the Main class."""

    def setUp(self):
        """Execute steps before each tests.

        Set the server_name_url_url from kytos/topology
        """
        self.server_name_url = 'http://localhost:8181/api/kytos/topology'

        patch('kytos.core.helpers.run_on_thread', lambda x: x).start()
        from napps.kytos.topology.main import Main
        self.addCleanup(patch.stopall)

        self.napp = Main(get_controller_mock())

    def test_get_event_listeners(self):
        """Verify all event listeners registered."""
        expected_events = ['kytos/core.shutdown',
                           'kytos/core.shutdown.kytos/topology',
                           '.*.interface.is.nni',
                           '.*.connection.lost',
                           '.*.switch.interface.created',
                           '.*.switch.interface.deleted',
                           '.*.switch.interface.link_down',
                           '.*.switch.interface.link_up',
                           '.*.switch.(new|reconnected)',
                           '.*.switch.port.created',
                           'kytos/topology.*.metadata.*']
        actual_events = self.napp.listeners()
        self.assertEqual(expected_events, actual_events)

    def test_verify_api_urls(self):
        """Verify all APIs registered."""
        expected_urls = [
         ({}, {'GET', 'OPTIONS', 'HEAD'}, '/api/kytos/topology/v3/interfaces'),
         ({}, {'GET', 'OPTIONS', 'HEAD'}, '/api/kytos/topology/v3/switches'),
         ({}, {'GET', 'OPTIONS', 'HEAD'}, '/api/kytos/topology/v3/links'),
         ({}, {'GET', 'OPTIONS', 'HEAD'}, '/api/kytos/topology/v3/'),
         ({'dpid': '[dpid]'}, {'POST', 'OPTIONS'},
          '/api/kytos/topology/v3/interfaces/switch/<dpid>/disable'),
         ({'dpid': '[dpid]'}, {'POST', 'OPTIONS'},
          '/api/kytos/topology/v3/interfaces/switch/<dpid>/enable'),
         ({'key': '[key]', 'interface_id': '[interface_id]'},
          {'OPTIONS', 'DELETE'},
          '/api/kytos/topology/v3/interfaces/<interface_id>/metadata/<key>'),
         ({'interface_id': '[interface_id]'}, {'POST', 'OPTIONS'},
          '/api/kytos/topology/v3/interfaces/<interface_id>/metadata'),
         ({'interface_id': '[interface_id]'}, {'GET', 'OPTIONS', 'HEAD'},
          '/api/kytos/topology/v3/interfaces/<interface_id>/metadata'),
         ({'interface_disable_id': '[interface_disable_id]'},
          {'POST', 'OPTIONS'},
          '/api/kytos/topology/v3/interfaces/<interface_disable_id>/disable'),
         ({'interface_enable_id': '[interface_enable_id]'},
          {'POST', 'OPTIONS'},
          '/api/kytos/topology/v3/interfaces/<interface_enable_id>/enable'),
         ({'dpid': '[dpid]', 'key': '[key]'}, {'OPTIONS', 'DELETE'},
          '/api/kytos/topology/v3/switches/<dpid>/metadata/<key>'),
         ({'dpid': '[dpid]'}, {'POST', 'OPTIONS'},
          '/api/kytos/topology/v3/switches/<dpid>/metadata'),
         ({'dpid': '[dpid]'}, {'GET', 'OPTIONS', 'HEAD'},
          '/api/kytos/topology/v3/switches/<dpid>/metadata'),
         ({'dpid': '[dpid]'}, {'POST', 'OPTIONS'},
          '/api/kytos/topology/v3/switches/<dpid>/disable'),
         ({'dpid': '[dpid]'}, {'POST', 'OPTIONS'},
          '/api/kytos/topology/v3/switches/<dpid>/enable'),
         ({'link_id': '[link_id]', 'key': '[key]'}, {'OPTIONS', 'DELETE'},
          '/api/kytos/topology/v3/links/<link_id>/metadata/<key>'),
         ({'link_id': '[link_id]'}, {'POST', 'OPTIONS'},
          '/api/kytos/topology/v3/links/<link_id>/metadata'),
         ({'link_id': '[link_id]'}, {'GET', 'OPTIONS', 'HEAD'},
          '/api/kytos/topology/v3/links/<link_id>/metadata'),
         ({'link_id': '[link_id]'}, {'POST', 'OPTIONS'},
          '/api/kytos/topology/v3/links/<link_id>/disable'),
         ({'link_id': '[link_id]'}, {'POST', 'OPTIONS'},
          '/api/kytos/topology/v3/links/<link_id>/enable')]

        urls = get_napp_urls(self.napp)
        self.assertEqual(expected_urls, urls)

    def test_enable_interfaces(self):
        """Test enable_interfaces."""
        mock_switch = create_autospec(Switch)
        mock_interface_1 = create_autospec(Interface)
        mock_interface_2 = create_autospec(Interface)
        mock_switch.interfaces = {1: mock_interface_1, 2: mock_interface_2}
        self.napp.controller.switches = {'00:00:00:00:00:00:00:01':
                                         mock_switch}
        api = get_app_test_client(self.napp)
        expected_success = 'Operation successful'

        interface_id = '00:00:00:00:00:00:00:01:1'
        url = f'{self.server_name_url}/v3/interfaces/{interface_id}/enable'
        response = api.post(url)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(expected_success, json.loads(response.data))
        self.assertEqual(mock_interface_1.enable.call_count, 1)
        self.assertEqual(mock_interface_2.enable.call_count, 0)

        dpid = '00:00:00:00:00:00:00:01'
        mock_interface_1.enable.call_count = 0
        mock_interface_2.enable.call_count = 0
        url = f'{self.server_name_url}/v3/interfaces/switch/{dpid}/enable'
        response = api.post(url)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(expected_success, json.loads(response.data))
        self.assertEqual(mock_interface_1.enable.call_count, 1)
        self.assertEqual(mock_interface_2.enable.call_count, 1)

        # test interface not found
        interface_id = '00:00:00:00:00:00:00:01:3'
        mock_interface_1.enable.call_count = 0
        mock_interface_2.enable.call_count = 0
        url = f'{self.server_name_url}/v3/interfaces/{interface_id}/enable'
        response = api.post(url)
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(mock_interface_1.enable.call_count, 0)
        self.assertEqual(mock_interface_2.enable.call_count, 0)

        # test switch not found
        dpid = '00:00:00:00:00:00:00:02'
        expected_fail = f"Switch not found: '{dpid}'"
        url = f'{self.server_name_url}/v3/interfaces/switch/{dpid}/enable'
        response = api.post(url)
        self.assertEqual(response.status_code, 404, response.data)
        self.assertEqual(expected_fail, json.loads(response.data))
        self.assertEqual(mock_interface_1.enable.call_count, 0)
        self.assertEqual(mock_interface_2.enable.call_count, 0)

    def test_disable_interfaces(self):
        """Test disable_interfaces."""
        interface_id = '00:00:00:00:00:00:00:01:1'
        dpid = '00:00:00:00:00:00:00:01'
        expected = 'Operation successful'
        mock_switch = create_autospec(Switch)
        mock_interface_1 = create_autospec(Interface)
        mock_interface_2 = create_autospec(Interface)
        mock_switch.interfaces = {1: mock_interface_1, 2: mock_interface_2}
        self.napp.controller.switches = {'00:00:00:00:00:00:00:01':
                                         mock_switch}
        api = get_app_test_client(self.napp)

        url = f'{self.server_name_url}/v3/interfaces/{interface_id}/disable'
        response = api.post(url)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(expected, json.loads(response.data))
        self.assertEqual(mock_interface_1.disable.call_count, 1)
        self.assertEqual(mock_interface_2.disable.call_count, 0)

        mock_interface_1.disable.call_count = 0
        mock_interface_2.disable.call_count = 0
        url = f'{self.server_name_url}/v3/interfaces/switch/{dpid}/disable'
        response = api.post(url)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(expected, json.loads(response.data))
        self.assertEqual(mock_interface_1.disable.call_count, 1)
        self.assertEqual(mock_interface_2.disable.call_count, 1)

        # test interface not found
        interface_id = '00:00:00:00:00:00:00:01:3'
        mock_interface_1.disable.call_count = 0
        mock_interface_2.disable.call_count = 0
        url = f'{self.server_name_url}/v3/interfaces/{interface_id}/disable'
        response = api.post(url)
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(mock_interface_1.disable.call_count, 0)
        self.assertEqual(mock_interface_2.disable.call_count, 0)

        # test switch not found
        dpid = '00:00:00:00:00:00:00:02'
        expected_fail = f"Switch not found: '{dpid}'"
        url = f'{self.server_name_url}/v3/interfaces/switch/{dpid}/disable'
        response = api.post(url)
        self.assertEqual(response.status_code, 404, response.data)
        self.assertEqual(expected_fail, json.loads(response.data))
        self.assertEqual(mock_interface_1.disable.call_count, 0)
        self.assertEqual(mock_interface_2.disable.call_count, 0)

    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.update_instance_metadata')
    def test_handle_new_switch(self, *args):
        """Test handle_new_switch."""
        (mock_instance_metadata, mock_notify_topology_update) = args
        mock_event = MagicMock()
        mock_switch = create_autospec(Switch)
        mock_event.content['switch'] = mock_switch
        self.napp.handle_new_switch(mock_event)
        mock_notify_topology_update.assert_called()
        mock_instance_metadata.assert_called()

    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    def test_handle_connection_lost(self, mock_notify_topology_update):
        """Test handle connection_lost."""
        mock_event = MagicMock()
        mock_switch = create_autospec(Switch)
        mock_switch.return_value = True
        mock_event.content['source'] = mock_switch
        self.napp.handle_connection_lost(mock_event)
        mock_notify_topology_update.assert_called()

    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.update_instance_metadata')
    def test_handle_interface_up(self, *args):
        """Test handle_interface_up."""
        (mock_instance_metadata, mock_notify_topology_update) = args
        mock_event = MagicMock()
        mock_interface = create_autospec(Interface)
        mock_event.content['interface'] = mock_interface
        self.napp.handle_interface_up(mock_event)
        mock_notify_topology_update.assert_called()
        mock_instance_metadata.assert_called()

    @patch('napps.kytos.topology.main.Main.handle_interface_up')
    def test_handle_interface_created(self, mock_handle_interface_up):
        """Test handle interface created."""
        mock_event = MagicMock()
        self.napp.handle_interface_created(mock_event)
        mock_handle_interface_up.assert_called()

    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.handle_interface_link_down')
    def test_handle_interface_down(self, *args):
        """Test handle interface down."""
        (mock_handle_interface_link_down, mock_notify_topology_update) = args
        mock_event = MagicMock()
        mock_interface = create_autospec(Interface)
        mock_event.content['interface'] = mock_interface
        self.napp.handle_interface_down(mock_event)
        mock_handle_interface_link_down.assert_called()
        mock_notify_topology_update.assert_called()

    @patch('napps.kytos.topology.main.Main.handle_interface_down')
    def test_interface_deleted(self, mock_handle_interface_link_down):
        """Test interface deleted."""
        mock_event = MagicMock()
        self.napp.handle_interface_deleted(mock_event)
        mock_handle_interface_link_down.assert_called()

    @patch('napps.kytos.topology.main.Main._get_link_from_interface')
    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.update_instance_metadata')
    @patch('napps.kytos.topology.main.Main.notify_link_status_change')
    def test_interface_link_up(self, *args):
        """Test interface link_up."""
        (mock_status_change, mock_instance_metadata, mock_topology_update,
         mock_link_from_interface) = args

        mock_event = MagicMock()
        mock_interface = create_autospec(Interface)
        mock_link = create_autospec(Link)
        mock_link.is_active.return_value = False
        mock_link_from_interface.return_value = mock_link
        mock_event.content['interface'] = mock_interface
        self.napp.handle_interface_link_up(mock_event)
        mock_topology_update.assert_called()
        mock_instance_metadata.assert_called()
        mock_status_change.assert_called()

    @patch('napps.kytos.topology.main.Main._get_link_from_interface')
    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    @patch('napps.kytos.topology.main.Main.notify_link_status_change')
    def test_interface_link_down(self, *args):
        """Test interface link down."""
        (mock_status_change, mock_topology_update,
         mock_link_from_interface) = args

        mock_event = MagicMock()
        mock_interface = create_autospec(Interface)
        mock_link = create_autospec(Link)
        mock_link.is_active.return_value = True
        mock_link_from_interface.return_value = mock_link
        mock_event.content['interface'] = mock_interface
        self.napp.handle_interface_link_down(mock_event)
        mock_topology_update.assert_called()
        mock_status_change.assert_called()

    @patch('napps.kytos.topology.main.Main._get_link_or_create')
    @patch('napps.kytos.topology.main.Main.notify_topology_update')
    def test_add_links(self, *args):
        """Test add_links."""
        (mock_notify_topology_update, mock_get_link_or_create) = args
        mock_event = MagicMock()
        self.napp.add_links(mock_event)
        mock_get_link_or_create.assert_called()
        mock_notify_topology_update.assert_called()

    @patch('napps.kytos.topology.main.KytosEvent')
    @patch('kytos.core.buffers.KytosEventBuffer.put')
    def test_notify_topology_update(self, *args):
        """Test notify_topology_update."""
        (mock_buffers_put, mock_event) = args
        self.napp.notify_topology_update()
        mock_event.assert_called()
        mock_buffers_put.assert_called()

    @patch('napps.kytos.topology.main.KytosEvent')
    @patch('kytos.core.buffers.KytosEventBuffer.put')
    def test_notify_link_status_change(self, *args):
        """Test notify link status change."""
        (mock_buffers_put, mock_event) = args
        mock_link = create_autospec(Link)
        self.napp.notify_link_status_change(mock_link)
        mock_event.assert_called()
        mock_buffers_put.assert_called()

    @patch('napps.kytos.topology.main.KytosEvent')
    @patch('kytos.core.buffers.KytosEventBuffer.put')
    @patch('napps.kytos.topology.main.isinstance')
    def test_notify_metadata_changes(self, *args):
        """Test notify metadata changes."""
        (mock_isinstance, mock_buffers_put, mock_event) = args
        mock_isinstance.return_value = True
        mock_obj = MagicMock()
        mock_action = create_autospec(Switch)
        self.napp.notify_metadata_changes(mock_obj, mock_action)
        mock_event.assert_called()
        mock_isinstance.assert_called()
        mock_buffers_put.assert_called()

    @patch('napps.kytos.topology.main.KytosEvent')
    @patch('kytos.core.buffers.KytosEventBuffer.put')
    def test_notify_port_created(self, *args):
        """Test notify port created."""
        (mock_buffers_put, mock_kytos_event) = args
        mock_event = MagicMock()
        self.napp.notify_port_created(mock_event)
        mock_kytos_event.assert_called()
        mock_buffers_put.assert_called()

    @patch('napps.kytos.topology.main.KytosEvent')
    @patch('kytos.core.buffers.KytosEventBuffer.put')
    def test_verify_storehouse(self, *args):
        """Test verify_storehouse."""
        (mock_buffers_put, mock_kytos_event) = args
        mock_entities = MagicMock()
        self.napp.verify_storehouse(mock_entities)
        mock_buffers_put.assert_called()
        mock_kytos_event.assert_called()
