===
IQE
===
This section is only Red Hat employees only.

IQE is a suite of tests that ensures the quality of any pull request
to Koku via additional tests. IQE is owned by Red Hat QA,

The source code for the IQE tests is here: https://gitlab.cee.redhat.com/insights-qe/hccm-plugin/tree/master

Prerequisites:
    - koku is deployed via docker-compose or other method, 
    - you are connected to the Red Hat internal network.


===================
Running IQE locally
===================

To run IQE Smoke, Vortex or API tests, run one of the following commands, respectively::

    make docker-iqe-smokes-tests
    make docker-iqe-vortex-tests
    make docker-iqe-api-tests

The tests expect the koku database to be empty



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





