"""
CS3 operations for groups.

Authors: Rasmus Oscar Welander.
Emails: rasmus.oscar.welander@cern.ch.
"""


from typing import List
from .utils import retry_on_auth_failure

class CS3Groups:
    """
    CS3 operations for groups.
    """

    @retry_on_auth_failure
    def find_groups(self, query: str, group_type) -> List[dict]:
        """
        Find groups matching a query.

        :param query: The query string for TYPE_QUERY filter.
        :param group_type: The group type for the TYPE_GROUPTYPE filter, GROUP_TYPE_FEDERATED or GROUP_TYPE_REGULAR.

        """
        filters = []
        if query:
            filters.append(self.client.group.create_find_group_filter("TYPE_QUERY", query=query, group_type=None))
        if group_type:
            filters.append(self.client.group.create_find_group_filter("TYPE_GROUPTYPE", query=None, group_type=group_type))

        try:
            result = self.client.group.find_groups(
                self.auth.get_token(),
                filters
            )
            return result if result is not None else []
        except Exception as e:
            self.status_handler.handle_errors(e)
            return []

    @retry_on_auth_failure
    def get_group(self, opaque_id: str, idp: str) -> dict:
        """
        Get information about a specific group by its ID and idp.
        """
        try:
            result = self.client.group.get_group(
                self.auth.get_token(),
                opaque_id,
                idp
            )
            return result if result is not None else {}
        except Exception as e:
            self.status_handler.handle_errors(e)
