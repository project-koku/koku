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
"""Test the tag view."""
import datetime
from unittest.mock import patch
from urllib.parse import quote_plus, urlencode

from dateutil import relativedelta
from django.db.models import Count, F, Sum
from django.http import HttpRequest, QueryDict
from django.urls import reverse
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIClient
from tenant_schemas.utils import tenant_context

from api.iam.serializers import UserSerializer
from api.iam.test.iam_test_case import IamTestCase
from api.models import User
from api.query_handler import TruncDayString
from api.report.aws.serializers import QueryParamSerializer
from api.tags.ocp.serializers import OCPTagsQueryParamSerializer
from api.report.ocp.ocp_query_handler import OCPReportQueryHandler
from api.report.test.ocp.helpers import OCPReportDataGenerator
from api.report.view import _generic_report
from api.utils import DateHelper
from reporting.models import OCPUsageLineItemDailySummary


class OCPReportViewTest(IamTestCase):
    """Tests the report view."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        cls.dh = DateHelper()

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.data_generator = OCPReportDataGenerator(self.tenant)
        self.data_generator.add_data_to_tenant()
        serializer = UserSerializer(data=self.user_data, context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            serializer.save()

        self.tag_ocp = {
            "filter": {
                "resolution": "monthly",
                "time_scope_value": "-1",
                "time_scope_units": "month"
            },
            "data": [
                "Democrat",
                "PM",
                "actually",
                "add",
                "admit",
                "adult",
                "again",
                "age",
                "agent",
                "always",
                "among",
                "answer",
                "app",
                "apply",
                "area",
                "argue",
                "as",
                "attorney",
                "authority",
                "away",
                "bank",
                "be",
                "beat",
                "because",
                "behavior",
                "best",
                "beyond",
                "bit",
                "body",
                "box",
                "build",
                "business",
                "by",
                "can",
                "care",
                "carry",
                "catch",
                "cell",
                "chair",
                "child",
                "choose",
                "civil",
                "clear",
                "coach",
                "college",
                "compare",
                "concern",
                "condition",
                "consider",
                "create",
                "culture",
                "customer",
                "decide",
                "degree",
                "design",
                "develop",
                "difficult",
                "discussion",
                "do",
                "dream",
                "drive",
                "drug",
                "east",
                "economic",
                "economy",
                "edge",
                "else",
                "employee",
                "energy",
                "enter",
                "entire",
                "environment",
                "establish",
                "evening",
                "event",
                "executive",
                "few",
                "field",
                "fill",
                "financial",
                "firm",
                "floor",
                "fly",
                "foreign",
                "free",
                "fund",
                "general",
                "generation",
                "get",
                "glass",
                "goal",
                "good",
                "ground",
                "guess",
                "hair",
                "hear",
                "heart",
                "help",
                "herself",
                "history",
                "human",
                "husband",
                "idea",
                "image",
                "impact",
                "improve",
                "indicate",
                "instead",
                "institution",
                "its",
                "job",
                "keep",
                "last",
                "lawyer",
                "letter",
                "listen",
                "loss",
                "lot",
                "low",
                "magazine",
                "main",
                "make",
                "management",
                "manager",
                "market",
                "marriage",
                "material",
                "matter",
                "may",
                "meeting",
                "mention",
                "military",
                "miss",
                "modern",
                "morning",
                "most",
                "mouth",
                "much",
                "music",
                "near",
                "need",
                "nothing",
                "notice",
                "officer",
                "official",
                "often",
                "ok",
                "organization",
                "painting",
                "party",
                "people",
                "per",
                "phone",
                "pick",
                "politics",
                "population",
                "production",
                "project",
                "property",
                "question",
                "ready",
                "reality",
                "realize",
                "receive",
                "recognize",
                "record",
                "reflect",
                "remain",
                "require",
                "respond",
                "responsibility",
                "reveal",
                "rise",
                "risk",
                "rock",
                "safe",
                "score",
                "sea",
                "section",
                "security",
                "send",
                "shake",
                "she",
                "similar",
                "since",
                "sister",
                "size",
                "skin",
                "so",
                "some",
                "somebody",
                "speech",
                "spend",
                "spring",
                "stay",
                "step",
                "store",
                "strategy",
                "student",
                "stuff",
                "subject",
                "summer",
                "sure",
                "take",
                "talk",
                "tax",
                "teach",
                "tell",
                "ten",
                "than",
                "them",
                "themselves",
                "thing",
                "third",
                "though",
                "thought",
                "together",
                "tonight",
                "tree",
                "true",
                "try",
                "us",
                "use",
                "version",
                "visit",
                "wait",
                "walk",
                "water",
                "way",
                "we",
                "western",
                "when",
                "which",
                "white",
                "whose",
                "will",
                "wind",
                "yard",
                "yeah",
                "yet"
            ]
        }

    def test_execute_query_ocp_tags_this_month(self):
        """Test that tag data is returned for the full month."""
        url = reverse('ocp-tags')
        client = APIClient()
        params = {
            'filter[resolution]': 'monthly',
            'filter[time_scope_value]': '-1',
            'filter[time_scope_units]': 'month'
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('data'))
        self.assertTrue(isinstance(data.get('data'), list))
