# Contributing to Koku

Thank you for your interest in contributing to this project!

The following are a set of guidelines for contributing to Koku. These are guidelines, not rules. Use your best judgement. Feel free to suggest changes to this document in a pull-request.

This document uses [RFC 2119](https://www.ietf.org/rfc/rfc2119.txt/) keywords to indicate requirement levels.

## Reporting Bugs & Requesting Features

We use Github Issues to track bug reports and feature requests.

When submitting a bug report, please be as detailed as possible. Include as much of these items as you have:

> 1.  steps to reproduce the bug
> 2.  error messages with stacktraces
> 3.  logs
> 4.  any relevant configuration settings
> 5.  environment details

When submitting a feature request, please submit them in the form of a user story with acceptance criteria:

> As a \[user\], I want \[a thing\], So that \[some goal\].
>
> When complete, I will be able to:
>
> 1.  \[do this\]
> 2.  \[do that\]
> 3.  \[do another\]

## Contributing Code (Pull Requests)

All code contributions MUST come in the form of a pull-request. Pull-requests will be reviewed for a variety of criteria. This section attempts to capture as much of that criteria as possible.

### Certificate of Origin

By contributing to this project you agree to the Developer Certificate of Origin (DCO). This document was created by the Linux Kernel community and is a simple statement that you, as a contributor, have the legal right to make the contribution. See the [DCO](DCO) file for details.

## Readability and Style considerations

In general, we believe that code is read just as much as it is executed. So, writing readable code is just as important as writing functional code.

Pull-requests MUST follow Python style conventions (e.g. [PEP 8](https://peps.python.org/pep-0008/) and [PEP 20](https://www.python.org/dev/peps/pep-0020/)) and conform to generally recognized best practices. Pull-requests MAY also choose to conform to additional style guidelines, e.g. [Google's Python Style Guide](https://google.github.io/styleguide/pyguide.html).

We do use automation whenever possible to ensure a basic level of acceptability. Pull-requests MUST pass a linter (flake8) without errors.

We do recognize that sometimes linters can get things wrong. They are useful tools, but they are not perfect tools. Pull-requests SHOULD pass a linter without warnings.

Pull-requests MAY include disabling a specific linter check. If your pull-request disables linting it MUST include a comment block detailing why that particular check was disabled and it MUST be scoped as narrowly as possible. i.e. Don\'t disable linting on an entire class or method when disabling the check for a single statement will do.

This repository uses [pre-commit](https://pre-commit.com/) to check and enforce code style. It uses [Black](https://github.com/psf/black/) to reformat the Python code and [Flake8](http://flake8.pycqa.org/) to check it afterwards. Other formats and text files are linted as well.

Install pre-commit hooks to your local repository by running:

    $ pre-commit install

After that, all your commited files will be linted. If the checks don't succeed, the commit will be rejected. Please make sure all checks pass before submitting a pull request.

## Code testing considerations

We believe that well-tested code is a critical component to every successful project. For this reason, all pull-requests MUST include unit test cases and those unit tests MUST pass when run.

The unit tests SHOULD cover all of the code in the pull-request. Our goal is to maintain at least 90% test coverage.

In general, the test cases SHOULD cover both success and failure conditions.

An attempt SHOULD be made to cover all code branches. You SHOULD also attempt to include tests for all class and method parameters. e.g. If a method accepts a boolean, there should be tests for when that boolean is True, False, and None.
