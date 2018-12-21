#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

"""Common pagination class."""
import logging

from rest_framework.pagination import PageNumberPagination

PATH_INFO = 'PATH_INFO'
logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class StandardResultsSetPagination(PageNumberPagination):
    """Create standard paginiation class with page size."""

    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 1000

    @staticmethod
    def link_rewrite(request, link):
        """Rewrite the link based on the path header to only provide partial url."""
        url = link
        if PATH_INFO in request.META:
            try:
                local_api_index = link.index('api/')
                path = request.META.get(PATH_INFO)
                path_api_index = path.index('api/')
                path_link = '{}{}'
                url = path_link.format(path[:path_api_index],
                                       link[local_api_index:])
            except ValueError:
                logger.warning('Unable to rewrite link as "api" was not found.')
        return url

    def get_next_link(self):
        """Create next link with partial url rewrite."""
        next_link = super().get_next_link()
        if next_link is None:
            return next_link
        return StandardResultsSetPagination.link_rewrite(self.request, next_link)

    def get_previous_link(self):
        """Create previous link with partial url rewrite."""
        previous_link = super().get_previous_link()
        if previous_link is None:
            return previous_link
        return StandardResultsSetPagination.link_rewrite(self.request, previous_link)
