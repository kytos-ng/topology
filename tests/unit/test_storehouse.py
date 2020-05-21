"""Module to test the storehouse client."""
from unittest import TestCase
from unittest.mock import MagicMock, patch

from tests.unit.helpers import get_controller_mock


# pylint: disable=too-many-public-methods
class TestStoreHouse(TestCase):
    """Test the Main class."""
    # pylint: disable=too-many-public-methods

    def setUp(self):
        """Execute steps before each tests.

        Set the server_name_url_url from kytos/topology
        """
        self.server_name_url = 'http://localhost:8181/api/kytos/topology'

        patch('kytos.core.helpers.run_on_thread', lambda x: x).start()
        from napps.kytos.topology.storehouse import StoreHouse
        self.addCleanup(patch.stopall)

        self.napp = StoreHouse(get_controller_mock())

    @patch('napps.kytos.topology.storehouse.StoreHouse.get_stored_box')
    def test_get_data(self, mock_get_stored_box):
        """Test get_data."""
        mock_box = MagicMock()
        response = self.napp.get_data()
        self.assertEqual(response, {})

        self.napp.box = mock_box
        self.napp.get_data()
        mock_get_stored_box.assert_called()

    @patch('napps.kytos.topology.storehouse.KytosEvent')
    @patch('kytos.core.buffers.KytosEventBuffer.put')
    def test_create_box(self, *args):
        """Test create_box."""
        (mock_buffers_put, mock_event) = args
        self.napp.create_box()
        mock_event.assert_called()
        mock_buffers_put.assert_called()

    @patch('napps.kytos.topology.storehouse.KytosEvent')
    @patch('kytos.core.buffers.KytosEventBuffer.put')
    def test_get_stored_box(self, *args):
        """Test get_stored_box."""
        (mock_buffers_put, mock_event) = args
        mock_box = MagicMock()
        self.napp.get_stored_box(mock_box)
        mock_event.assert_called()
        mock_buffers_put.assert_called()

    @patch('napps.kytos.topology.storehouse.KytosEvent')
    @patch('kytos.core.buffers.KytosEventBuffer.put')
    def test_save_status(self, *args):
        """Test save_status."""
        (mock_buffers_put, mock_event) = args
        mock_status = MagicMock()
        self.napp.save_status(mock_status)
        mock_event.assert_called()
        mock_buffers_put.assert_called()
