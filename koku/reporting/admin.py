#
# Copyright 2018 Red Hat, Inc.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Admin module for Django server application."""

from django.contrib import admin

from reporting.models import (AWSAccountAlias,
                              AWSCostEntry,
                              AWSCostEntryBill,
                              AWSCostEntryLineItem,
                              AWSCostEntryPricing,
                              AWSCostEntryProduct,
                              AWSCostEntryReservation,
                              CostSummary)

admin.site.register(AWSAccountAlias)
admin.site.register(AWSCostEntry)
admin.site.register(AWSCostEntryBill)
admin.site.register(AWSCostEntryLineItem)
admin.site.register(AWSCostEntryPricing)
admin.site.register(AWSCostEntryProduct)
admin.site.register(AWSCostEntryReservation)
admin.site.register(CostSummary)
