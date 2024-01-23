from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.request import Request

from api.common.pagination import ListPaginator
from api.common.permissions.settings_access import SettingsAccessPermission
from reporting.provider.all.models import TagMapping
from rest_framework.response import Response
from .serializers import TagMappingSerializer
from rest_framework.views import APIView
from rest_framework import status


# from reporting.provider.all.models import ChildTagKeys
# from reporting.provider.all.models import EnabledTagKeys


class SettingsTagMappingView(generics.GenericAPIView):
    queryset = TagMapping.objects.all()
    # needed to change to this serializer because the first was raising an error
    serializer_class = TagMappingSerializer
    permission_classes = (SettingsAccessPermission,)
    filter_backends = (DjangoFilterBackend,)

    @method_decorator(never_cache)
    def get(self, request: Request, **kwargs):
        filtered_qset = self.filter_queryset(self.get_queryset())
        serializer = self.serializer_class(filtered_qset, many=True)

        paginator = ListPaginator(serializer.data, request)
        response = paginator.paginated_response

        return response


class SettingsTagMappingChildAddView(APIView):
    permission_classes = (SettingsAccessPermission,)
    serializer_class = TagMappingSerializer

    def put(self, request):
        try:
            uuid = request.data.get('uuid')
            if uuid:
                tag_mapping = TagMapping.objects.get(uuid=uuid)
                serializer = TagMappingSerializer(tag_mapping, data=request.data)
            else:
                serializer = TagMappingSerializer(data=request.data)

            serializer.is_valid(raise_exception=True)
            serializer.save()

            return Response(serializer.data, status=status.HTTP_200_OK)

        except TagMapping.DoesNotExist:
            return Response({"detail": "TagMapping not found."}, status=status.HTTP_404_NOT_FOUND)
