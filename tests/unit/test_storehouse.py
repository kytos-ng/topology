"""Module to test the storehouse client."""
from unittest import TestCase
from unittest.mock import MagicMock, PropertyMock, patch

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
        # pylint: disable=import-outside-toplevel
        from napps.kytos.topology.storehouse import StoreHouse
        self.addCleanup(patch.stopall)

        self.napp = StoreHouse(get_controller_mock())

    @patch('time.sleep', return_value=None)
    @patch('napps.kytos.topology.storehouse.settings')
    @patch('napps.kytos.topology.storehouse.StoreHouse.get_stored_box')
    def test_get_data(self, mock_get_stored_box, mock_settings, mock_sleep):
        """Test get_data."""
        mock_box = MagicMock()
        box_data = MagicMock()
        mock_get_stored_box.return_value = True
        type(box_data).data = PropertyMock(side_effect=[{}, "box"])
        type(mock_box).data = PropertyMock(return_value=box_data)
        self.napp.box = mock_box
        response = self.napp.get_data()
        self.assertEqual(response.data, {})

        response = self.napp.get_data()
        self.assertEqual(response.data, "box")

        # test timeout
        mock_settings.STOREHOUSE_TIMEOUT = 2
        mock_settings.STOREHOUSE_WAIT_INTERVAL = 0.5
        self.napp.box = None
        with self.assertRaises(FileNotFoundError):
            self.napp.get_data()
        self.assertEqual(mock_sleep.call_count, 4)

    @patch('napps.kytos.topology.storehouse.KytosEvent')
    @patch('kytos.core.buffers.KytosEventBuffer.put')
    def test_create_box(self, *args):
        """Test create_box."""
        (mock_buffers_put, mock_event) = args
        self.napp.create_box()
        mock_event.assert_called()
        mock_buffers_put.assert_called()

    # pylint: disable = protected-access
    @patch('napps.kytos.topology.storehouse.log')
    def test_create_box_callback(self, mock_log):
        """Test _create_box_callback."""
        mock_data = MagicMock()
        self.napp._create_box_callback('event', mock_data, None)
        mock_log.error.assert_not_called()
        self.napp._create_box_callback('event', mock_data, 'error')
        mock_log.error.assert_called()

    # pylint: disable = protected-access
    @patch('napps.kytos.topology.storehouse.StoreHouse.get_stored_box')
    @patch('napps.kytos.topology.storehouse.StoreHouse.create_box')
    def test_get_or_create_a_box_from_list_of_boxes(self, *args):
        """Test create_box."""
        (mock_create_box, mock_get_stored_box) = args
        mock_event = MagicMock()
        mock_data = MagicMock()
        mock_error = MagicMock()
        self.napp._get_or_create_a_box_from_list_of_boxes(mock_event,
                                                          mock_data,
                                                          mock_error)
        mock_get_stored_box.assert_called()
        self.napp._get_or_create_a_box_from_list_of_boxes(mock_event,
                                                          None,
                                                          mock_error)
        mock_create_box.assert_called()

    @patch('napps.kytos.topology.storehouse.KytosEvent')
    @patch('kytos.core.buffers.KytosEventBuffer.put')
    def test_get_stored_box(self, *args):
        """Test get_stored_box."""
        (mock_buffers_put, mock_event) = args
        mock_box = MagicMock()
        self.napp.get_stored_box(mock_box)
        mock_event.assert_called()
        mock_buffers_put.assert_called()

    # pylint: disable = protected-access
    @patch('napps.kytos.topology.storehouse.log')
    def test_get_box_callback(self, mock_log):
        """Test _get_box_callback."""
        mock_data = MagicMock()
        self.napp._get_box_callback('event', mock_data, None)
        mock_log.error.assert_not_called()
        self.napp._get_box_callback('event', mock_data, 'error')
        mock_log.error.assert_called()

    @patch('time.sleep', return_value=None)
    @patch('napps.kytos.topology.storehouse.log')
    @patch('kytos.core.buffers.KytosEventBuffer.put')
    def test_save_status(self, *args):
        """Test save_status."""
        (mock_buffers_put, mock_log, mock_sleep) = args
        mock_status = MagicMock()
        self.napp.box = MagicMock()

        # case 1: successfull return
        def buffers_put_side_effect_1(event):
            event.content['callback']('event', 'data', None)
        mock_buffers_put.side_effect = buffers_put_side_effect_1
        self.napp.save_status(mock_status)
        mock_buffers_put.assert_called()
        mock_sleep.assert_not_called()
        mock_log.info.assert_called()

        # case 2: error from storehouse
        def buffers_put_side_effect_2(event):
            event.content['callback']('event', 'data', 'error')
        mock_buffers_put.side_effect = buffers_put_side_effect_2
        self.napp.save_status(mock_status)
        mock_buffers_put.assert_called()
        mock_sleep.assert_not_called()
        mock_log.error.assert_called()

        # case 3: timeout
        mock_log.error.call_count = 0
        mock_buffers_put.side_effect = [None]
        self.napp.save_status(mock_status)
        mock_buffers_put.assert_called()
        mock_sleep.assert_called()
        mock_log.error.assert_called()
