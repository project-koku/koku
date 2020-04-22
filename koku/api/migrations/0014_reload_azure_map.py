import json
import pkgutil

import django.contrib.postgres.fields.jsonb
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [("api", "0013_auto_20200226_1953")]

    operations = []
