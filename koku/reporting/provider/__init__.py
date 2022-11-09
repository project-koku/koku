# noqa
from django.db.models import Field
from django.db.models import Lookup


# Custom Django Lookups
@Field.register_lookup
class AllowNullIcontains(Lookup):
    """
    This custom lookup accepts a list as the param wne will create
    a NOT LIKE with an 'AND' between each element in the list.
    Currently exclusively beinng used for tag exclusions.
    """

    lookup_name = "notlikelist"
    prepare_rhs = False

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        formatted_sql = []
        lhs = lhs.replace("->", "->>")  # the lhs_param is returning it as a json object, but I need it as text.
        params = tuple()
        for rhs_param in rhs_params:
            for exclude in rhs_param:
                format_exclude = f"%{exclude}%"
                params = params + lhs_params + (format_exclude,)
                the_format = f"(UPPER({lhs}::text) NOT LIKE UPPER({rhs}))"
                formatted_sql.append(the_format)
        final_format = " AND ".join(formatted_sql), params
        return final_format

    # COST-3199: no-{option} disappears with exclude functionality
    # When we use .exclude(self.query_exclusions) the django
    # optimizer was adding an `IS NOT NULL` to the query it runs
    # which was removing the no-{option}.

    # Part of the reason django does this is to handle the tri-value
    # logic where NULL equates to UNKNOWN. So, NOT UNKNOWN is still
    # UNKNOWN.
