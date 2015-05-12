import os
import time

from nose.plugins.skip import SkipTest

from ci.tests.general import general
from ci import autotests

testsToRun = general.get_tests_to_run(autotests.getTestLevel())


def setup():
    print "Setup called " + __name__


def post_reboot_checks_test():
    """
    %s
    """ % general.get_function_name()

    general.check_prereqs(testcase_number=1,
                          tests_to_run=testsToRun)

    rebooted_host = os.environ.get('POST_REBOOT_HOST')
    if not rebooted_host:
        raise SkipTest()

    print "Post reboot check node {0}\n".format(rebooted_host)

    wait_time = 5 * 60
    sleep_time = 5

    non_running_services = ''
    while wait_time > 0:
        out = general.execute_command_on_node(rebooted_host, "initctl list | grep ovs-*")
        statuses = out.splitlines()

        non_running_services = [s for s in statuses if 'start/running' not in s]
        if len(non_running_services) == 0:
            break

        wait_time -= sleep_time
        time.sleep(sleep_time)

    assert len(non_running_services) == 0,\
        "Found non running services after reboot on node {0}\n{1}".format(rebooted_host, non_running_services)
