from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import TagMappingSerializer
from api.common.pagination import ListPaginator
from api.common.permissions.settings_access import SettingsAccessPermission
from reporting.provider.all.models import TagMapping


class SettingsTagMappingView(generics.GenericAPIView):
    queryset = TagMapping.objects.all()
    serializer_class = TagMappingSerializer
    permission_classes = (SettingsAccessPermission,)
    filter_backends = (DjangoFilterBackend,)

    @method_decorator(never_cache)
    def get(self, request: Request, **kwargs):
        filtered_qset = self.filter_queryset(self.get_queryset())
        serializer = self.serializer_class(filtered_qset, many=True)

        paginator = ListPaginator(serializer.data, request)
        response = paginator.paginated_response

        # (FIXME): Lucas
        # This return structure doesn't currently match what we told
        # Dan we would return in our api doc.

        # data": [
        #     {
        #         "parent": "b02c8a2b-b0d7-493b-a85a-190e81ed1623",
        #         "child": "fbaf9863-6168-428e-812a-d0f1feab8eb6"
        #     }
        # ]

        return response


class SettingsTagMappingChildAddView(APIView):
    permission_classes = (SettingsAccessPermission,)
    serializer_class = TagMappingSerializer

    def put(self, request):
        try:
            uuid = request.data.get("uuid")
            if uuid:
                tag_mapping = TagMapping.objects.get(uuid=uuid)
                # FIXME: Lucas
                # Our api spec document says that the data needs to accept a list of children
                # Also, it is likely that dan will be sending us a list of strings.
                # Example payload
                # dat ={"parent":"uuid_str","child":["uuid_str"]}
                serializer = TagMappingSerializer(tag_mapping, data=request.data)
            else:
                serializer = TagMappingSerializer(data=request.data)

            serializer.is_valid(raise_exception=True)
            serializer.save()

            return Response(serializer.data, status=status.HTTP_200_OK)

        except TagMapping.DoesNotExist:
            return Response({"detail": "TagMapping not found."}, status=status.HTTP_404_NOT_FOUND)
