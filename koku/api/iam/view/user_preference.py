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
from django.forms.models import model_to_dict
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import exceptions, mixins, viewsets
from rest_framework.authentication import (SessionAuthentication,
                                           TokenAuthentication)
from rest_framework.permissions import IsAuthenticated

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
    authentication_classes = (TokenAuthentication,
                              SessionAuthentication)
    permission_classes = (IsObjectOwner, IsAuthenticated)
    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('name',)

    def get_queryset(self):
        """Get a queryset that only displays the owner's preferences."""
        return self.queryset.filter(user=self.request.user)

    def _validate_user(self, user_id, uuid):
        """Validate that the user object is assigned the given uuid."""
        user_a = models.User.objects.get(id=user_id)
        user_b = models.User.objects.get(uuid=uuid)
        return user_a == user_b

    def create(self, request, *args, **kwargs):
        """Create a user preference.

        @api {post} /api/v1/user/:user_uuid/preferences/ Create a user preference
        @apiName createUserPreference
        @apiGroup UserPreferences
        @apiVersion 1.0.0
        @apiDescription Create a user preference.

        @apiHeader {String} token User authorization token.
        @apiHeaderExample {json} Header-Example:
            {
                "Authorization": "Token 45138a913da44ab89532bab0352ef84b"
            }

        @apiParam {String} user_uuid User unique ID.

        @apiParam (Request Body) {String} preference a stringified JSON object
        @apiParamExample {json} Request Body:
            {
                "name": "my-preference-name",
                'preference': {'currency': 'USD'},
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
        if not self._validate_user(request.user.id, kwargs['user_uuid']):
            # don't allow user_a to set user_b's preferences
            raise exceptions.PermissionDenied()

        user = models.User.objects.get(uuid=kwargs['user_uuid'])
        request.data['user'] = model_to_dict(user)
        return super().create(request=request, args=args, kwargs=kwargs)

    def list(self, request, *args, **kwargs):
        """Obtain the list of preferences for the user.

        @api {get} /api/v1/user/:user_uuid/preferences/ Obtain a list of user preferences
        @apiName GetUserPreferences
        @apiGroup UserPreferences
        @apiVersion 1.0.0
        @apiDescription Obtain the list of preferences for the user.

        @apiHeader {String} token User authorization token.
        @apiHeaderExample {json} Header-Example:
            {
                "Authorization": "Token 45138a913da44ab89532bab0352ef84b"
            }

        @apiParam (Path) {String} user_uuid User unique ID.

        @apiParam (Query) {String} name Filter by preference name.

        @apiSuccess {Number} count The number of preferences.
        @apiSuccess {String} previous  The uri of the previous page of results.
        @apiSuccess {String} next  The uri of the next page of results.
        @apiSuccess {Object[]} results  The array of preference results.
        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                'count': 3,
                'next': None,
                'previous': None,
                'results': [
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
        if not self._validate_user(request.user.id, kwargs['user_uuid']):
            # don't allow user_a to see user_b's preferences
            raise exceptions.PermissionDenied()

        return super().list(request=request, args=args, kwargs=kwargs)

    def retrieve(self, request, *args, **kwargs):
        """Get a user preference.

        @api {get} /api/v1/user/:user_uuid/preferences/:pref_uuid Get a preference
        @apiName GetUserPreference
        @apiGroup UserPreferences
        @apiVersion 1.0.0
        @apiDescription Get a user preference.

        @apiHeader {String} token User authorization token.
        @apiHeaderExample {json} Header-Example:
            {
                "Authorization": "Token 45138a913da44ab89532bab0352ef84b"
            }

        @apiParam {String} user_uuid User unique ID.
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
        if not self._validate_user(request.user.id, kwargs['user_uuid']):
            # don't allow user_a to see user_b's preferences
            raise exceptions.PermissionDenied()

        return super().retrieve(request=request, args=args, kwargs=kwargs)

    def destroy(self, request, *args, **kwargs):
        """Delete a user preference.

        @api {delete} /api/v1/user/:user_uuid/preferences/:pref_uuid Delete a preference
        @apiName DeleteUserPreference
        @apiGroup UserPreferences
        @apiVersion 1.0.0
        @apiDescription Delete a user preference.

        @apiHeader {String} token User authorization token.
        @apiHeaderExample {json} Header-Example:
            {
                "Authorization": "Token 45138a913da44ab89532bab0352ef84b"
            }

        @apiParam {String} user_uuid User unique ID.
        @apiParam {String} pref_uuid User Preference unique ID.

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 204 NO CONTENT
        """
        if not self._validate_user(request.user.id, kwargs['user_uuid']):
            # don't allow user_a to delete user_b's preferences
            raise exceptions.PermissionDenied()

        return super().destroy(request=request, args=args, kwargs=kwargs)

    def update(self, request, *args, **kwargs):
        """Update a user preference.

        @api {put} /api/v1/user/:user_uuid/preferences/:pref_uuid Update a preference
        @apiName UpdateUserPreference
        @apiGroup UserPreferences
        @apiVersion 1.0.0
        @apiDescription Udpate a user preference.

        @apiHeader {String} token User authorization token.
        @apiHeaderExample {json} Header-Example:
            {
                "Authorization": "Token 45138a913da44ab89532bab0352ef84b"
            }

        @apiParam {String} user_uuid User unique ID.
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
        if not self._validate_user(request.user.id, kwargs['user_uuid']):
            # don't allow user_a to delete user_b's preferences
            raise exceptions.PermissionDenied()

        user = models.User.objects.get(uuid=kwargs['user_uuid'])
        request.data['user'] = model_to_dict(user)
        return super(UserPreferenceViewSet, self).update(request=request, args=args, kwargs=kwargs)
