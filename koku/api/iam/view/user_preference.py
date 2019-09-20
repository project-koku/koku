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

"""View for User Preferences."""
from django.views.decorators.cache import cache_control, never_cache
from django.views.decorators.vary import vary_on_headers
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import exceptions, mixins, viewsets
from rest_framework.permissions import AllowAny

import api.iam.models as models
import api.iam.serializers as serializers
from api.common.permissions.object_owner import IsObjectOwner


class UserPreferenceViewSet(mixins.CreateModelMixin,
                            mixins.DestroyModelMixin,
                            mixins.ListModelMixin,
                            mixins.RetrieveModelMixin,
                            mixins.UpdateModelMixin,
                            viewsets.GenericViewSet):
    """User Preference View.

    A viewset that provides default `create()`, `destroy`, `retrieve()`,
    and `list()` actions.
    """

    lookup_field = 'uuid'
    queryset = models.UserPreference.objects.all()
    serializer_class = serializers.UserPreferenceSerializer
    permission_classes = (IsObjectOwner, AllowAny)
    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('name',)

    def get_queryset(self):
        """Get a queryset that only displays the owner's preferences."""
        queryset = models.UserPreference.objects.none()
        req_user = self.request.user
        if req_user:
            queryset = self.queryset.filter(user=req_user)
        return queryset

    def get_serializer_context(self):
        """Pass user attribute to serializer."""
        context = super().get_serializer_context()
        req_user = self.request.user
        if req_user:
            context['user'] = req_user
        return context

    def _validate_user(self, user_id, uuid):
        """Validate that the user object is assigned the given uuid."""
        user_a = models.User.objects.get(id=user_id)
        user_b = models.User.objects.get(uuid=uuid)
        return user_a == user_b

    @never_cache
    def create(self, request, *args, **kwargs):
        """Create a user preference.

        @api {post} /cost-management/v1/preferences/ Create a user preference
        @apiName createUserPreference
        @apiGroup UserPreferences
        @apiVersion 1.0.0
        @apiDescription Create a user preference.

        @apiHeader {String} token User authorization token.

        @apiParam (Request Body) {String} name User preference name.
                                               No requirement to match the key in preference
        @apiParam (Request Body) {Object} preference Preference value
        @apiParam (Request Body) {String} [description] The description of the user preference.
        @apiParamExample {json} Request Body:
            {
                "name": "my-preference-name",
                "preference": {"currency": "USD"},
                "description": "description of my-preference-name"
            }

        @apiSuccess {String} uuid The identifier of the preference.
        @apiSuccess {String} user_uuid The identifier of the user.
        @apiSuccess {Object} preference The user preference JSON object.
        @apiSuccess {String} name The name of the user preference.
        @apiSuccess {String} description The description of the user preference.
        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 201 CREATED
            {
                'uuid': 'ff2cb4a9-26c3-4b97-9b19-74560698676d',
                'preference': {'currency': 'USD'},
                'name': 'my-preference-name',
                'description': None,
                'user': 'a3feac7b-8366-4bd8-8958-163a0ae85f25'
            }
        """
        user = request.user

        # if the pref already exists, it's a bad request
        query = models.UserPreference.objects.filter(user=user,
                                                     name=request.data.get('name'))
        if query.count():
            message = 'UserPreference({pref}) already exists for User({user})'
            raise exceptions.ParseError(detail=message.format(pref=request.data.get('name'),
                                                              user=user.username))

        return super().create(request=request, args=args, kwargs=kwargs)

    @cache_control(private=True)
    @vary_on_headers('User-Agent', 'Cookie')
    def list(self, request, *args, **kwargs):
        """Obtain the list of preferences for the user.

        @api {get} /cost-management/v1/preferences/ Obtain a list of user preferences
        @apiName GetUserPreferences
        @apiGroup UserPreferences
        @apiVersion 1.0.0
        @apiDescription Obtain the list of preferences for the user.

        @apiHeader {String} token User authorization token.

        @apiParam (Query) {String} name Filter by preference name.

        @apiSuccess {Object} meta The metadata for pagination.
        @apiSuccess {Object} links  The object containing links of results.
        @apiSuccess {Object[]} data  The array of results.
        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                'meta': {
                    'count': 3
                }
                'links': {
                    'first': /cost-management/v1/preferences/?page=1,
                    'next': None,
                    'previous': None,
                    'last': /cost-management/v1/preferences/?page=1
                },
                'data': [
                                {
                                    'uuid': '7f273d8a-50cb-4a3a-a4c0-6b7fae0bfd61',
                                    'preference': {'currency': 'USD'},
                                    'name': 'currency',
                                    'description': 'default preference',
                                    'user': 'a3feac7b-8366-4bd8-8958-163a0ae85f25'
                                },
                                {
                                    'uuid': 'b5572625-0856-4ecf-a6fd-d1977114e90c',
                                    'preference': {'locale': 'en_US.UTF-8'},
                                    'name': 'locale',
                                    'description': 'default preference',
                                    'user': 'a3feac7b-8366-4bd8-8958-163a0ae85f25'
                                },
                                {
                                    'uuid': '7c7d73c1-9134-4736-b92b-4fee4811ba96',
                                    'preference': {'timezone': 'UTC'},
                                    'name': 'timezone',
                                    'description': 'default preference',
                                    'user': 'a3feac7b-8366-4bd8-8958-163a0ae85f25'
                                }
                            ]
            }
        """
        return super().list(request=request, args=args, kwargs=kwargs)

    @cache_control(private=True)
    @vary_on_headers('User-Agent', 'Cookie')
    def retrieve(self, request, *args, **kwargs):
        """Get a user preference.

        @api {get} /cost-management/v1/preferences/:pref_uuid Get a preference
        @apiName GetUserPreference
        @apiGroup UserPreferences
        @apiVersion 1.0.0
        @apiDescription Get a user preference.

        @apiHeader {String} token User authorization token.

        @apiParam {String} pref_uuid User Preference unique ID.

        @apiSuccess {String} uuid The identifier of the preference.
        @apiSuccess {String} user_uuid The identifier of the user.
        @apiSuccess {Object} preference The user preference JSON object.
        @apiSuccess {String} name The name of the user preference.
        @apiSuccess {String} description The description of the user preference.
        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                'uuid': '74d17664-08da-4690-8945-d79adc06d6e4',
                'preference': {'currency': 'USD'},
                'name': 'currency',
                'description': 'default preference',
                'user': 'a3feac7b-8366-4bd8-8958-163a0ae85f25'
            }
        """
        return super().retrieve(request=request, args=args, kwargs=kwargs)

    @never_cache
    def destroy(self, request, *args, **kwargs):
        """Delete a user preference.

        @api {delete} /cost-management/v1/preferences/:pref_uuid Delete a preference
        @apiName DeleteUserPreference
        @apiGroup UserPreferences
        @apiVersion 1.0.0
        @apiDescription Delete a user preference.

        @apiHeader {String} token User authorization token.

        @apiParam {String} pref_uuid User Preference unique ID.

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 204 NO CONTENT
        """
        return super().destroy(request=request, args=args, kwargs=kwargs)

    @never_cache
    def update(self, request, *args, **kwargs):
        """Update a user preference.

        @api {put} /cost-management/v1/preferences/:pref_uuid Update a preference
        @apiName UpdateUserPreference
        @apiGroup UserPreferences
        @apiVersion 1.0.0
        @apiDescription Udpate a user preference.

        @apiHeader {String} token User authorization header.

        @apiParam {String} pref_uuid User Preference unique ID.

        @apiSuccess {String} uuid The identifier of the preference.
        @apiSuccess {String} user_uuid The identifier of the user.
        @apiSuccess {Object} preference The user preference JSON object.
        @apiSuccess {String} name The name of the user preference.
        @apiSuccess {String} description The description of the user preference.
        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                'uuid': '91b057af-a2a6-453b-93b8-35385a512b7b',
                'name': 'test-pref',
                'description': 'test-pref',
                'preference': {'test-pref': ['a', ['b', 'c'], {'foo': 'bar'}]},
                'user': 'a3feac7b-8366-4bd8-8958-163a0ae85f25'
            }
        """
        return super(UserPreferenceViewSet, self).update(request=request, args=args, kwargs=kwargs)
