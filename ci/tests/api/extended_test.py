# Copyright (C) 2016 iNuron NV
#
# This file is part of Open vStorage Open Source Edition (OSE),
# as available from
#
#      http://www.openvstorage.org and
#      http://www.openvstorage.com.
#
# This file is free software; you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License v3 (GNU AGPLv3)
# as published by the Free Software Foundation, in version 3 as it comes
# in the LICENSE.txt file of the Open vStorage OSE distribution.
#
# Open vStorage is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY of any kind.

"""
Extended testsuite
"""

import os
import time
from ci.tests.general.general import General
from ci.tests.general.logHandler import LogHandler

logger = LogHandler.get('api', name='setup')
logger.logger.propagate = False


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
            logger.info('Test not setup to run')
            return

        logger.info('Post reboot check node {0}\n'.format(rebooted_host))

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
