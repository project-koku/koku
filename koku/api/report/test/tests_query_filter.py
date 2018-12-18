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
"""Test the QueryFilter."""

from collections import Iterable

from django.db.models import Q
from django.test import TestCase
from faker import Faker

from api.query_filter import QueryFilter, QueryFilterCollection


class QueryFilterTest(TestCase):
    """Test the QueryFilter class."""

    fake = Faker()

    def test_composed_string_all(self):
        """Test composed_query_string() method using all parameters."""
        table = self.fake.word()
        field = self.fake.word()
        operation = self.fake.word()
        parameter = self.fake.word()
        filt = QueryFilter(table, field, operation, parameter)
        expected = f'{table}__{field}__{operation}'
        self.assertEqual(filt.composed_query_string(), expected)

    def test_composed_string_table_op(self):
        """Test composed_query_string() method using table and operation parameters."""
        table = self.fake.word()
        operation = self.fake.word()
        filt = QueryFilter(table=table, operation=operation)
        expected = f'{table}__{operation}'
        self.assertEqual(filt.composed_query_string(), expected)

    def test_composed_dict_all(self):
        """Test composed_dict() method with all parameters."""
        table = self.fake.word()
        field = self.fake.word()
        operation = self.fake.word()
        parameter = self.fake.word()

        filt = QueryFilter(table, field, operation, parameter)
        expected_dict = {f'{table}__{field}__{operation}': parameter}
        expected = Q(**expected_dict)
        self.assertEqual(filt.composed_Q(), expected)

    def test_composed_dict_field(self):
        """Test composed_dict() method without a Table parameter."""
        field = self.fake.word()
        operation = self.fake.word()
        parameter = self.fake.word()
        filt = QueryFilter(field=field, operation=operation,
                           parameter=parameter)
        expected_dict = {f'{field}__{operation}': parameter}
        expected = Q(**expected_dict)
        self.assertEqual(filt.composed_Q(), expected)

    def test_from_string_all(self):
        """Test from_string() method with all parts."""
        table = self.fake.word()
        field = self.fake.word()
        operation = self.fake.word()
        SEP = QueryFilter.SEP
        test_string = table + SEP + field + SEP + operation
        filt = QueryFilter().from_string(test_string)

        self.assertEqual(filt.table, table)
        self.assertEqual(filt.field, field)
        self.assertEqual(filt.operation, operation)
        self.assertEqual(filt.composed_query_string(), test_string)

    def test_from_string_two_parts(self):
        """Test from_string() method with two parts."""
        table = self.fake.word()
        operation = self.fake.word()
        SEP = QueryFilter.SEP
        test_string = table + SEP + operation
        filt = QueryFilter().from_string(test_string)

        self.assertEqual(filt.table, table)
        self.assertEqual(filt.operation, operation)
        self.assertEqual(filt.composed_query_string(), test_string)

    def test_from_string_wrong_parts_few(self):
        """Test from_string() method with too few parts."""
        test_string = self.fake.word()
        with self.assertRaises(TypeError):
            QueryFilter().from_string(test_string)

    def test_from_string_wrong_parts_more(self):
        """Test from_string() method with too many parts."""
        SEP = QueryFilter.SEP
        test_string = self.fake.word() + SEP + \
            self.fake.word() + SEP + \
            self.fake.word() + SEP + \
            self.fake.word()

        with self.assertRaises(TypeError):
            QueryFilter().from_string(test_string)


class QueryFilterCollectionTest(TestCase):
    """Test the QueryFilterCollection class."""

    fake = Faker()

    def test_constructor(self):
        """Test the constructor using valid QueryFilter instances."""
        filters = []
        for _ in range(0, 3):
            filt = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                               operation=self.fake.word(), parameter=self.fake.word())
            filters.append(filt)
        qf_coll = QueryFilterCollection(filters)
        self.assertEqual(qf_coll._filters, filters)

    def test_constructor_bad_type(self):
        """Test the constructor using an invalid object type."""
        with self.assertRaises(TypeError):
            QueryFilterCollection(dict())

    def test_constructor_bad_elements(self):
        """Test the constructor using invalid values."""
        bad_list = [self.fake.word(), self.fake.word()]

        with self.assertRaises(TypeError):
            QueryFilterCollection(bad_list)

    def test_add_filter(self):
        """Test the add() method using a QueryFilter instance."""
        filters = []
        qf_coll = QueryFilterCollection()
        for _ in range(0, 3):
            filt = QueryFilter(self.fake.word(), self.fake.word(),
                               self.fake.word(), self.fake.word())
            filters.append(filt)
            qf_coll.add(query_filter=filt)
        self.assertEqual(qf_coll._filters, filters)

    def test_add_params(self):
        """Test the add() method using parameters."""
        table = self.fake.word()
        field = self.fake.word()
        operation = self.fake.word()
        parameter = self.fake.word()
        filt = QueryFilter(table=table, field=field, operation=operation,
                           parameter=parameter)
        qf_coll = QueryFilterCollection()
        qf_coll.add(table=table, field=field, operation=operation,
                    parameter=parameter)
        self.assertEqual(qf_coll._filters[0], filt)

    def test_add_bad(self):
        """Test the add() method using invalid values."""
        qf_coll = QueryFilterCollection()

        with self.assertRaises(AttributeError):
            qf_coll.add(self.fake.word(), self.fake.word(), self.fake.word())

    def test_compose(self):
        """Test the compose() method."""
        qf_coll = QueryFilterCollection()
        table = self.fake.word()
        field = self.fake.word()
        operation = self.fake.word()
        parameter = self.fake.word()
        filt = QueryFilter(table=table, field=field, operation=operation,
                           parameter=parameter)
        expected = filt.composed_Q()
        qf_coll.add(table=table, field=field, operation=operation, parameter=parameter)
        self.assertEqual(qf_coll.compose(), expected)

    def test_contains_with_filter(self):
        """Test the __contains__() method using a QueryFilter."""
        qf = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                         parameter=self.fake.word())
        qf_coll = QueryFilterCollection([qf])
        self.assertIn(qf, qf_coll)

    def test_contains_with_dict(self):
        """Test the __contains__() method using a dict to get a fuzzy match."""
        table = self.fake.word()
        field = self.fake.word()
        operation = self.fake.word()
        parameter = self.fake.word()
        qf = QueryFilter(table=table, field=field, operation=operation,
                         parameter=parameter)
        qf_coll = QueryFilterCollection([qf])
        self.assertIn({'table': table, 'parameter': parameter}, qf_coll)

    def test_contains_fail(self):
        """Test the __contains__() method fails with a non-matching filter."""
        qf1 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf2 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf_coll = QueryFilterCollection([qf1])
        self.assertNotIn(qf2, qf_coll)
        self.assertFalse(qf2 in qf_coll)

    def test_delete_filter(self):
        """Test the delete() method works with QueryFilters."""
        qf1 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf2 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf_coll = QueryFilterCollection([qf1, qf2])

        qf_coll.delete(qf1)
        self.assertEqual([qf2], qf_coll._filters)
        self.assertNotIn(qf1, qf_coll)

    def test_delete_fail(self):
        """Test the delete() method works with QueryFilters."""
        qf1 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf2 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf_coll = QueryFilterCollection([qf1, qf2])

        q_dict = {'table': self.fake.word(),
                  'field': self.fake.word(),
                  'parameter': self.fake.word()}

        with self.assertRaises(AttributeError):
            qf_coll.delete(qf1, **q_dict)

    def test_delete_params(self):
        """Test the delete() method works with parameters."""
        qf1 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf2 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf_coll = QueryFilterCollection([qf1, qf2])

        qf_coll.delete(table=qf1.table, field=qf1.field,
                       parameter=qf1.parameter)
        self.assertEqual([qf2], qf_coll._filters)
        self.assertNotIn(qf1, qf_coll)

    def test_get_fail(self):
        """Test the get() method fails when no match is found."""
        qf1 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf2 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf_coll = QueryFilterCollection([qf1, qf2])

        response = qf_coll.get({'table': self.fake.word(),
                                'field': self.fake.word(),
                                'parameter': self.fake.word()})
        self.assertIsNone(response)

    def test_iterable(self):
        """Test the __iter__() method returns an iterable."""
        qf1 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf2 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf_coll = QueryFilterCollection([qf1, qf2])

        self.assertIsInstance(qf_coll.__iter__(), Iterable)

    def test_indexing(self):
        """Test that __getitem__() allows array slicing."""
        qf1 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf2 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf_coll = QueryFilterCollection([qf1, qf2])

        self.assertEqual(qf_coll[0], qf1)
        self.assertEqual(qf_coll[1], qf2)
        self.assertEqual(qf_coll[-1], qf2)
        self.assertEqual(qf_coll[-2], qf1)
