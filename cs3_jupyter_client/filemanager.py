"""A contents manager that uses the local file system for storage."""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
from __future__ import annotations

import os
import errno
import stat

from jupyter_server import _tz as tz
from anyio.to_thread import run_sync
from tornado import web
from traitlets import default, validate
from tornado.web import HTTPError

from .filecheckpoints import CS3FileCheckpoints
from .fileio import CS3FileManagerMixin
from jupyter_server.services.contents.manager import copy_pat
from pathlib import Path

'''
These are functions that have been reimplemented from jupyter.core.paths and os.path
'''

# replaces "import jupyter.core.paths is_file_hidden"
def is_file_hidden(os_path, stat_res=None):
    """Return whether a file is hidden based on its name."""
    p = Path(os_path)

    for part in p.parts:
        if part.startswith('.') and part not in ('.', '..'):
            return True

    return False

# replaces "import jupyter.core.paths is_hidden"
def is_hidden(os_path, root_dir=None):
    return is_file_hidden(os_path)

# replaces "import os.path.samefile"
def naive_same_file(path1, path2):
    """Check if two paths are the same file"""
    return  path1 == path2


'''
These are the modifications to the upstream Jupyter FileContentsManager that need significant changes
to work with CS3 filesystem or contain unecessary functionality for our use case - here it is not as simple
as replacing os calls with self.<method> calls.
'''
class CS3FileContentsManager(CS3FileManagerMixin):
    """An async file contents manager."""

    # Upstream uses os.getcwd
    # Different implementation
    @default("root_dir")
    def _default_root_dir(self):
        return self.get_user_path()

    # Upstream uses os.path.isabs and os.path.isdir
    # Different implementation
    @validate("root_dir")
    def _validate_root_dir(self, proposal):
        return self.get_user_path()

    # Upstream calls dir_exists which requires the CS3 filesystem to be ready.
    # Skip the existence check — the directory is validated at access time instead.
    @validate("preferred_dir")
    def _validate_preferred_dir(self, proposal):
        return proposal["value"]

    # Different import than upstream
    @default("checkpoints_class")
    def _checkpoints_class_default(self):
        return CS3FileCheckpoints

    # Different implementation than upstream (we don't need atomic writing)
    def is_writable(self, path, use_cache=True):
        """Does the API style path correspond to a writable directory or file?"""
        if use_cache and hasattr(self, '_writable_cache'):
            if path in self._writable_cache:
                return self._writable_cache[path]

        path = path.strip("/")
        os_path = self._get_os_path(path=path)
        try:
            result = self.access(os_path, os.W_OK)

            # Cache the result
            if use_cache:
                if not hasattr(self, '_writable_cache'):
                    self._writable_cache = {}
                self._writable_cache[path] = result

            return result
        except OSError:
            self.log.error("Failed to check write permissions on %s", os_path)
            return False

    # Upstream is significantly more complex due to os functionality
    # handling trashbin, and the windows/mac specifics.
    async def delete_file(self, path):
        """Delete file at path."""
        path = path.strip("/")
        os_path = self._get_os_path(path)

        if not self.allow_hidden and is_hidden(os_path, self.root_dir):
            raise web.HTTPError(400, f"Cannot delete file or directory {os_path!r}")
        if not await self.exists(path):
            raise web.HTTPError(404, "File or directory does not exist: %s" % os_path)
        if self.is_dir(os_path):
            self.log.debug("Removing directory %s", os_path)
            with self.perm_to_403():
                await run_sync(self.rmdir, os_path)
        else:
            self.log.debug("Unlinking file %s", os_path)
            with self.perm_to_403():
                await run_sync(self.unlink, os_path)

    async def _dir_model(self, path, content=True):
        """Build a model for a directory

        if content is requested, will include a listing of the directory
        """
        os_path = self._get_os_path(path)

        four_o_four = "directory does not exist: %r" % path
        ## Replaced os.path.isdir
        if not self.is_dir(os_path):
            raise web.HTTPError(404, four_o_four)
        ## replaced is_hidden with implementation above
        elif not self.allow_hidden and is_hidden(os_path, self.root_dir):
            self.log.info("Refusing to serve hidden directory %r, via 404 Error", os_path)
            raise web.HTTPError(404, four_o_four)

        model = self._base_model(path)
        model["type"] = "directory"
        model["size"] = None
        if content:
            model["content"] = contents = []
            os_dir = self._get_os_path(path)
            ## replaced os.listdir
            dir_contents = await run_sync(self.list_dir, os_dir)

            for dir_name, stat_info in dir_contents:
                try:
                    os_path = os.path.join(os_dir, dir_name)
                except UnicodeDecodeError as e:
                    # skip over broken symlinks in listing
                    if e.errno == errno.ENOENT:
                        self.log.warning("%s doesn't exist", os_path)
                    elif e.errno != errno.EACCES:  # Don't provide clues about protected files
                        self.log.warning("Error stat-ing %s: %r", os_path, e)
                    continue

                if (
                    not stat.S_ISLNK(stat_info.st_mode)
                    and not stat.S_ISREG(stat_info.st_mode)
                    and not stat.S_ISDIR(stat_info.st_mode)
                ):
                    self.log.debug("%s not a regular file", os_path)
                    continue

                try:
                    if self.should_list(dir_name) and (
                        ## replaced is_file_hidden with implementation above class
                        self.allow_hidden or not is_file_hidden(os_path, stat_res=stat_info)
                    ):
                        resource_model = {
                            "name": dir_name,
                            "path": f"{path}/{dir_name}",
                            "last_modified": tz.utcfromtimestamp(stat_info.st_mtime),
                            "created": tz.utcfromtimestamp(stat_info.st_ctime),
                            "size": stat_info.st_size,
                            "writable": stat_info.writeable,
                        }

                        if stat.S_ISDIR(stat_info.st_mode):
                            resource_model["type"] = "directory"
                        contents.append(resource_model)
                except OSError as e:
                    # ELOOP: recursive symlink, also don't show failure due to permissions
                    if e.errno not in [errno.ELOOP, errno.EACCES]:
                        self.log.warning(
                            "Unknown error checking if file %r is hidden",
                            os_path,
                            exc_info=True,
                        )

            model["format"] = "json"

        return model

    # Upstream uses AsyncContentsManager.copy which makes it is impossible to
    # to replace the os function in the super class (AsyncContentsManager - manager.py)
    # this needs to be fixed in upstream...
    # FIXME: This function is largely copied from upstream (with the AsyncContentsManager's
    # copy function inside).
    async def copy(self, from_path, to_path=None):
        """
        Copy an existing file or directory and return its new model.
        If to_path not specified, it will be the parent directory of from_path.
        If copying a file and to_path is a directory, filename/directoryname will increment `from_path-Copy#.ext`.
        Considering multi-part extensions, the Copy# part will be placed before the first dot for all the extensions except `ipynb`.
        For easier manual searching in case of notebooks, the Copy# part will be placed before the last dot.
        from_path must be a full path to a file or directory.
        """
        to_path_original = str(to_path)
        path = from_path.strip("/")
        if to_path is not None:
            to_path = to_path.strip("/")

        if "/" in path:
            from_dir, from_name = path.rsplit("/", 1)
        else:
            from_dir = ""
            from_name = path

        model = await self.get(path)
        # limit the size of folders being copied to prevent a timeout error
        if model["type"] == "directory":
            await self.check_folder_size(path)
        else:
            # Copied from AsyncContentManager and OS functionality replaced with cs3_fs functionality
            path = from_path.strip("/")

            if to_path is not None:
                to_path = to_path.strip("/")

            if "/" in path:
                from_dir, from_name = path.rsplit("/", 1)
            else:
                from_dir = ""
                from_name = path

            model = await self.get(path)
            model.pop("path", None)
            model.pop("name", None)
            if model["type"] == "directory":
                raise HTTPError(400, "Can't copy directories")

            is_destination_specified = to_path is not None
            if not is_destination_specified:
                to_path = from_dir
            if await self.dir_exists(to_path):
                name = copy_pat.sub(".", from_name)
                to_name = await self.increment_filename(name, to_path, insert="-Copy")
                to_path = f"{to_path}/{to_name}"
            elif is_destination_specified:
                if "/" in to_path:
                    to_dir, to_name = to_path.rsplit("/", 1)
                    if not await self.dir_exists(to_dir):
                        raise HTTPError(404, "No such parent directory: %s to copy file in" % to_dir)
            else:
                raise HTTPError(404, "No such directory: %s" % to_path)

            model = await self.save(model, to_path)
            self.emit(data={"action": "copy", "path": to_path, "source_path": from_path})
            return model

        is_destination_specified = to_path is not None
        to_name = copy_pat.sub(".", from_name)
        if not is_destination_specified:
            to_path = from_dir
        if await self.exists(to_path):
            name = copy_pat.sub(".", from_name)
            to_name = await self.increment_filename(name, to_path, insert="-Copy")
        to_path = f"{to_path}/{to_name}"

        return await self._copy_dir(
            from_path=from_path,
            to_path_original=to_path_original,
            to_name=to_name,
            to_path=to_path,
        )

    # Upstream uses subprocess to call du command to get directory size
    # and upstream is significantly more complex so no point in pushing this upstream
    async def _get_dir_size(self, path: str = ".") -> str:
        return self.get_dir_size(str(path))  # type:ignore[return-value]
