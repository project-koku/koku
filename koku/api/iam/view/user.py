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

from rest_framework import mixins, viewsets

import api.iam.models as model
import api.iam.serializers as serializers


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

    def create(self, request, *args, **kwargs):
        """Create a user.

        @api {post} /api/v1/users/
        @apiName createUser
        @apiGroup Users
        @apiVersion 1.0.0
        @apiDescription Create a user.

        @apiHeader {String} token User authorizaton token.
        @apiHeaderExample {json} Header-Example:
            {
                "Authorizaton": "Token 45138a913da44ab89532bab0352ef84b"
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

        @apiSuccess {Number} id The identifier of the user.
        @apiSuccess {String} username  The name of the user.
        @apiSuccess {String} email  The email address of the user.
        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 201 CREATED
            {
                "id": "57e60f90-8c0c-4bd1-87a0-2143759aae1c",
                "username": "smithj",
                "email": "smithj@mytechco.com"
            }
        """
        return super().create(request=request, args=args, kwargs=kwargs)

    def list(self, request, *args, **kwargs):
        """Obtain the list of users.

        @api {get} /api/v1/users/
        @apiName GetUsers
        @apiGroup Users
        @apiVersion 1.0.0
        @apiDescription Obtain the list of users.

        @apiHeader {String} token User authorizaton token.
        @apiHeaderExample {json} Header-Example:
            {
                "Authorizaton": "Token 45138a913da44ab89532bab0352ef84b"
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
                        "id": "57e60f90-8c0c-4bd1-87a0-2143759aae1c",
                        "username": "smithj",
                        "email": "smithj@mytechco.com"
                    }
              ]
            }
        """
        return super().list(request=request, args=args, kwargs=kwargs)

    def retrieve(self, request, *args, **kwargs):
        """Get a user.

        @api {get} /api/v1/user/:id/
        @apiName GetUser
        @apiGroup Users
        @apiVersion 1.0.0
        @apiDescription Get a user.

        @apiHeader {String} token User authorizaton token.
        @apiHeaderExample {json} Header-Example:
            {
                "Authorizaton": "Token 45138a913da44ab89532bab0352ef84b"
            }

        @apiParam {Number} id User unique ID.

        @apiSuccess {Number} id The identifier of the user.
        @apiSuccess {String} username  The name of the user.
        @apiSuccess {String} email  The email address of the user.
        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "id": "57e60f90-8c0c-4bd1-87a0-2143759aae1c",
                "username": "smithj",
                "email": "smithj@mytechco.com"
            }
        """
        return super().retrieve(request=request, args=args, kwargs=kwargs)

    def destroy(self, request, *args, **kwargs):
        """Delete a user.

        @api {delete} /api/v1/user/:id/
        @apiName DeleteUser
        @apiGroup Users
        @apiVersion 1.0.0
        @apiDescription Delete a user.

        @apiHeader {String} token User authorizaton token.
        @apiHeaderExample {json} Header-Example:
            {
                "Authorizaton": "Token 45138a913da44ab89532bab0352ef84b"
            }

        @apiParam {Number} id User unique ID.

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 204 NO CONTENT
        """
        return super().destroy(request=request, args=args, kwargs=kwargs)
