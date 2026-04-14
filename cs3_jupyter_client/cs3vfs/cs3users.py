"""
CS3 operations for users.

Authors: Rasmus Oscar Welander.
Emails: rasmus.oscar.welander@cern.ch.
"""

from typing import List


from cs3client.user import User
from .utils import retry_on_auth_failure

class CS3Users:
    """
    CS3 operations for users.
    """

    @retry_on_auth_failure
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

    @retry_on_auth_failure
    def get_user(self, idp: str, user_id: str) -> 'User':
        """Get user information by user ID and IDP."""
        try:
            result = self.client.user.get_user(
                idp,
                user_id,
            )
            return result if result is not None else {}
        except Exception as e:
            self.status_handler.handle_errors(e)
