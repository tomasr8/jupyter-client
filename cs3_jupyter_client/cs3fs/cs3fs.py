"""
CS3 Operating System Interface

This module provides a CS3-based implementation of common file system operations
to replace standard library functions like os, shutil, etc. with CS3 storage operations.

Authors: Rasmus Welander.
Emails: rasmus.oscar.welander@cern.ch.
"""

import base64
import configparser
import logging
import os
import stat
import time
from .statuscodehandler import StatusCodeHandler
from contextlib import contextmanager
from typing import Generator, List, Optional, Tuple, Union
from tornado import web


from cs3client.cs3client import CS3Client
from cs3client.user import User
from cs3client.auth import Auth
from cs3client.cs3resource import Resource
import cs3.storage.provider.v1beta1.resources_pb2 as cs3spr


class StatResult:
    def __init__(self, info) -> None:
        """Initialize StatResult from CS3 resource info."""
        # size is needed for jupyter
        self.st_size = getattr(info, 'size', 0)

        if hasattr(info, 'mtime') and info.mtime:
            self.st_mtime = float(info.mtime.seconds)
            if hasattr(info.mtime, 'nanos'):
                self.st_mtime += info.mtime.nanos / 1e9
        else:
            self.st_mtime = time.time()

        # mtime and ctime are needed for jupyter
        self.st_ctime = int(self.st_mtime)
        self.st_mtime = int(self.st_mtime)

        # type is needed for jupyter
        if hasattr(info, 'type'):
            if info.type == cs3spr.ResourceType.RESOURCE_TYPE_CONTAINER:
                self.st_mode = stat.S_IFDIR | 0o755
            elif info.type == cs3spr.ResourceType.RESOURCE_TYPE_FILE:
                self.st_mode = stat.S_IFREG | 0o644
            elif info.type == cs3spr.ResourceType.RESOURCE_TYPE_SYMLINK:
                self.st_mode = stat.S_IFLNK | 0o777
            else:
                self.st_mode = stat.S_IFREG | 0o644
        else:
            self.st_mode = stat.S_IFREG | 0o644
        # All resources do not have the permissions_set attribute, but
        # if a resource doesn't have this attribute it can't be writeable.
        if hasattr(info, 'permission_set'):
            if info.permission_set.create_container or info.permission_set.delete:
                self.writeable = True
            else:
                self.writeable = False
        else:
            self.writeable = False


class CS3FileSystem:
    """
    CS3-based file system operations that can replace standard library functions.

    This class provides implementations for file operations using CS3 storage
    instead of the local file system.
    """

    def __init__(self, cs3config: configparser.ConfigParser, root_path: str, client_secret: str = None, client_id: str = None) -> None:
        """
        Initialize CS3 file system interface.

        Args:
            config: CS3 configuration parser
            token: Existing CS3 token
        """
        self.log = logging.getLogger(__name__)
        self.status_handler = StatusCodeHandler()
        self.root_path = root_path

        if not client_secret:
            raise ValueError("Either token or client_secret must be provided for authentication")
        # Initialize CS3 client
        self.client = CS3Client(cs3config, "cs3client", self.log)
        self.auth = Auth(self.client)
        # Set the client id (can also be set in the config)
        self.auth.set_client_id(client_id)
        # Set client secret (can also be set in config)
        self.auth.set_client_secret(client_secret)
        # Seed _token with the bearer token so get_token() uses it directly
        # via check_token() without calling the Authenticate gateway endpoint.
        # The bearer token from oauth.token is already a valid CS3 access token.
        self.auth._token = client_secret

    def _resource_from_path(self, path: str) -> Resource:
        """Convert path to CS3 Resource object."""
        return Resource(abs_path=path)

    @contextmanager
    def cs3open(self, path: str, mode: str = 'r', encoding: Optional[str] = None, **kwargs) -> Generator['CS3File', None, None]:
        """Context manager for opening CS3 files."""
        cs3_file = CS3File(self, path, mode, encoding)
        cs3_file._init()
        try:
            yield cs3_file
        finally:
            cs3_file.close()

    def exists(self, path: str) -> bool:
        """Check if path exists."""
        try:
            resource = self._resource_from_path(path)
            result = self.client.file.stat(
                self.auth.get_token(),
                resource
            )
            return result is not None
        except Exception:
            return False

    def is_file(self, path: str) -> bool:
        """Check if path is a file."""
        try:
            resource = self._resource_from_path(path)
            result = self.client.file.stat(
                self.auth.get_token(),
                resource
            )
            if result is None:
                return False

            is_file = hasattr(result, 'type') and result.type == cs3spr.ResourceType.RESOURCE_TYPE_FILE
            return is_file
        except Exception:
            return False

    def is_dir(self, path: str) -> bool:
        """Check if path is a directory."""
        try:
            resource = self._resource_from_path(path)
            result = self.client.file.stat(
                self.auth.get_token(),
                resource
            )
            if result is None:
                return False
            return result.type == cs3spr.ResourceType.RESOURCE_TYPE_CONTAINER
        except Exception:
            return False

    def is_abs(self, path: str) -> bool:
        """Check if path is absolute."""
        return path.startswith(self.root_path)

    def abs_path(self, path: str) -> str:
        return path

    def list_dir(self, path: str) -> List[Tuple[str, 'StatResult']]:
        """List directory contents with stat information in one call."""
        resource = self._resource_from_path(path)
        try:
            result = self.client.file.list_dir(
                self.auth.get_token(),
                resource
            )
        except Exception as e:
            self.status_handler.handle_errors(e)
        items = []
        for item in result:
            stat_result = StatResult(item)
            # item.path should be the full path
            # but jupyter expects just the name
            # so we extract the name from the path
            name = item.path.split("/")[-1]
            items.append((name, stat_result))

        return items

    def mkdir(self, path: str) -> None:
        """Create directory."""
        try:
            resource = self._resource_from_path(path)
            self.client.file.make_dir(
                self.auth.get_token(),
                resource
            )
        except Exception as e:
            self.status_handler.handle_errors(e)

    # Alias for rmdir, because jupyter uses it
    def rmdir(self, path: str) -> None:
        """Remove directory."""
        return self.unlink(path)


    def unlink(self, path: str) -> None:
        """Remove file."""
        try:
            resource = self._resource_from_path(path)
            self.client.file.remove_file(
                self.auth.get_token(),
                resource
            )
        except Exception as e:
            self.status_handler.handle_errors(e)

    def move(self, src: str, dst: str) -> None:
        """Move file or directory."""
        self.rename(src, dst)

    def rename(self, src: str, dst: str) -> None:
        """Rename file or directory."""
        try:
            src_resource = self._resource_from_path(src)
            dst_resource = self._resource_from_path(dst)
            self.client.file.rename_file(
                self.auth.get_token(),
                src_resource,
                dst_resource
            )
        except Exception as e:
            self.status_handler.handle_errors(e)

    def lstat(self, path: str) -> 'StatResult':
        """Get file stats."""
        try:
            resource = self._resource_from_path(path)
            result = self.client.file.stat(
                self.auth.get_token(),
                resource
            )
        except Exception as e:
            self.status_handler.handle_errors(e)

        return StatResult(result)

    def get_quota(self, path: str) -> 'QuotaResponse':  # noqa: F821
        """Get resource quota."""
        try:
            resource = self._resource_from_path(path)
            result = self.client.file.get_quota(
                self.auth.get_token(),
                resource
            )
        except Exception as e:
            self.status_handler.handle_errors(e)

        return result

    def access(self, path: str, mode: int) -> bool:
        """Check file access permissions."""
        try:
            resource = self._resource_from_path(path)
            result = self.client.file.stat(
                self.auth.get_token(),
                resource
            )
            return result is not None
        except PermissionError:
            return False
        except Exception as e:
            self.status_handler.handle_errors(e)

    def read_file(self, path: str, format: Optional[str] = None, raw: bool = False) -> Union[Tuple[Union[str, bytes], str], Tuple[Union[str, bytes], str, bytes]]:
        """Read a file with CS3."""

        try:
            resource = self._resource_from_path(path)
            result = self.client.file.read_file(
                self.auth.get_token(),
                resource
            )
        except Exception as e:
            self.status_handler.handle_errors(e)

        # Collect all chunks
        bcontent = b''
        for chunk in result:
            if isinstance(chunk, Exception):
                raise chunk
            bcontent += chunk

        if format == "byte":
            return (bcontent, "byte", bcontent) if raw else (bcontent, "byte")

        if format is None or format == "text":
            try:
                text_content = bcontent.decode("utf8")
                return (text_content, "text", bcontent) if raw else (text_content, "text")
            except UnicodeError as e:
                if format == "text":
                    raise web.HTTPError(400, "Cannot decode file, file type may not be supported: %s" % path) from e
        # Fall back to base64
        b64_content = base64.encodebytes(bcontent).decode("ascii")
        return (b64_content, "base64", bcontent) if raw else (b64_content, "base64")

    def _save_file(self, path: str, content: Union[str, bytes], format: str) -> None:
        """Save a file with CS3."""
        try:
            if format == "text":
                bcontent = content.encode("utf8")
            else:
                b64_bytes = content.encode("ascii")
                bcontent = base64.decodebytes(b64_bytes)
        except Exception as e:
            return self.status_handler.handle_errors(e)
        resource = self._resource_from_path(path)
        try:
            self.client.file.write_file(
                self.auth.get_token(),
                resource,
                bcontent,
                len(bcontent)
            )
        except Exception as e:
            self.status_handler.handle_errors(e)

    def get_dir_size(self, path: str) -> int:
        """Calculate total size of directory and subdirectories using CS3 stat."""
        try:
            resource = self._resource_from_path(path)
            try:
                result = self.client.file.stat(
                    self.auth.get_token(),
                    resource
                )
            except Exception as e:
                self.status_handler.handle_errors(e)

            # Get stat info which includes tree_size in opaque metadata
            stat_result = StatResult(result)

            # If it's a file, return its size
            if stat_result.st_mode & stat.S_IFREG:
                return stat_result.st_size

            # For directories, try to get tree_size from opaque metadata
            if result and hasattr(result, 'opaque') and result.opaque:
                # Look for EOS metadata with tree_size
                for key, value in result.opaque.map.items():
                    if key == "eos" and value.decoder == "json":
                        import json
                        try:
                            eos_data = json.loads(value.value.decode('utf-8'))
                            if 'tree_size' in eos_data:
                                return int(eos_data['tree_size'])
                        except (json.JSONDecodeError, KeyError, ValueError):
                            pass

            # Fallback to directory size (not including subdirectories)
            return stat_result.st_size

        except Exception as e:
            self.log.warning(f"Error calculating directory size for {path}: {e}")
            return 0

    async def copyfile(self, src: str, dst: str) -> None:
        """Copy file contents using streaming to avoid loading entire file in memory."""
        src_resource = self._resource_from_path(src)
        dst_resource = self._resource_from_path(dst)

        try:
            # Get the source file size first
            stat = self.client.file.stat(
                self.auth.get_token(),
                src_resource
            )

            file_size = stat.size

            # Get the content generator
            content_generator = self.client.file.read_file(
                self.auth.get_token(),
                src_resource
            )

            # Stream write
            self._write_file_streamed(dst_resource, content_generator, file_size)

        except Exception as e:
            self.status_handler.handle_errors(e)

    def _write_file_streamed(self, resource: Resource, content_generator: Generator[bytes, None, None], size: int) -> None:
        """Write a file using streaming to avoid loading entire content in memory."""
        try:
            self.client.file.write_file(
                self.auth.get_token(),
                resource,
                content_generator,  # Pass generator directly
                size
            )
        except Exception as e:
            self.status_handler.handle_errors(e)

    async def copy_tree(self, src: str, dst: str) -> None:
        """Copy directory tree."""
        self.mkdir(dst)
        dir_contents = self.list_dir(src)
        for dir_name, _ in dir_contents:
            src_path = os.path.join(src, dir_name)
            dst_path = os.path.join(dst, dir_name)

            if self.is_dir(src_path):
                await self.copy_tree(src_path, dst_path)
            else:
                await self.copyfile(src_path, dst_path)

    def rm_tree(self, path: str) -> None:
        """Remove directory tree."""
        if self.is_dir(path):
            self.unlink(path)

    # Jupyter core utils
    def ensure_dir_exists(self, path: str) -> None:
        """Ensure directory exists."""
        if not self.exists(path):
            parent = os.path.dirname(path)
            # Ensure parent directory exists
            if parent and not self.exists(parent):
                self.ensure_dir_exists(parent)
            self.mkdir(path)

    def list_file_versions(self, path: str) -> Generator["FileVersion", any, any]:  # noqa: F821
        """List file versions"""
        try:
            resource = self._resource_from_path(path)
            result = self.client.checkpoint.list_file_versions(
                self.auth.get_token(),
                resource
            )
            return result if result is not None else []
        except Exception as e:
            self.status_handler.handle_errors(e)
            return []

    def restore_file_version(self, path: str, key: str) -> None:
        """Restore a file version."""
        try:
            resource = self._resource_from_path(path)
            self.client.checkpoint.restore_file_version(
                self.auth.get_token(),
                resource,
                key
            )
        except Exception as e:
            self.status_handler.handle_errors(e)

    def create_share(self, path: str, opaque_id: str, idp: str, role: str, grantee_type: str) -> None:
        """Create a share for a given resource to a target user."""
        try:
            resource = self._resource_from_path(path)
            # We need the resource info for creating the share
            resource_info = self.client.file.stat(
                self.auth.get_token(),
                resource
            )
            if resource_info is None:
                raise web.HTTPError(404, "Resource not found: %s" % path)
            share = self.client.share.create_share(
                self.auth.get_token(),
                resource_info,
                opaque_id,
                idp,
                role,
                grantee_type
            )
            return share
        except Exception as e:
            self.status_handler.handle_errors(e)

    # This is when we want to list shares for a specific resource, such as
    # who we have shared a specific file with.
    def list_existing_shares_by_resource(self, path) -> List[dict]:
        """List existing shares for a given resource."""
        resource = self._resource_from_path(path)
        filter = self.client.share.create_share_filter(filter_type = "TYPE_RESOURCE_ID", resource_id = resource.id)
        try:
            result = self.client.share.list_existing_shares(
                self.auth.get_token(),
                [filter]
            )
            return result if result is not None else []
        except Exception as e:
            self.status_handler.handle_errors(e)
            return []

    # This is when we want to list "shared by me" shares
    def list_existing_shares_by_creator(self, creator_idp: str, creator_opaque_id: str) -> List[dict]:
        """List existing shares created by a user."""
        print(f"Listing shares for creator_idp: {creator_idp}, creator_opaque_id: {creator_opaque_id}")
        filter = self.client.share.create_share_filter(filter_type="TYPE_CREATOR", creator_opaque_id=creator_opaque_id, creator_idp=creator_idp)
        try:
            result = self.client.share.list_existing_shares(
                self.auth.get_token(),
                [filter]
            )
            return result if result is not None else []
        except Exception as e:
            self.status_handler.handle_errors(e)
            return []

    def remove_share(self, share_id: str) -> None:
        """Remove a share by its ID."""
        try:
            self.client.share.remove_share(
                self.auth.get_token(),
                opaque_id=share_id
            )
        except Exception as e:
            self.status_handler.handle_errors(e)

    def update_share(self, share_id: str, role: str = None, display_name: str = None) -> None:
        """Update a shares role/display name by using its unique ID."""
        try:
            share = self.client.share.update_share(
                self.auth.get_token(),
                role=role,
                opaque_id=share_id,
                display_name=display_name,
            )
        except Exception as e:
            self.status_handler.handle_errors(e)
        return share

    def list_received_existing_shares(self) -> List[dict]:
        """List existing received shares."""
        try:
            result = self.client.share.list_received_existing_shares(
                self.auth.get_token()
            )
            return result if result is not None else []
        except Exception as e:
            self.status_handler.handle_errors(e)
            return []

    def update_received_share(self, share_id: str, hidden: bool) -> None:
        """Update a received shares state by using its unique ID."""
        if not hidden:
            state = "SHARE_STATE_ACCEPTED"
        else:
            state = "SHARE_STATE_REJECTED"
        try:
            self.client.share.update_received_share(
                self.auth.get_token(),
                share_id,
                state
            )
        except Exception as e:
            self.status_handler.handle_errors(e)

    def create_public_share(self, path: str, role: str, password: str = None, expiration: str = None,
                            description: str = None, internal: bool = False, notify_uploads: bool = False,
                            notify_uploads_extra_recipients: Optional[list] = None) -> dict:
        """Create a public share for a given resource."""
        try:
            resource = self._resource_from_path(path)
            resource_info = self.client.file.stat(
                self.auth.get_token(),
                resource
            )
            if resource_info is None:
                raise web.HTTPError(404, "Resource not found: %s" % path)
            share = self.client.share.create_public_share(
                self.auth.get_token(),
                resource_info,
                role=role,
                password=password,
                expiration=expiration,
                description=description,
                internal=internal,
                notify_uploads=notify_uploads,
                notify_uploads_extra_recipients=notify_uploads_extra_recipients
            )
            return share
        except Exception as e:
            self.status_handler.handle_errors(e)
            return {}

    def list_existing_public_shares_by_creator(self, creator_idp: str, creator_opaque_id: str) -> List[dict]:
        """List existing public shares by creator."""
        filter = self.client.share.create_public_share_filter(filter_type="TYPE_CREATOR", creator_idp=creator_idp, creator_opaque_id=creator_opaque_id)
        try:
            result = self.client.share.list_existing_public_shares(
                self.auth.get_token(),
                [filter]
            )
            return result if result is not None else []
        except Exception as e:
            self.status_handler.handle_errors(e)
            return []

    def list_existing_public_shares_by_resource(self, path: str) -> List[dict]:
        """List existing public shares for a given resource."""
        resource = self._resource_from_path(path)
        filter = self.client.share.create_public_share_filter("TYPE_RESOURCE_ID", resource.id)
        try:
            result = self.client.share.list_existing_public_shares(
                self.auth.get_token(),
                [filter]
            )
            return result if result is not None else []
        except Exception as e:
            self.status_handler.handle_errors(e)
            return []

    def update_public_share(self, share_id: str, type: str,role: str = None, password: str = None,
                            expiration: str = None, description: str = None,
                            notify_uploads: bool = None, display_name: str = None,  notify_uploads_extra_recipients: Optional[list] = None) -> None:
        """Update a public share by its ID."""
        try:
            share = self.client.share.update_public_share(
                self.auth.get_token(),
                type=type,
                role=role,
                opaque_id=share_id,
                password=password,
                expiration=expiration,
                description=description,
                notify_uploads=notify_uploads,
                display_name=display_name,
                notify_uploads_extra_recipients=notify_uploads_extra_recipients
            )
        except Exception as e:
            self.log.error("Error updating public share:", e)
            self.status_handler.handle_errors(e)
        return share

    def remove_public_share(self, share_id: str) -> None:
        """Remove a public share by its ID."""
        try:
            self.client.share.remove_public_share(
                self.auth.get_token(),
                opaque_id=share_id
            )
        except Exception as e:
            self.status_handler.handle_errors(e)

    def find_users(self, query: str, user_type: str) -> List[dict]:
        """Find users matching a query.
        :param query: The query string for TYPE_QUERY filter.
        :param user_type: The user type for TYPE_USER_TYPE filter. Supported types: USER_TYPE_PRIMARY,
            USER_TYPE_SECONDARY, USER_TYPE_SERVICE, USER_TYPE_GUEST, USER_TYPE_FEDERATED, USER_TYPE_LIGHTWEIGHT,
            USER_TYPE_SPACE_OWNER.
        """
        filters = []
        if query:
            filters.append(User.create_find_user_filter("TYPE_QUERY", query=query))
        if user_type:
            filters.append(User.create_find_user_filter("TYPE_USERTYPE", user_type=user_type))

        try:
            result = self.client.user.find_users(
                self.auth.get_token(),
                filters
            )
            return result if result is not None else []
        except Exception as e:
            self.status_handler.handle_errors(e)
            return []

    def find_groups(self, query: str, group_type) -> List[dict]:
        """
        Find groups matching a query.

        :param query: The query string for TYPE_QUERY filter.
        :param group_type: The group type for the TYPE_GROUPTYPE filter, GROUP_TYPE_FEDERATED or GROUP_TYPE_REGULAR.

        """
        filters = []
        if query:
            filters.append(self.client.group.create_find_group_filter("TYPE_QUERY", query))
        if group_type:
            filters.append(self.client.group.create_find_group_filter("TYPE_GROUP_TYPE", group_type))

        try:
            result = self.client.group.find_groups(
                self.auth.get_token(),
                filters
            )
            return result if result is not None else []
        except Exception as e:
            self.status_handler.handle_errors(e)
            return []

    def list_spaces(self) -> List[dict]:
        """List existing spaces."""
        filter = self.client.space.create_storage_space_filter(filter_type = "TYPE_SPACE_TYPE", space_type = "project")
        try:
            result = self.client.space.list_storage_spaces(
                self.auth.get_token(),
                [filter]
            )
            return result if result is not None else []
        except Exception as e:
            self.status_handler.handle_errors(e)
            return []

class CS3File:
    """File-like object for CS3 storage with proper context manager support."""

    def __init__(self, cs3_fs: CS3FileSystem, path: str, mode: str = 'r', encoding: Optional[str] = None) -> None:
        self.cs3_fs = cs3_fs
        self.path = path
        self.mode = mode
        self.encoding = encoding or 'utf-8'
        self._content: Union[str, bytes, None] = None
        self._position = 0
        self._closed = False
        self._modified = False

    def _init(self) -> None:
        """Initialization after creation."""
        # Load content if reading
        if 'r' in self.mode or 'a' in self.mode:
            self._load_content()
        else:
            self._content = b'' if 'b' in self.mode else ''

    def _load_content(self) -> None:
        """Load file content from CS3."""
        try:
            if 'b' in self.mode:
                result = self.cs3_fs._read_file(self.path, "byte")
                self._content = result[0]
            else:
                result = self.cs3_fs._read_file(self.path, "text")
                self._content = result[0]
        except Exception:
            if 'r' in self.mode:
                raise
            self._content = b'' if 'b' in self.mode else ''

    def read(self, size: int = -1) -> Union[str, bytes]:
        """Read from file."""
        if self._closed:
            raise ValueError("I/O operation on closed file")

        if size == -1:
            result = self._content[self._position:]
            self._position = len(self._content)
        else:
            result = self._content[self._position:self._position + size]
            self._position += len(result)

        return result

    def write(self, data: Union[str, bytes]) -> int:
        """Write to file."""
        if self._closed:
            raise ValueError("I/O operation on closed file")

        if 'r' in self.mode and 'w' not in self.mode and 'a' not in self.mode:
            raise OSError("File not open for writing")

        if isinstance(data, str) and 'b' in self.mode:
            data = data.encode(self.encoding)
        elif isinstance(data, bytes) and 'b' not in self.mode:
            data = data.decode(self.encoding)

        if 'a' in self.mode:
            self._content += data
        else:
            self._content = self._content[:self._position] + data + self._content[self._position + len(data):]
            self._position += len(data)

        self._modified = True
        return len(data)

    def flush(self) -> None:
        """Flush to CS3 storage."""
        if self._closed or not self._modified:
            return

        if 'w' in self.mode or 'a' in self.mode:
            if isinstance(self._content, str):
                format = "text"
                content = self._content
            else:
                format = "base64"
                content = base64.encodebytes(self._content).decode("ascii")

            self.cs3_fs._save_file(self.path, content, format)
            self._modified = False

    def close(self) -> None:
        """Close file."""
        if not self._closed:
            self.flush()
            self._closed = True

    def __enter__(self) -> 'CS3File':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def fileno(self) -> int:
        """Get file descriptor (not applicable for CS3)."""
        raise NotImplementedError("File descriptors not supported in CS3")

# Convenience function to create a global CS3 file system instance
def create_cs3_filesystem(config, root_path, client_id = None, client_secret = None) -> CS3FileSystem:
    """Create a CS3FileSystem instance."""
    cs3_fs = CS3FileSystem(config, root_path, client_id=client_id, client_secret=client_secret)
    return cs3_fs
