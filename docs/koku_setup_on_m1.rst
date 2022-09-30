=====================
Koku Setup on M1 Mac
=====================

About
-----

This documentation is to guide M1 Mac users on how to successfully install and run Koku on their machines.

Generally, in order to run Intel-based packages and programs on Mac with Apple silicon processors (M1), one can make `use of Rosetta`_ which emulates the Intel environment.

However, as for running Koku on M1 Macs we can follow the general development documentation with a few modifications as shown below.

Developing with Docker
^^^^^^^^^^^^^^^^^^^^^^

If you want to run the project in Docker environment, follow the below steps:

1. Set ``compose_file`` in your ``.env`` file to point to docker-compose-m1.yml_ file specially created for M1 Mac: ::

    compose_file='testing/compose_files/docker-compose-m1.yml'

2. docker-compose-m1.yml_ removes the use of ``watchdog`` package as at the time of creating this documentation, `watchdog` package is not supported on M1.
   Instead, we use a VSCode extension to run a `bash script`_ on Save in order to re-build docker containers.
   From VSCode Extensions, install `emeraldwalk.RunOnSave` and add the following to `settings.json`. More on `Run on Save`_: ::

    {
        ...
        "emeraldwalk.runonsave": {
            "commands": [
                {
                    "cmd": "bash <path-to-project>/koku/dev/scripts/m1_refresher.sh"
                }
            ]
        }
    }

Once these steps are completed, follow the instructions on `Developing with docker-compose`_.

References
----------

- https://github.com/jsbroks/coco-annotator/issues/493

.. _`use of Rosetta`: https://github.com/project-koku/koku/blob/main/docs/rosetta_on_m1.rst
.. _`Koku's README`: https://github.com/project-koku/koku/blob/main/README.rst
.. _`docker-compose-m1.yml`: https://github.com/project-koku/koku/blob/main/testing/compose_files/docker-compose-m1.yml
.. _`Run on Save`: https://betterprogramming.pub/automatically-execute-bash-commands-on-save-in-vs-code-7a3100449f63
.. _`bash script`: https://github.com/project-koku/koku/tree/main/dev/scripts/m1_refresher.sh
.. _`Developing with docker-compose`: https://github.com/project-koku/koku/blob/main/README.rst#developing-with-docker-compose
