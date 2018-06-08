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

"""View for Users."""
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import ugettext as _
from rest_framework import mixins, viewsets
from rest_framework.authentication import (SessionAuthentication,
                                           TokenAuthentication)
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.serializers import ValidationError


import api.iam.models as model
import api.iam.serializers as serializers
from api.common.permissions.customer_owner import IsCustomerOwner


class UserViewSet(mixins.CreateModelMixin,
                  mixins.DestroyModelMixin,
                  mixins.ListModelMixin,
                  mixins.RetrieveModelMixin,
                  viewsets.GenericViewSet):
    """User View .

    A viewset that provides default `create()`, `destroy`, `retrieve()`,
    and `list()` actions.
    """

    lookup_field = 'uuid'
    queryset = model.User.objects.all()
    serializer_class = serializers.UserSerializer
    authentication_classes = (TokenAuthentication,
                              SessionAuthentication)
    permission_classes = (IsCustomerOwner,)

    def get_queryset(self):
        """Get a queryset.

        Restricts the returned users to associated Customer,
        by filtering against a `user` object in the request.
        """
        queryset = model.User.objects.none()
        group = self.request.user.groups.first()
        if group:
            queryset = model.User.objects.filter(groups__id=group.id)
        return queryset

    def perform_create(self, serializer):
        """Create a user."""
        user = serializer.save()
        group = self.request.user.groups.first()
        if group:
            user.groups.add(group)
            user.save()

    def create(self, request, *args, **kwargs):
        """Create a user.

        @api {post} /api/v1/users/ Create a user
        @apiName createUser
        @apiGroup User
        @apiVersion 1.0.0
        @apiDescription Create a user.

        @apiHeader {String} token Customer owner authorization token.
        @apiHeaderExample {json} Header-Example:
            {
                "Authorization": "Token 45138a913da44ab89532bab0352ef84b"
            }

        @apiParam (Request Body) {String} username The username for access
        @apiParam (Request Body) {String} email The email address of the user
        @apiParam (Request Body) {String} password The password for the user
        @apiParamExample {json} Request Body:
            {
            "username": "smithj",
            "email": "smithj@mytechco.com",
            "password": "str0ng!P@ss"
            }

        @apiSuccess {String} uuid The identifier of the user.
        @apiSuccess {String} username  The name of the user.
        @apiSuccess {String} email  The email address of the user.
        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 201 CREATED
            {
                "uuid": "57e60f90-8c0c-4bd1-87a0-2143759aae1c",
                "username": "smithj",
                "email": "smithj@mytechco.com"
            }
        """
        return super().create(request=request, args=args, kwargs=kwargs)

    def list(self, request, *args, **kwargs):
        """Obtain the list of users.

        @api {get} /api/v1/users/ Obtain the list of users
        @apiName GetUsers
        @apiGroup User
        @apiVersion 1.0.0
        @apiDescription Obtain the list of users.

        @apiHeader {String} token User authorization token.
        @apiHeaderExample {json} Header-Example:
            {
                "Authorization": "Token 45138a913da44ab89532bab0352ef84b"
            }

        @apiSuccess {Number} count The number of users.
        @apiSuccess {String} previous  The uri of the previous page of results.
        @apiSuccess {String} next  The uri of the previous page of results.
        @apiSuccess {Object[]} results  The array of user results.
        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "count": 30,
                "previous": "/api/v1/users/?page=2",
                "next": "/api/v1/users/?page=4",
                "results": [
                    {
                        "uuid": "57e60f90-8c0c-4bd1-87a0-2143759aae1c",
                        "username": "smithj",
                        "email": "smithj@mytechco.com"
                    }
              ]
            }
        """
        return super().list(request=request, args=args, kwargs=kwargs)

    def retrieve(self, request, *args, **kwargs):
        """Get a user.

        @api {get} /api/v1/users/:uuid/ Get a user
        @apiName GetUser
        @apiGroup User
        @apiVersion 1.0.0
        @apiDescription Get a user.

        @apiHeader {String} token User authorization token.
        @apiHeaderExample {json} Header-Example:
            {
                "Authorization": "Token 45138a913da44ab89532bab0352ef84b"
            }

        @apiParam {String} uuid User unique ID.

        @apiSuccess {String} uuid The identifier of the user.
        @apiSuccess {String} username  The name of the user.
        @apiSuccess {String} email  The email address of the user.
        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "uuid": "57e60f90-8c0c-4bd1-87a0-2143759aae1c",
                "username": "smithj",
                "email": "smithj@mytechco.com"
            }
        """
        return super().retrieve(request=request, args=args, kwargs=kwargs)

    def destroy(self, request, *args, **kwargs):
        """Delete a user.

        @api {delete} /api/v1/users/:uuid/ Delete a user
        @apiName DeleteUser
        @apiGroup User
        @apiVersion 1.0.0
        @apiDescription Delete a user.

        @apiHeader {String} token Customer owner authorization token.
        @apiHeaderExample {json} Header-Example:
            {
                "Authorization": "Token 45138a913da44ab89532bab0352ef84b"
            }

        @apiParam {String} uuid User unique ID.

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 204 NO CONTENT
        """
        return super().destroy(request=request, args=args, kwargs=kwargs)

    @action(methods=['put'], detail=True, permission_classes=[AllowAny],
            url_path='reset-password', url_name='reset-password',
            serializer_class=serializers.PasswordChangeSerializer)
    def reset_password(self, request, uuid=None):
        """Reset a user's password.

        @api {put} /api/v1/users/:uuid/reset-password/ Reset user password
        @apiName ResetUserPassword
        @apiGroup User
        @apiVersion 1.0.0
        @apiDescription Reset a user's password.

        @apiParam {String} uuid User unique ID.

        @apiParam (Request Body) {String} token The reset token for the user
        @apiParam (Request Body) {String} password The password for the user
        @apiParamExample {json} Request Body:
            {
            "token": "cc0111c4ffab478e802c-579bd14f5818",
            "password": "str0ng!P@ss"
            }

        @apiSuccess {String} uuid The identifier of the user.
        @apiSuccess {String} username  The name of the user.
        @apiSuccess {String} email  The email address of the user.
        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "uuid": "57e60f90-8c0c-4bd1-87a0-2143759aae1c",
                "username": "smithj",
                "email": "smithj@mytechco.com"
            }
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = get_object_or_404(model.User.objects.all(), uuid=uuid)

        token = request.data.get('token')
        password = request.data.get('password')
        now = timezone.now()
        # check for reset token
        token_qs = model.ResetToken.objects.filter(token=token,
                                                   user=user,
                                                   used=False,
                                                   expiration_date__gt=now)
        if not token_qs.exists():
            error = {
                'token': [_('Token has expired or is invalid.')]
            }
            raise ValidationError(error)

        reset_token = token_qs.first()
        if user.check_password(password):
            msg = 'Password cannot be the same as the previous password.'
            error = {
                'password': [_(msg)]
            }
            raise ValidationError(error)

        user.set_password(password)
        user.save()
        reset_token.used = True
        reset_token.save()

        output = {'uuid': user.uuid,
                  'username': user.username,
                  'email': user.email}
        return Response(output)

    @action(methods=['get'], detail=False, permission_classes=[IsAuthenticated],
            url_path='current', url_name='current')
    def current(self, request):
        """Get the current user.

        @api {get} /api/v1/users/current/ Get the current user
        @apiName GetCurrentUser
        @apiGroup User
        @apiVersion 1.0.0
        @apiDescription Get the current user.

        @apiHeader {String} token User authorization token.
        @apiHeaderExample {json} Header-Example:
            {
                "Authorization": "Token 45138a913da44ab89532bab0352ef84b"
            }

        @apiSuccess {String} uuid The identifier of the user.
        @apiSuccess {String} username  The name of the user.
        @apiSuccess {String} email  The email address of the user.
        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "uuid": "57e60f90-8c0c-4bd1-87a0-2143759aae1c",
                "username": "smithj",
                "email": "smithj@mytechco.com"
            }
        """
        user = get_object_or_404(self.queryset, pk=request.user.id)
        output = {'uuid': user.uuid,
                  'username': user.username,
                  'email': user.email}
        return Response(output)
