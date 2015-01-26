
import os

from nose.plugins.skip          import SkipTest

from ci.tests.general           import general
from ci                         import autotests



testsToRun     = general.getTestsToRun(autotests.getTestLevel())


def setup():
    print "Setup called " + __name__



def post_reboot_checks_test():
    """
    %s
    """ % general.getFunctionName()

    general.checkPrereqs(testCaseNumber = 1,
                         testsToRun     = testsToRun)

    rebooted_host = os.environ.get('POST_REBOOT_HOST')
    if not rebooted_host:
        raise SkipTest()

    print "Post reboot check node {0}\n".format(rebooted_host)

    wait_time = 5 * 60
    sleep_time = 5

    while wait_time > 0:
        out = general.execute_command_on_node(rebooted_host, "initctl list | grep ovs-*")
        statuses = out.splitlines()

        not_running_services = [s for s in statuses if 'start/running' not in s]
        if len(not_running_services) == 0:
            break

        wait_time -= sleep_time

    assert len(not_running_services) == 0, "Found not running services after reboot on node {0}\n{1}".format(rebooted_host, not_running_services)
