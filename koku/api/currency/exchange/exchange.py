#
# Copyright 2021 Red Hat, Inc.
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
"""Exchange rates functions."""
import random

from api.currency.models import CurrencyCodes, ExchangeRate

def create_currency_codes(): 
    """Try this"""
    for currency in CurrencyCodes.SUPPORTED_CURRENCIES:
        try: 
            currencyCode = CurrencyCodes.objects.get(name=currency)
        except CurrencyCodes.DoesNotExist: 
            currencyCode = CurrencyCodes(name=currency)
            currencyCode.save()

def populate_exchange_rates():
    """Grab the exchange rates from external api"""
    print("\n\n\n\nASHLEY LOOK HERE!")
    print(CurrencyCodes.SUPPORTED_CURRENCIES)
    create_currency_codes()
    for currency in CurrencyCodes.SUPPORTED_CURRENCIES:
        og = currency[1]
        starting = CurrencyCodes.objects.get(name=currency)
        for paired_currency in CurrencyCodes.SUPPORTED_CURRENCIES:
            ending = CurrencyCodes.objects.get(name=paired_currency)
            transform_to = paired_currency[1]
            print("\nThe pairing is: ")
            print(og)
            print(transform_to)
            try: 
                exchange = ExchangeRate.objects.get(startingCurrency=starting, endingCurrency=ending)
            except ExchangeRate.DoesNotExist:
                exchange = ExchangeRate(startingCurrency=starting, endingCurrency=ending)
            # exchange.startingCurrency = starting
            # exchange.endingCurrency = ending
            ### RIGHT HERE IS WHERE WE NEED TO QUERY AN EXTERNAL API 
            er = random.random()
            print(er)
            exchange.exchangeRate = er
            exchange.save()
