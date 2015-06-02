import os
import time

from nose.plugins.skip import SkipTest

from ci.tests.general import general
from ci import autotests

testsToRun = general.get_tests_to_run(autotests.getTestLevel())


def setup():
    print "setup called " + __name__
    general.cleanup()


def teardown():
    pass


def ovs_2053_check_for_alba_warnings_test():
    """
    %s
    """ % general.get_function_name()

    general.check_prereqs(testcase_number=1,
                          tests_to_run=testsToRun)

    out = general.execute_command_on_node('127.0.0.1', "grep warn /var/log/upstart/*-asd-*.log | wc -l")
    assert out == '0', \
        "syncfs warnings detected in asd logs\n:{0}".format(out.splitlines())
