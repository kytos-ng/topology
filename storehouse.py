"""Module to handle the storehouse."""
import threading
import time

from kytos.core import log
from kytos.core.events import KytosEvent
from napps.kytos.topology import settings


class StoreHouse:
    """Class to handle storehouse."""

    @classmethod
    def __new__(cls, *args, **kwargs):
        # pylint: disable=unused-argument
        """Make this class a Singleton."""
        instance = cls.__dict__.get("__instance__")
        if instance is not None:
            return instance
        cls.__instance__ = instance = object.__new__(cls)
        return instance

    def __init__(self, controller):
        """Create a storehouse client instance."""
        self.controller = controller
        self.namespace = 'kytos.topology.status'
        if '_lock' not in self.__dict__:
            self._lock = threading.Lock()
        if 'box' not in self.__dict__:
            self.box = None
        self.storehouse_done = False
        self.storehouse_error = None
        self.list_stored_boxes()

    def get_data(self):
        """Return the persistence box data."""
        # Wait for box retrieve from storehouse
        i = 0
        while not self.box and i < settings.STOREHOUSE_TIMEOUT:
            time.sleep(settings.STOREHOUSE_WAIT_INTERVAL)
            i += settings.STOREHOUSE_WAIT_INTERVAL
        if not self.box:
            error = 'Error retrieving persistence box from storehouse.'
            raise FileNotFoundError(error)
        return self.box.data

    def create_box(self):
        """Create a persistence box to store administrative changes."""
        content = {'namespace': self.namespace,
                   'callback': self._create_box_callback,
                   'data': {}}
        event = KytosEvent(name='kytos.storehouse.create', content=content)
        self.controller.buffers.app.put(event)

    def _create_box_callback(self, _event, data, error):
        """Execute the callback to handle create_box."""
        if error:
            log.error(f'Can\'t create persistence'
                      f'box with namespace {self.namespace}')

        self.box = data

    def list_stored_boxes(self):
        """List all persistence box stored in storehouse."""
        name = 'kytos.storehouse.list'
        content = {'namespace': self.namespace,
                   'callback': self._get_or_create_a_box_from_list_of_boxes}

        event = KytosEvent(name=name, content=content)
        self.controller.buffers.app.put(event)

    def _get_or_create_a_box_from_list_of_boxes(self, _event, data, _error):
        """Create a persistence box or retrieve the stored box."""
        if data:
            self.get_stored_box(data[0])
        else:
            self.create_box()

    def get_stored_box(self, box_id):
        """Get persistence box from storehouse."""
        content = {'namespace': self.namespace,
                   'callback': self._get_box_callback,
                   'box_id': box_id,
                   'data': {}}
        name = 'kytos.storehouse.retrieve'
        event = KytosEvent(name=name, content=content)
        self.controller.buffers.app.put(event)

    def _get_box_callback(self, _event, data, error):
        """Handle get_box method saving the box or logging with the error."""
        if error:
            log.error('Persistence box not found.')

        self.box = data

    def save_status(self, status):
        """Save the network administrative status using storehouse."""
        with self._lock:
            self.storehouse_done = False
            self.storehouse_error = None
            self.box.data[status.get('id')] = status
            content = {'namespace': self.namespace,
                       'box_id': self.box.box_id,
                       'data': self.box.data,
                       'callback': self._save_status_callback}
            event = KytosEvent(name='kytos.storehouse.update',
                               content=content)
            self.controller.buffers.app.put(event)

            i = 0
            while not self.storehouse_done and i < settings.STOREHOUSE_TIMEOUT:
                time.sleep(settings.STOREHOUSE_WAIT_INTERVAL)
                i += settings.STOREHOUSE_WAIT_INTERVAL

            if not self.storehouse_done:
                self.storehouse_error = 'Timeout while waiting for storehouse'

            if self.storehouse_error:
                log.error('Fail to update persistence box in '
                          f'{self.namespace}.{self.box.box_id}. '
                          f'Error: {self.storehouse_error}')
                return

        log.info('Network administrative status saved in '
                 f'{self.namespace}.{self.box.box_id}')

    def _save_status_callback(self, _event, _data, error):
        """Handle storehouse update result."""
        self.storehouse_done = True
        self.storehouse_error = error
