# RBAC

RBAC stands for Role Based Access Control and it is a [repository](https://github.com/RedHatInsights/rbac-config) maintained by the Insights team, and it contains decoupled RBAC service roles and permission configs that are seeded into each tenant or account.

## Koku
Koku reads the information seeded in the tenant or account at the time of the request to decide if the user has access to the view. We accomplish this by creating [permission classes](https://github.com/project-koku/koku/tree/main/koku/api/common/permissions) that return a simple boolean value that indicates if the user has access to the page. These classes are attached to the views, for example `AwsAccessPermission` in the following code snippet:

```
class AWSAccountRegionView(generics.ListAPIView):
    """API GET list view for AWS by region"""

    queryset = (
        AWSCostSummaryByRegionP.objects.annotate(**{"value": F("region")})
        .values("value")
        .distinct()
        .filter(region__isnull=False)
    )
    serializer_class = ResourceTypeSerializer
    permission_classes = [AwsAccessPermission]
```

### Testing RBAC Access Locally
The `.env` contains the variable `DEVELOPMENT_IDENTITY` which mocks the identitiy information that would be sent with the request from the Insights Platform team.

Admin Example:
```
DEVELOPMENT_IDENTITY='{"identity": {"account_number": "10001", "org_id": "1234567", "type": "User", "user": {"username": "user_dev", "email": "user_dev@foo.com", "is_org_admin": "True", "access": {}}},"entitlements": {"cost_management": {"is_entitled": "True"}}}'
```

Limited User Example:
```
DEVELOPMENT_IDENTITY='{"identity": {"account_number": "10001", "type": "User", "user": {"username": "user_dev", "email": "user_dev@foo.com", "access": {"aws.account": {"read": ["111111111111", "9999999999990", "9999999999990"]}, "aws.organizational_unit": {"read": ["*"]}}}}, "entitlements": {"cost_management": {"is_entitled": "True"}}}'
```
Note: The access key's dictionary will contain "resource_types" defined in our permission classes above.

Additionally, we have a user_access endpoint that can help identify your access level:
- http://localhost:8000/api/cost-management/v1/user-access/


### Write Provides an Implicit Read
- We have some additional logic that runs in our stage/prod environment that can be found in the [rbac.py](https://github.com/project-koku/koku/blob/main/koku/koku/rbac.py#L111-L113) file that ensures that those who have write access are also provided an implict READ. It is inside of the `_update_access_obj` method:
```
if operation == "write" and res_access[res].get("write") is not None:
    res_access[res]["write"] += res_list
    res_access[res]["read"] += res_list
```

## How to create or edit roles in RBAC config
1. The first step is to modifiy the [permissions file](https://github.com/RedHatInsights/rbac-config/blob/master/configs/stage/permissions/cost-management.json) for cost management:

```
"cost_model": [
        {
            "verb": "*"
        },
        {
            "verb": "read"
        },
        {
            "verb": "write"
        }
    ],
```

2. Then the name of your permission will need to be added to the corresponding role in stage and prod:
```
{
        "name": "Cost Price List Administrator",
        "description": "A cost management role that grants read and write permissions on cost models.",
        "system": true,
        "version": 3,
        "access": [{
            "permission": "cost-management:cost_model:*"
        }]
    }
```
*Note:* When you update this file you will need to uptick the version.


[Example](https://github.com/RedHatInsights/rbac-config/commit/fc301f54ebea5ee9538d319973cda95c45a7e505)
