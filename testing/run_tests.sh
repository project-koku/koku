#!/usr/bin/env bash
#mkdir /test
#mkdir /test/aws_local && mkdir /test/aws_local_0 && mkdir /test/aws_local_1 && mkdir /test/aws_local_2 && mkdir /test/aws_local_3 && mkdir /test/aws_local_4 && mkdir /test/insights_local
#while :; do echo 'Hit CTRL+C'; sleep 1; done
iqe tests plugin hccm -k $TESTS
