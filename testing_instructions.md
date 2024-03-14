1. Create some tag mappings

```
http://localhost:8000/api/cost-management/v1/settings/tags/mappings/child/add/
```

```
{
    "parent": "49829a25-13e8-442e-bb6a-aa5449c4714b",
    "children": ["f6a04487-9287-4292-8f44-434d9ab3e65a"]
}
```

2. Check if you can do multiple filters.

*Tag Mapping*

Parent Key
```
http://localhost:8000/api/cost-management/v1/settings/tags/mappings/?filter[parent]=i&filter[parent]=p
```
Example Return:
```
{
    "meta": {
        "count": 3,
        "limit": 3,
        "offset": 0
    },
    "links": {
        "first": "/api/cost-management/v1/settings/tags/mappings/?filter%5Bparent%5D=i&filter%5Bparent%5D=p&limit=3&offset=0",
        "next": null,
        "previous": null,
        "last": "/api/cost-management/v1/settings/tags/mappings/?filter%5Bparent%5D=i&filter%5Bparent%5D=p&limit=3&offset=0"
    },
    "data": [
        {
            "parent": {
                "uuid": "23af1240-03f4-4a07-9b53-351836380ae2",
                "key": "Mapping",
                "source_type": "AWS",
                "children": [
                    {
                        "uuid": "97982dc7-e412-494a-b995-2acf95aab118",
                        "key": "dashed-key-on-aws",
                        "source_type": "AWS"
                    },
                    {
                        "uuid": "7a40eee0-f188-408c-92dc-dc672b6618cb",
                        "key": "environment",
                        "source_type": "AWS"
                    }
                ]
            }
        },
        {
            "parent": {
                "uuid": "49829a25-13e8-442e-bb6a-aa5449c4714b",
                "key": "app",
                "source_type": "AWS",
                "children": [
                    {
                        "uuid": "f6a04487-9287-4292-8f44-434d9ab3e65a",
                        "key": "CoM_RedHat_Rhel_varianT",
                        "source_type": "AWS"
                    }
                ]
            }
        }
    ]
}
```

Child Key
```
http://localhost:8000/api/cost-management/v1/settings/tags/mappings/?filter[child]=k&filter[child]=v
```
Example Return:
```
{
    "meta": {
        "count": 3,
        "limit": 3,
        "offset": 0
    },
    "links": {
        "first": "/api/cost-management/v1/settings/tags/mappings/?filter%5Bchild%5D=k&filter%5Bchild%5D=v&limit=3&offset=0",
        "next": null,
        "previous": null,
        "last": "/api/cost-management/v1/settings/tags/mappings/?filter%5Bchild%5D=k&filter%5Bchild%5D=v&limit=3&offset=0"
    },
    "data": [
        {
            "parent": {
                "uuid": "23af1240-03f4-4a07-9b53-351836380ae2",
                "key": "Mapping",
                "source_type": "AWS",
                "children": [
                    {
                        "uuid": "97982dc7-e412-494a-b995-2acf95aab118",
                        "key": "dashed-key-on-aws",
                        "source_type": "AWS"
                    },
                    {
                        "uuid": "7a40eee0-f188-408c-92dc-dc672b6618cb",
                        "key": "environment",
                        "source_type": "AWS"
                    }
                ]
            }
        },
        {
            "parent": {
                "uuid": "49829a25-13e8-442e-bb6a-aa5449c4714b",
                "key": "app",
                "source_type": "AWS",
                "children": [
                    {
                        "uuid": "f6a04487-9287-4292-8f44-434d9ab3e65a",
                        "key": "CoM_RedHat_Rhel_varianT",
                        "source_type": "AWS"
                    }
                ]
            }
        }
    ]
}
```

Source Type
```
http://localhost:8000/api/cost-management/v1/settings/tags/mappings/?filter[source_type]=AWS&filter[source_type]=OCP
```
Return
```
{
    "meta": {
        "count": 3,
        "limit": 3,
        "offset": 0
    },
    "links": {
        "first": "/api/cost-management/v1/settings/tags/mappings/?filter%5Bsource_type%5D=AWS&filter%5Bsource_type%5D=OCP&limit=3&offset=0",
        "next": null,
        "previous": null,
        "last": "/api/cost-management/v1/settings/tags/mappings/?filter%5Bsource_type%5D=AWS&filter%5Bsource_type%5D=OCP&limit=3&offset=0"
    },
    "data": [
        {
            "parent": {
                "uuid": "23af1240-03f4-4a07-9b53-351836380ae2",
                "key": "Mapping",
                "source_type": "AWS",
                "children": [
                    {
                        "uuid": "97982dc7-e412-494a-b995-2acf95aab118",
                        "key": "dashed-key-on-aws",
                        "source_type": "AWS"
                    },
                    {
                        "uuid": "7a40eee0-f188-408c-92dc-dc672b6618cb",
                        "key": "environment",
                        "source_type": "AWS"
                    }
                ]
            }
        },
        {
            "parent": {
                "uuid": "49829a25-13e8-442e-bb6a-aa5449c4714b",
                "key": "app",
                "source_type": "AWS",
                "children": [
                    {
                        "uuid": "f6a04487-9287-4292-8f44-434d9ab3e65a",
                        "key": "CoM_RedHat_Rhel_varianT",
                        "source_type": "AWS"
                    }
                ]
            }
        }
    ]
}
```

Parent Endpoint
Source type:
```
http://localhost:8000/api/cost-management/v1/settings/tags/mappings/parent/?limit=100&filter[source_type]=AwS&filter[source_type]=OCp
```
Key:
```
http://localhost:8000/api/cost-management/v1/settings/tags/mappings/parent/?limit=100&filter[key]=app&filter[key]=e
```

Child Endpoint
key:
```
http://localhost:8000/api/cost-management/v1/settings/tags/mappings/child/?filter[key]=app&filter[key]=e
```
source type:
```
http://localhost:8000/api/cost-management/v1/settings/tags/mappings/child/?filter[source_type]=AWS&filter[source_type]=OCP
```
