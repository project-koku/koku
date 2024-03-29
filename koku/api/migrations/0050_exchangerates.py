# Generated by Django 3.1.13 on 2021-10-07 16:36
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [("api", "0049_auto_20210818_2208")]

    operations = [
        migrations.CreateModel(
            name="ExchangeRates",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "currency_type",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("aud", "AUD"),
                            ("cad", "CAD"),
                            ("chf", "CHF"),
                            ("cny", "CNY"),
                            ("dkk", "DKK"),
                            ("eur", "EUR"),
                            ("gbp", "GBP"),
                            ("hkd", "HKD"),
                            ("jpy", "JPY"),
                            ("nok", "NOK"),
                            ("nzd", "NZD"),
                            ("sek", "SEK"),
                            ("sgd", "SGD"),
                            ("usd", "USD"),
                            ("zar", "ZAR"),
                        ],
                        max_length=5,
                    ),
                ),
                ("exchange_rate", models.FloatField(default=0)),
            ],
        )
    ]
