#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Accessor for Customer information from koku database."""
import logging

from django.db import transaction
from django.db.models import Subquery
from django_tenants.utils import schema_context

from masu.config import Config


LOG = logging.getLogger(__name__)


class KokuDBAccess:
    """Base Class to connect to the koku database.

    Subclass of Django Atomic class to make use of atomic transactions
    with a schema/tenant context.
    """

    def __init__(self, schema_name):
        """
        Establish database connection.

        Args:
            schema_name   (String) database schema (i.e. public or customer tenant value)

        """
        self.schema_name = schema_name

    def __enter__(self):
        """Enter context manager."""
        connection = transaction.get_connection()
        connection.set_schema(self.schema_name)
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        """Context manager reset schema to public and exit."""
        connection = transaction.get_connection()
        connection.set_schema_to_public()

    def _get_db_obj_query(self, **filter_args):
        """
        Return the django queryset for this table .

        Args:
            None
        Returns:
            (django.db.query.QuerySet): QuerySet of objects matching the given filters

        """
        with schema_context(self.schema_name):
            queryset = self._table.objects.all()
            if filter_args:
                queryset = queryset.filter(**filter_args)
            return queryset

    def does_db_entry_exist(self):
        """
        Return status for the existence of an object in the database.

        Args:
            None
        Returns:
            (Boolean): "True/False",

        """
        with schema_context(self.schema_name):
            return self._get_db_obj_query().exists()

    def add(self, **kwargs):
        """
        Add a new row to this table.

        Args:
            kwargs (Dictionary): Fields containing table attributes.

        Returns:
            (Object): new model object

        """
        with schema_context(self.schema_name):
            new_entry, _ = self._table.objects.get_or_create(**kwargs)
            new_entry.save()
            return new_entry

    def delete(self, obj=None):
        """
        Delete our object from the database.

        Args:
            obj (object) model object to delete
        Returns:
            None

        """
        if obj:
            deleteme = obj
        else:
            deleteme = self._obj
        with schema_context(self.schema_name):
            deleteme.delete()


def mtd_check_remainder(base_select_query):
    return base_select_query.count()


def mini_transaction_delete(base_select_query):
    """
    Uses a select query to make a mini transactinal delete loop.
    Schema should be set before calling this function.
    Args:
        base_select_query (QuerySet) : Single-table django select query
    Returns:
        tuple : (deleted_record_total, records_remaining)
    """
    # Change the base query into a SELECT ... FOR UPDATE SKIP LOCKED query
    delete_subquery = base_select_query.select_for_update(skip_locked=True).values_list("pk")
    # Remove any ordering
    base_select_query.query.clear_ordering(True)
    delete_subquery.query.clear_ordering(True)
    # Use the line_item_query as a subquery with a LIMIT clause
    delete_query = delete_subquery.model.objects.filter(pk__in=Subquery(delete_subquery[: Config.DEL_RECORD_LIMIT]))
    # Remove any ordering
    delete_query.query.clear_ordering(True)

    iterations = 0
    del_total = 0
    remainder = 0
    while iterations < Config.MAX_ITERATIONS:
        del_count = -1
        while del_count != 0:
            # The use of FOR UPDATE demands a transaction!
            with transaction.atomic():
                del_count = delete_query.delete()[0]
            del_total += del_count

        remainder = mtd_check_remainder(base_select_query)
        if remainder > 0:
            iterations += 1
        else:
            break

    LOG.debug(f"Removed {del_total} records")

    if (iterations >= Config.MAX_ITERATIONS) and (remainder > 0):
        LOG.warning(f"Due to possible lock contention, there are {remainder} records remaining.")

    return (del_total, remainder)
