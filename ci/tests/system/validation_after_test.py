# Copyright 2014 iNuron NV
#
# Licensed under the Open vStorage Non-Commercial License, Version 1.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.openvstorage.org/OVS_NON_COMMERCIAL
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ci.tests.general import general
from ci import autotests

vpool_name = general.test_config.get("vpool", "vpool_name")
vpool_name = 'system-' + vpool_name

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

    out = general.execute_command_on_node('127.0.0.1', 'grep "warning: syncfs" /var/log/upstart/*-asd-*.log | wc -l')
    assert out == '0', \
        "syncfs warnings detected in asd logs\n:{0}".format(out.splitlines())


def ovs_2493_detect_could_not_acquire_lock_events_test():
    """
    %s
    """ % general.get_function_name()

    general.check_prereqs(testcase_number=2,
                          tests_to_run=testsToRun)

    errorlist = ""
    command = "grep  -C 1 'Could not acquire lock' /var/log/ovs/lib.log"
    gridips = autotests._get_ips()

    for gridip in gridips:
        out = general.execute_command_on_node(gridip, command + " | wc -l")
        if not out == '0':
            errorlist += "node %s \n:{0}\n\n".format(general.execute_command_on_node(gridip, command).splitlines()) % gridip

    assert len(errorlist) == 0 , "Lock errors detected in lib logs on \n" + errorlist


def ovs_2468_verify_no_mds_files_left_after_remove_vpool_test():
    """
    %s
    """ % general.get_function_name()

    general.check_prereqs(testcase_number=3,
                          tests_to_run=testsToRun)

    vpools = general.get_vpools()
    vpool_names = [vpool.name for vpool in vpools]
    command = "find /mnt -name '*mds*'"
    mdsvpoolnames = []

    out = general.execute_command(command + " | wc -l")
    if not out == '0':
        mdsvpoolnames = [line.split('/')[-1] for line in general.execute_command(command)[0].splitlines()]

    mds_files_still_in_filesystem = ""

    for mdsvpoolname in mdsvpoolnames:
        if mdsvpoolname.split('_')[1] not in vpool_names:
            mds_files_still_in_filesystem += mdsvpoolname + "\n"

    assert len(mds_files_still_in_filesystem) == 0, "MDS files still present in filesystem after remove vpool test:\n %s" % mds_files_still_in_filesystem
