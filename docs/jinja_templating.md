# Jinja

Our project uses [Jinja](https://jinja.palletsprojects.com/en/3.0.x/api/) and [JinjaSQL](https://github.com/sripathikrishnan/jinjasql) to template our sql commands.

However, there is some additional nuances to consider when using jinja conditionals combined with the `_execute_trino_multipart_sql_query` method. The multipart method parses the query string and runs each query statement individually in Trino.

For example, if I were to run my `example.sql` below both queries would be run individually within Trino and the results would be compiled.

```
 % cat example.sql
select * from {{schema | sqlsafe}}.azure_line_items;
select * from {{schema | sqlsafe}}.azure_openshift_daily;
```

We achieve this behavior by looping over the results of the `sqlparse` package in the `executescript` function in [trino_database.py](https://github.com/project-koku/koku/blob/main/koku/koku/trino_database.py).

The `sqlparse` package splits the query string up using a semicolon as the deliminator. Each query is then templated through the JinjaSQL preprocessor passed into the function:
```
stmt, s_params = preprocessor(p_stmt, params)
```

Which works fine for simple variable replacement. However, if you want to do something more complex like prevent a section of sql from running unless a feature flag is enable.

```
select * from {{schema | sqlsafe}}.azure_line_items;
select * from {{schema | sqlsafe}}.azure_openshift_daily;
{% if feature_enabled %}
INSERT INTO employees (id, name, email)
VALUES (1, 'John Doe', 'john.doe@example.com');
{% endif %}
```

The `sqlparse` package will return the following because the deliminator comes before the endif jinja tag.
```
{% if feature_enabled %}
INSERT INTO employees (id, name, email)
VALUES (1, 'John Doe', 'john.doe@example.com');
```
Then when we try to JinjaSQL to render the query you get the following error:
```
Jinja was looking for the following tags: 'elif' or 'else' or 'endif'.
```

Therefore, when templating sql executed by the `_execute_trino_multipart_sql_query` method you must include the semicolon after the `{% endif %}` command.

Example:
```
select * from {{schema | sqlsafe}}.azure_line_items;
select * from {{schema | sqlsafe}}.azure_openshift_daily;
{% if feature_enabled %}
INSERT INTO employees (id, name, email)
VALUES (1, 'John Doe', 'john.doe@example.com')
{% endif %}
;
```

If the `feature_enable` jinja variable is False and empty string will be returned; however, we have checked for an empty string and will not attempt to an execute the query inside of the `executescript` function.
