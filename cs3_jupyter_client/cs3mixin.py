from __future__ import annotations


import os
import inspect
from traitlets import Bool, Int, Unicode
from traitlets.config.configurable import LoggingConfigurable
from .cs3fs.cs3fs import create_cs3_filesystem
from configparser import ConfigParser
from functools import wraps

class CS3Mixin(LoggingConfigurable):
    """
    Base mixin providing CS3 filesystem access for all file operation classes.
    """
    def __init__(self, **kwargs):
        # Pre-initialize private attrs before super().__init__() so that trait
        # validators (e.g. _validate_preferred_dir → root_dir → get_user_path)
        # don't raise AttributeError and trigger __getattr__ recursion.
        self.__dict__.setdefault('_user_path', '')
        self.__dict__.setdefault('_cs3_fs', None)
        self.__dict__.setdefault('_config', None)
        super().__init__(**kwargs)
        self._read_token_file()
        # Overwrite with the actual values now that traits are initialised.
        self._user_path = f'{self.root_path}'
        self._config = self._create_cs3_config()
        self.log.debug(f"CS3Mixin initialized with path: {self._user_path}")

    host = Unicode(
        config=True,
        help="CS3 host address"
    )

    tus_enabled = Bool(
        default_value=False,
        config=True,
        help="Enable TUS protocol"
    )

    ssl_enabled = Bool(
        default_value=False,
        config=True,
        help="Enable SSL connection"
    )

    token_path = Unicode(
        default_value="/tmp/cernbox_oauth.token",
        config=True,
        help="Path to OAuth token file"
    )

    root_path = Unicode(
        default_value="",
        config=True,
        help="CS3 root path for the user"
    )

    auth_login_type = Unicode(
        default_value="bearer",
        config=True,
        help="Authentication login type"
    )

    authtokenvalidity = Int(
        default_value=3600,
        config=True,
        help="Authentication token validity in seconds"
    )

    lock_not_impl = Bool(
        default_value=False,
        config=True,
        help="Lock not implemented flag"
    )

    lock_as_attr = Bool(
        default_value=False,
        config=True,
        help="Lock as attribute flag"
    )

    cs3_token = Unicode(
        default_value="",
        config=True,
        help="CS3 authentication token"
    )

    client_id = Unicode(
        default_value="",
        config=True,
        help="CS3 client ID (can be set in config)"
    )

    def get_user_path(self):
        """Get the user path for CS3 operations."""
        return self._user_path

    def _read_token_file(self):
        """Read token from file and set cs3_token."""
        try:
            if os.path.exists(self.token_path):
                with open(self.token_path, 'r') as f:
                    self.cs3_token = f.read().strip()
            else:
                self.log.warning(f"Token file not found: {self.token_path}")
        except Exception as e:
            self.log.error(f"Failed to read token file {self.token_path}: {e}")

    def _create_cs3_config(self):
        """Create CS3 config object from trait values."""

        cs3config = ConfigParser()
        cs3config.add_section('cs3client')
        cs3config.set('cs3client', 'host', self.host)
        cs3config.set('cs3client', 'tus_enabled', str(self.tus_enabled).lower())
        cs3config.set('cs3client', 'ssl_enabled', str(self.ssl_enabled).lower())
        cs3config.set('cs3client', 'token_path', self.token_path)
        cs3config.set('cs3client', 'auth_login_type', self.auth_login_type)
        cs3config.set('cs3client', 'authtokenvalidity', str(self.authtokenvalidity))
        cs3config.set('cs3client', 'lock_not_impl', str(self.lock_not_impl).lower())
        cs3config.set('cs3client', 'lock_as_attr', str(self.lock_as_attr).lower())

        return cs3config

    def _get_cs3_fs_indep(self):
        """
        Get CS3 filesystem instance independent of the mixin,
        creates a new client each time, this was tested to be more
        performant than reusing the same client.
        """
        return create_cs3_filesystem(
            self._config,
            self.root_path,
            client_secret=self.cs3_token,
            client_id=self.client_id,
        )

    @property
    def cs3_fs(self):
        """CS3 filesystem instance, we create a new client on each access because this is more
        performant than trying to reuse the same client."""
        return self._get_cs3_fs_indep()

    def __getattr__(self, name: str):
        if name.startswith('_') or self.__dict__.get('_config') is None:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

        # Delegate to cs3_fs
        target = getattr(self.cs3_fs, name)

        if not callable(target):
            return target

        # Wrap sync vs async
        if inspect.iscoroutinefunction(target):
            @wraps(target)
            async def async_wrapped(*args, **kwargs):
                try:
                    return await target(*args, **kwargs)
                except PermissionError as e:
                    self.log.error(f"cs3mixin: {name.upper()} AUTH ERROR - {e}, reading token and retrying...")
                    self._read_token_file()
                    return await getattr(self.cs3_fs, name)(*args, **kwargs)
            return async_wrapped

        @wraps(target)
        def wrapped(*args, **kwargs):
            try:
                return target(*args, **kwargs)
            except PermissionError as e:
                self.log.error(f"cs3mixin: {name.upper()} AUTH ERROR - {e}, reading token and retrying...")
                self._read_token_file()
                return getattr(self.cs3_fs, name)(*args, **kwargs)
        return wrapped
