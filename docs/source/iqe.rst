===
IQE
===

Prerequisites:
    - koku is deployed via docker-compose or other method, 
    - you are connected to the Red Hat internal network.

For simple setup, continue to the prerequisites below, otherwise, for information on IQE, visit: https://gitlab.cee.redhat.com/insights-qe/hccm-plugin/tree/master 

===================
Running IQE locally
===================

IQE expects the database to be empty.
To run IQE Smoke, Vortex or API tests, run one of the following commands, respectively::

    make docker-iqe-smokes-tests
    make docker-iqe-vortex-tests
    make docker-iqe-api-tests


====================
Running PDB in IQE
====================
To run PDB while using dockerized IQE: 
    Shell into the docker container that runs IQE::

        koku/testing/run_test.sh bash

run the following command to run a specific test, 
replacing the :code:`-k` flag's input to a specific test you want to run::

    iqe tests plugin hccm -k test_api_aws_storage_filtered_top --pdb

optionally you can, run all tests::

    iqe tests plugin hccm --pdb

Any test that fails should start a PDB session.





