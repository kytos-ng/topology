"""Module to help to create tests."""


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
