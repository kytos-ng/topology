"""Module to test the main napp file."""
from unittest import TestCase
from unittest.mock import MagicMock, create_autospec, patch

from kytos.core.switch import Switch
from kytos.core.interface import Interface
from kytos.core.link import Link


from tests.unit.helpers import (get_controller_mock, get_napp_urls)


class TestMain(TestCase):
    """Test the Main class."""
    # pylint: disable=too-many-public-methods

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
                           'kytos/maintenance.start_link',
                           'kytos/maintenance.end_link',
                           'kytos/maintenance.start_switch',
                           'kytos/maintenance.end_switch',
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
        self.assertCountEqual(expected_events, actual_events)

    def test_verify_api_urls(self):
        """Verify all APIs registered."""
        expected_urls = [
         ({}, {'GET', 'OPTIONS', 'HEAD'}, '/api/kytos/topology/v3/interfaces'),
         ({}, {'GET', 'OPTIONS', 'HEAD'}, '/api/kytos/topology/v3/switches'),
         ({}, {'GET', 'OPTIONS', 'HEAD'}, '/api/kytos/topology/v3/links'),
         ({}, {'GET', 'OPTIONS', 'HEAD'}, '/api/kytos/topology/v3/'),
         ({'key': '[key]', 'interface_id': '[interface_id]'},
          {'OPTIONS', 'DELETE'},
          '/api/kytos/topology/v3/interfaces/<interface_id>/metadata/<key>'),
         ({'interface_id': '[interface_id]'}, {'POST', 'OPTIONS'},
          '/api/kytos/topology/v3/interfaces/<interface_id>/metadata'),
         ({'interface_id': '[interface_id]'}, {'GET', 'OPTIONS', 'HEAD'},
          '/api/kytos/topology/v3/interfaces/<interface_id>/metadata'),
         ({'interface_id': '[interface_id]'}, {'POST', 'OPTIONS'},
          '/api/kytos/topology/v3/interfaces/<interface_id>/disable'),
         ({'interface_id': '[interface_id]'}, {'POST', 'OPTIONS'},
          '/api/kytos/topology/v3/interfaces/<interface_id>/enable'),
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

    @patch('napps.kytos.topology.main.Main.notify_link_status_change')
    def test_handle_link_maintenance_start(self, status_change_mock):
        """Test handle_link_maintenance_start."""
        link1 = MagicMock()
        link1.id = 2
        link2 = MagicMock()
        link2.id = 3
        link3 = MagicMock()
        link3.id = 4
        content = {'links': [link1, link2]}
        event = MagicMock()
        event.content = content
        self.napp.links = {2: link1, 4: link3}
        self.napp.handle_link_maintenance_start(event)
        status_change_mock.assert_called_once_with(link1)

    @patch('napps.kytos.topology.main.Main.notify_link_status_change')
    def test_handle_link_maintenance_end(self, status_change_mock):
        """Test handle_link_maintenance_end."""
        link1 = MagicMock()
        link1.id = 2
        link2 = MagicMock()
        link2.id = 3
        link3 = MagicMock()
        link3.id = 4
        content = {'links': [link1, link2]}
        event = MagicMock()
        event.content = content
        self.napp.links = {2: link1, 4: link3}
        self.napp.handle_link_maintenance_end(event)
        status_change_mock.assert_called_once_with(link1)

    @patch('napps.kytos.topology.main.Main.handle_link_down')
    def test_handle_switch_maintenance_start(self, handle_link_down_mock):
        """Test handle_switch_maintenance_start."""
        switch1 = MagicMock()
        interface1 = MagicMock()
        interface1.is_active.return_value = True
        interface2 = MagicMock()
        interface2.is_active.return_value = False
        interface3 = MagicMock()
        interface3.is_active.return_value = True
        switch1.interfaces = {1: interface1, 2: interface2, 3: interface3}
        switch2 = MagicMock()
        interface4 = MagicMock()
        interface4.is_active.return_value = False
        interface5 = MagicMock()
        interface5.is_active.return_value = True
        switch2.interfaces = {1: interface4, 2: interface5}
        content = {'switches': [switch1, switch2]}
        event = MagicMock()
        event.content = content
        self.napp.handle_switch_maintenance_start(event)
        self.assertEqual(handle_link_down_mock.call_count, 3)

    @patch('napps.kytos.topology.main.Main.handle_link_up')
    def test_handle_switch_maintenance_end(self, handle_link_up_mock):
        """Test handle_switch_maintenance_end."""
        switch1 = MagicMock()
        interface1 = MagicMock()
        interface1.is_active.return_value = True
        interface2 = MagicMock()
        interface2.is_active.return_value = False
        interface3 = MagicMock()
        interface3.is_active.return_value = True
        switch1.interfaces = {1: interface1, 2: interface2, 3: interface3}
        switch2 = MagicMock()
        interface4 = MagicMock()
        interface4.is_active.return_value = False
        interface5 = MagicMock()
        interface5.is_active.return_value = True
        switch2.interfaces = {1: interface4, 2: interface5}
        content = {'switches': [switch1, switch2]}
        event = MagicMock()
        event.content = content
        self.napp.handle_switch_maintenance_end(event)
        self.assertEqual(handle_link_up_mock.call_count, 5)
