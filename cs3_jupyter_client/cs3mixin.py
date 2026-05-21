from __future__ import annotations

import jwt
import os
from configparser import ConfigParser
from typing import Any

from cs3client.auth import Auth
from cs3client.cs3client import CS3Client
from traitlets import Bool, Int, Unicode
from traitlets.config.configurable import LoggingConfigurable

from .cs3vfs.statuscodehandler import StatusCodeHandler
from .cs3vfs.cs3versions import CS3FileVersions
from .cs3vfs.cs3groups import CS3Groups
from .cs3vfs.cs3sharing import CS3Sharing
from .cs3vfs.cs3spaces import CS3Spaces
from .cs3vfs.cs3users import CS3Users
from .cs3vfs.cs3vfs import CS3VirtualFileSystem

class CS3BaseMixin(CS3Groups, CS3Users, CS3Spaces, CS3Sharing, CS3FileVersions, LoggingConfigurable):
    """Owns the shared CS3Client/Auth and persistent service instances."""

    host = Unicode(config=True, help="CS3 host address")
    tus_enabled = Bool(default_value=False, config=True, help="Enable TUS protocol")
    ssl_enabled = Bool(default_value=False, config=True, help="Enable SSL connection")
    token_path = Unicode(
        default_value="/tmp/cernbox_oauth.token",
        config=True,
        help="Path to OAuth token file",
    )
    root_path = Unicode(default_value="", config=True, help="CS3 root path for the user")
    auth_login_type = Unicode(
        default_value="bearer", config=True, help="Authentication login type"
    )
    authtokenvalidity = Int(
        default_value=3600, config=True, help="Authentication token validity in seconds"
    )
    lock_not_impl = Bool(default_value=False, config=True, help="Lock not implemented flag")
    lock_as_attr = Bool(default_value=False, config=True, help="Lock as attribute flag")
    cs3_token = Unicode(default_value="", config=True, help="CS3 authentication token")
    client_id = Unicode(default_value="", config=True, help="CS3 client ID (can be set in config)")


    def __init__(self, **kwargs: Any):
        self.status_handler = StatusCodeHandler()
        super().__init__(**kwargs)
        self._read_token_file()
        self._config = self._create_cs3_config()
        self.client = CS3Client(self._config, "cs3client", self.log)
        self.auth = Auth(self.client)
        self.auth.set_client_id(self.client_id)
        self.auth.set_client_secret(self.cs3_token)

        self.log.debug(f"CS3ClientMixinBase initialized with path: {self.root_path}")

    def get_user_path(self) -> str:
        return self.root_path

    def _read_token_file(self) -> None:
        try:
            if os.path.exists(self.token_path):
                with open(self.token_path, "r") as f:
                    self.cs3_token = f.read().strip()
            else:
                self.log.warning(f"Token file not found: {self.token_path}")
        except Exception as e:
            self.log.error(f"Failed to read token file {self.token_path}: {e}")

    def _refresh_auth(self) -> None:
        """Reload token/secret from disk and update the shared Auth object."""
        self._read_token_file()
        self.auth.set_client_secret(self.cs3_token)

    def _create_cs3_config(self) -> ConfigParser:
        cs3config = ConfigParser()
        cs3config.add_section("cs3client")
        cs3config.set("cs3client", "host", self.host)
        cs3config.set("cs3client", "tus_enabled", str(self.tus_enabled).lower())
        cs3config.set("cs3client", "ssl_enabled", str(self.ssl_enabled).lower())
        cs3config.set("cs3client", "token_path", self.token_path)
        cs3config.set("cs3client", "auth_client_id", self.client_id)
        cs3config.set("cs3client", "auth_login_type", self.auth_login_type)
        cs3config.set("cs3client", "authtokenvalidity", str(self.authtokenvalidity))
        cs3config.set("cs3client", "lock_not_impl", str(self.lock_not_impl).lower())
        cs3config.set("cs3client", "lock_as_attr", str(self.lock_as_attr).lower())
        return cs3config

    def _decode_token(self) -> dict:
        _, token = self.auth.get_token()
        return jwt.decode(
            jwt=token,
            algorithms=["HS256"],
            options={"verify_signature": False},
        )

    @property
    def user_idp(self) -> str:
        return self._decode_token()["user"]["id"]["idp"]

    @property
    def user_opaque_id(self) -> str:
        return self._decode_token()["user"]["id"]["opaque_id"]

class CS3Mixin(CS3BaseMixin, CS3VirtualFileSystem):
    """CS3Mixin combines the base mixin with the virtual file system operations."""
    pass
