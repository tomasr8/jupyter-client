# sharing/__init__.py
from .sharing import default_handlers, CS3_SERVICE_KEY
from ..fileio import CS3FileManagerMixin
from jupyter_server.utils import url_path_join


def _load_jupyter_server_extension(serverapp):
    # Called when the extension loads; attach handlers here.
    cs3_service = CS3FileManagerMixin(config=serverapp.config, log=serverapp.log)
    setup_handlers(serverapp.web_app, cs3_service)
    serverapp.log.info("sharing extension loaded")


def setup_handlers(web_app, cs3_service: CS3FileManagerMixin):
    web_app.settings[CS3_SERVICE_KEY] = cs3_service

    base_url = web_app.settings["base_url"]
    host_pattern = ".*$"

    handlers = []
    for url, class_ in default_handlers:
        handlers.append((url_path_join(base_url, url), class_))

    web_app.add_handlers(host_pattern, handlers)
