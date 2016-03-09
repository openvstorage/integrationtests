# Copyright 2014 iNuron NV
#
# Licensed under the Open vStorage Modified Apache License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.openvstorage.org/license
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Extended testsuite
"""

import os
import time
from ci.tests.general.general import General
from nose.plugins.skip import SkipTest


class TestExtended(object):
    """
    Extended testsuite
    """
    @staticmethod
    def post_reboot_checks_test():
        """
        Perform service checks after reboot
        """
        rebooted_host = os.environ.get('POST_REBOOT_HOST')
        if not rebooted_host:
            raise SkipTest('Test not setup to run')

        print "Post reboot check node {0}\n".format(rebooted_host)

        wait_time = 5 * 60
        sleep_time = 5

        non_running_services = ''
        while wait_time > 0:
            out = General.execute_command_on_node(rebooted_host, "initctl list | grep ovs-*")
            statuses = out.splitlines()

            non_running_services = [s for s in statuses if 'start/running' not in s]
            if len(non_running_services) == 0:
                break

            wait_time -= sleep_time
            time.sleep(sleep_time)

        assert len(non_running_services) == 0,\
            "Found non running services after reboot on node {0}\n{1}".format(rebooted_host, non_running_services)
