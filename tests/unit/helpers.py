"""Module to help to create tests."""
from unittest.mock import Mock

from kytos.core import Controller
from kytos.core.config import KytosConfig


def get_controller_mock():
    """Return a controller mock."""
    options = KytosConfig().options['daemon']
    controller = Controller(options)
    controller.log = Mock()
    return controller


def get_napp_urls(napp):
    """Return the kytos/topology urls.

    The urls will be like:

    urls = [
        (options, methods, url)
    ]

    """
    controller = napp.controller
    controller.api_server.register_napp_endpoints(napp)

    urls = []
    for rule in controller.api_server.app.url_map.iter_rules():
        options = {}
        for arg in rule.arguments:
            options[arg] = f"[{arg}]"

        if f'{napp.username}/{napp.name}' in str(rule):
            urls.append((options, rule.methods, f'{str(rule)}'))

    return urls
