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

from api.models import (Customer,
                        Provider,
                        ProviderAuthentication,
                        ProviderBillingSource,
                        ResetToken,
                        Status,
                        User,
                        UserPreference)

admin.site.register(Customer)
admin.site.register(Provider)
admin.site.register(ProviderAuthentication)
admin.site.register(ProviderBillingSource)
admin.site.register(ResetToken)
admin.site.register(Status)
admin.site.register(User)
admin.site.register(UserPreference)
