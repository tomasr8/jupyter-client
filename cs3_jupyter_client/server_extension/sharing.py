# sharing/handlers.py
import jwt
from typing import cast
from tornado import web
from jupyter_server.base.handlers import APIHandler
from jupyter_server.utils import url_path_join
from google.protobuf.json_format import MessageToDict
from ..cs3fs.statuscodehandler import ErrorToHttpCode
from ..fileio import CS3FileManagerMixin

CS3_SERVICE_KEY = 'cs3_service'


class CS3APIHandler(APIHandler):
    """Base handler that provides access to the CS3 service regardless of
    which ContentsManager is configured."""

    @property
    def cs3_service(self) -> CS3FileManagerMixin:
        return self.settings[CS3_SERVICE_KEY]


class SharesHandler(CS3APIHandler):

    @web.authenticated
    async def post(self):
        """
        Create a share for a resource.
        :query param path: path to the resource(REQUIRED).
        :field opaque_id: Opaque group/user id, (REQUIRED).
        :field idp: Identity provider, (REQUIRED).
        :field role: Role to assign to the grantee, VIEWER or EDITOR (REQUIRED).
        :field grantee_type: Type of grantee, USER or GROUP (REQUIRED).
        """
        # Get the resource path from query parameters
        path = self.get_query_argument("path", default="")
        # Get other parameters from the request body
        body = self.get_json_body() or {}
        opaque_id = body.get("opaque_id", "")
        idp = body.get("idp", "")
        role = body.get("role", "")
        grantee_type = body.get("grantee_type", "USER")

        # Reuse client from the contents manager
        cm = self.cs3_service
        self.log.info(f"Creating share for path: {path} to {grantee_type} {opaque_id} with role {role}")
        try:
            share = cm.create_share(opaque_id, idp, role, path, grantee_type)
        except Exception as e:
            http_code = ErrorToHttpCode().map_exception_to_http_code(e)
            self.set_status(http_code)
            self.write({"error": str(e)})
            return

        share = MessageToDict(share, preserving_proto_field_name=True)

        self.set_status(201)
        self.write({"created": True, "data": body, "path": path, "share": share})

    @web.authenticated
    async def put(self):
        """
        Update a share for a resource.
        :query param share_id: The ID of the share to update (REQUIRED).
        :field role: Role to update the share, VIEWER or EDITOR (REQUIRED).
        :field display_name: new display name.
        """
        # Get the resource path from query parameters
        share_id = self.get_query_argument("share_id", default=None)
        body = self.get_json_body() or {}
        role = body.get("role", None)
        display_name = body.get("display_name", None)

        cm = self.cs3_service
        self.log.info(f"Updating share: {share_id} with role {role} and display name {display_name}")
        try:
            share = cm.update_share(share_id, role=role, display_name=display_name)
        except Exception as e:
            http_code = ErrorToHttpCode().map_exception_to_http_code(e)
            self.set_status(http_code)
            self.write({"error": str(e)})
            return

        share = MessageToDict(share, preserving_proto_field_name=True)
        self.set_status(200)
        self.write({"updated": True, "data": body, "share": share})

    @web.authenticated
    async def delete(self):
        """
        Remove a share for a resource.
        :field share_id: The ID of the share to remove (REQUIRED).
        """
        # Get the resource path from query parameters
        share_id = self.get_query_argument("share_id", default=None)
        cm = self.cs3_service
        try:
            cm.remove_share(share_id)
        except Exception as e:
            http_code = ErrorToHttpCode().map_exception_to_http_code(e)
            self.set_status(http_code)
            self.write({"error": str(e)})
            return

        self.set_status(204)

class LinkHandler(CS3APIHandler):

    @web.authenticated
    async def post(self):
        """
        Create a public link for a resource.
        :query param path: path to the resource(REQUIRED).
        :field role: Role to assign to the grantee, VIEWER or EDITOR (REQUIRED)
        :field password: Password to access the share.
        :field expiration: Expiration timestamp for the share.
        :field description: Description for the share.
        :field internal: Internal share flag.
        :field notify_upload: Notify upload flag.
        :field notify_uploads_extra_recipients: List of extra recipients to notify on upload.
        """
        # Get the resource path from query parameters
        path = self.get_query_argument("path", default="")
        # Get other parameters from the request body
        body = self.get_json_body() or {}
        role = body.get("role", "")
        password = body.get("password", None)
        expiration = body.get("expiration", None)
        description = body.get("description", None)
        internal = body.get("internal", False)
        notify_uploads = body.get("notify_uploads", False)
        notify_uploads_extra_recipients = body.get("notify_uploads_extra_recipients", None)

        # Reuse client from the contents manager
        cm = self.cs3_service
        self.log.info(f"Creating public share for path: {path} with role {role}")
        try:
            share = cm.create_public_share(
                path,
                role,
                password=password,
                expiration=expiration,
                description=description,
                internal=internal,
                notify_uploads=notify_uploads,
                notify_uploads_extra_recipients=notify_uploads_extra_recipients
            )
        except Exception as e:
            http_code = ErrorToHttpCode().map_exception_to_http_code(e)
            self.set_status(http_code)
            self.write({"error": str(e)})
            return

        share = MessageToDict(share, preserving_proto_field_name=True)

        self.set_status(201)
        self.write({"created": True, "data": body, "path": path, "share": share})

    @web.authenticated
    async def put(self):
        """
        Update a public link for a resource.
        :query param opaque_id: The ID of the share to update (REQUIRED).
        :field type: Type of update to perform TYPE_PERMISSIONS, TYPE_PASSWORD, TYPE_EXPIRATION, TYPE_DISPLAYNAME,
                        TYPE_DESCRIPTION, TYPE_NOTIFYUPLOADS, TYPE_NOTIFYUPLOADSEXTRARECIPIENTS (REQUIRED).
        :field role: Role to assign to the grantee, VIEWER or EDITOR (REQUIRED).
        :field opaque_id: Opaque share id (REQUIRED).
        :field display_name: Display name for the share.
        :field description: Description for the share.
        :field notify_uploads: Notify uploads flag.
        :field expiration: Expiration timestamp for the share.
        :field notify_uploads_extra_recipients: List of extra recipients to notify on upload.
        :field password: Password to access the share.
        """
        # Get the share_id from query parameters
        share_id = self.get_query_argument("share_id", default="")
        # Get other parameters from the request body
        body = self.get_json_body() or {}
        type = body.get("type", "")
        role = body.get("role", "")
        password = body.get("password", None)
        expiration = body.get("expiration", None)
        description = body.get("description", None)
        display_name = body.get("display_name", None)
        notify_uploads = body.get("notify_uploads", False)
        notify_uploads_extra_recipients = body.get("notify_uploads_extra_recipients", None)

        cm = self.cs3_service

        self.log.info(f"Updating public share: {share_id} with type {type} role {role}")
        try:
            share = cm.update_public_share(
                share_id,
                type=type,
                role=role,
                password=password,
                expiration=expiration,
                description=description,
                notify_uploads=notify_uploads,
                display_name=display_name,
                notify_uploads_extra_recipients=notify_uploads_extra_recipients
            )
        except Exception as e:
            http_code = ErrorToHttpCode().map_exception_to_http_code(e)
            self.set_status(http_code)
            self.write({"error": str(e)})
            return
        share = MessageToDict(share, preserving_proto_field_name=True)

        self.set_status(200)
        self.write({"updated": True, "data": body, "share": share})

    @web.authenticated
    async def delete(self):
        """
        Remove a share for a resource.
        :field share_id: The ID of the share to remove (REQUIRED).
        """
        # Get the resource path from query parameters
        share_id = self.get_query_argument("share_id", default=None)
        cm = self.cs3_service

        try:
            cm.remove_public_share(share_id)
        except Exception as e:
            http_code = ErrorToHttpCode().map_exception_to_http_code(e)
            self.set_status(http_code)
            self.write({"error": str(e)})
            return

        self.set_status(204)

class SharedWithMeHandler(CS3APIHandler):
    @web.authenticated
    async def get(self):
        cm = self.cs3_service
        try:
            shares, _ = cm.list_received_existing_shares()
        except Exception as e:
            http_code = ErrorToHttpCode().map_exception_to_http_code(e)
            self.set_status(http_code)
            self.write({"error": str(e)})
            return
        shares_list = [
            MessageToDict(s, preserving_proto_field_name=True)
            for s in shares
        ]

        self.set_header("Content-Type", "application/json")
        self.write({"shares": shares_list})


class SharedByMeHandler(CS3APIHandler):
    """
    Handler for retrieving shares created by the user, both regular and public shares.
    """
    @web.authenticated
    async def get(self):
        headers = self.request.headers
        creator_idp = headers.get("creator_idp", "")
        creator_opaque_id = headers.get("creator_opaque_id", "")
        from ..cs3mixin import CS3Mixin
        cm = self.cs3_service
        if not creator_idp or not creator_opaque_id:
            decoded = jwt.decode(cast(CS3Mixin, cm).cs3_token, algorithms=["HS256"], options={"verify_signature": False})
            user_id = decoded.get("user", {}).get("id", {})
            creator_idp = creator_idp or user_id.get("idp", "")
            creator_opaque_id = creator_opaque_id or user_id.get("opaque_id", "")
        print(f"Listing shares created by user with idp: {creator_idp}, opaque_id: {creator_opaque_id}")
        shares, _ = cm.list_existing_shares_by_creator(creator_idp, creator_opaque_id)
        public_shares, _ = cm.list_existing_public_shares_by_creator(creator_idp, creator_opaque_id)
        # try:
        # except Exception as e:
        #     http_code = ErrorToHttpCode().map_exception_to_http_code(e)
        #     self.set_status(http_code)
        #     self.write({"error": str(e)})
        #     return
        shares_list = [
            MessageToDict(s, preserving_proto_field_name=True)
            for s in shares
        ]
        public_shares_list = [
            MessageToDict(s, preserving_proto_field_name=True)
            for s in public_shares
        ]
        self.set_header("Content-Type", "application/json")
        self.write({"shares": shares_list, "public_shares": public_shares_list})


class SharedByResourceHandler(CS3APIHandler):
    """
    Handler for retrieving regular and public shares created by the user for a specific resource.
    query param path: path to the resource (REQUIRED).
    """
    @web.authenticated
    async def get(self):
        path = self.get_query_argument("path", default="")
        cm = self.cs3_service
        try:
            shares, _ = cm.list_existing_shares_by_resource(path)
            public_shares, _ = cm.list_existing_public_shares_by_resource(path)
        except Exception as e:
            http_code = ErrorToHttpCode().map_exception_to_http_code(e)
            self.set_status(http_code)
            self.write({"error": str(e)})
            return
        shares_list = [
            MessageToDict(s, preserving_proto_field_name=True)
            for s in shares
        ]
        public_shares_list = [
            MessageToDict(s, preserving_proto_field_name=True)
            for s in public_shares
        ]
        self.set_header("Content-Type", "application/json")
        self.write({"shares": shares_list, "public_shares": public_shares_list})

class FindUsersHandler(CS3APIHandler):
    """
    Handler for finding users.
    :query search: The query string for TYPE_QUERY filter.
    :field user_type: The user type for TYPE_USER_TYPE filter. Supported types: USER_TYPE_PRIMARY,
        USER_TYPE_SECONDARY, USER_TYPE_SERVICE, USER_TYPE_GUEST, USER_TYPE_FEDERATED, USER_TYPE_LIGHTWEIGHT,
        USER_TYPE_SPACE_OWNER.
    """
    @web.authenticated
    async def get(self):
        search = self.get_query_argument("search", default="")
        user_type = self.get_query_argument("type", default=None)
        cm = self.cs3_service
        try:
            users = cm.find_users(search, user_type=user_type)
        except Exception as e:
            http_code = ErrorToHttpCode().map_exception_to_http_code(e)
            self.set_status(http_code)
            self.write({"error": str(e)})
            return
        users_list = [
            MessageToDict(s, preserving_proto_field_name=True)
            for s in users
        ]
        self.set_header("Content-Type", "application/json")
        self.write({"search": search, "items": users_list})

class FindGroupsHandler(CS3APIHandler):
    """
    Handler for finding groups.
    :query search: The query string for TYPE_QUERY filter.
    """
    @web.authenticated
    async def get(self):
        search = self.get_query_argument("search", default="")
        cm = self.cs3_service
        try:
            # We don't use GROUP_TYPE_FEDERATED, all groups are regular groups.
            groups = cm.find_groups(search, "GROUP_TYPE_REGULAR")
        except Exception as e:
            http_code = ErrorToHttpCode().map_exception_to_http_code(e)
            self.set_status(http_code)
            self.write({"error": str(e)})
            return
        groups_list = [
            MessageToDict(s, preserving_proto_field_name=True)
            for s in groups
        ]
        self.set_header("Content-Type", "application/json")
        self.write({"search": search, "items": groups_list})

class GetQuotaHandler(CS3APIHandler):
    """
    Handler for retrieving quota information for the user.
    """
    @web.authenticated
    async def get(self):
        cm = self.cs3_service
        path = self.get_query_argument("path", default="")
        # try:
        quota = cm.get_quota(path)
        # except Exception as e:
        #     http_code = ErrorToHttpCode().map_exception_to_http_code(e)
        #     self.set_status(http_code)
        #     self.write({"error": str(e)})
        #     return
        quota_dict = MessageToDict(quota, preserving_proto_field_name=True)
        self.set_header("Content-Type", "application/json")
        self.write({"quota": quota_dict})

class GetSpaceHandler(CS3APIHandler):
    """
    Handler for retrieving space information for the user.
    """
    @web.authenticated
    async def get(self):
        cm = self.cs3_service
        try:
            spaces = cm.list_spaces()
        except Exception as e:
            http_code = ErrorToHttpCode().map_exception_to_http_code(e)
            self.set_status(http_code)
            self.write({"error": str(e)})
            return
        spaces_list = [
            MessageToDict(s, preserving_proto_field_name=True)
            for s in spaces
        ]
        self.set_header("Content-Type", "application/json")
        self.write({"spaces": spaces_list})


default_handlers = [
        (url_path_join("share", "share"), SharesHandler),

        (url_path_join("share", "link"), LinkHandler),

        (url_path_join("share", "getSharedByMe"), SharedByMeHandler),

        (url_path_join("share", "getSharedWithMe"), SharedWithMeHandler),

        (url_path_join("share", "getSharedByResource"), SharedByResourceHandler),

        (url_path_join("find", "users"), FindUsersHandler),
        (url_path_join("find", "groups"), FindGroupsHandler),

        (url_path_join("quota"), GetQuotaHandler),
        (url_path_join("space", "list"), GetSpaceHandler),
]
