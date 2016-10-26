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

import os
import time
from ovs.log.log_handler import LogHandler
from ci.helpers.system import SystemHelper


class PostRebootChecks(object):

    CASE_TYPE = 'AT_QUICK'
    LOGGER = LogHandler.get(source="scenario", name="ci_scenario_post_reboot_checks")
    POST_REBOOT_TIMEOUT = 5
    POST_REBOOT_TRIES = 5

    def __init__(self):
        pass

    @staticmethod
    def main(blocked):
        """
        Run all required methods for the test

        :param blocked: was the test blocked by other test?
        :type blocked: bool
        :return: results of test
        :rtype: dict
        """
        if not blocked:
            try:
                # execute tests twice, because of possible leftover constraints
                PostRebootChecks.validate_post_reboot()
                return {'status': 'PASSED', 'case_type': PostRebootChecks.CASE_TYPE, 'errors': None}
            except Exception as ex:
                PostRebootChecks.LOGGER.error("Post reboot checks failed with error: {0}".format(str(ex)))
                return {'status': 'FAILED', 'case_type': PostRebootChecks.CASE_TYPE, 'errors': ex}
        else:
            return {'status': 'BLOCKED', 'case_type': PostRebootChecks.CASE_TYPE, 'errors': None}

    @staticmethod
    def validate_post_reboot(tries=POST_REBOOT_TRIES, timeout=POST_REBOOT_TIMEOUT):
        """
        Validate if all services come up after rebooting a node

        :param tries: amount of tries to check if ovs services are running
        :type tries: int
        :param timeout: timeout between tries
        :type timeout: int
        :return:
        """

        # find rebooted host
        rebooted_host = os.environ.get('POST_REBOOT_HOST')
        assert rebooted_host, "No rebooted host detected in env variable `POST_REBOOT_HOST`"

        # commence test
        PostRebootChecks.LOGGER.info('Starting post-reboot check on node `{0}`'.format(rebooted_host))
        amount_tries = 0
        non_running_services = None
        while tries >= amount_tries:
            non_running_services = SystemHelper.get_non_running_ovs_services(rebooted_host)

            if len(non_running_services) == 0:
                break
            else:
                amount_tries += 1
                time.sleep(timeout)

        assert len(non_running_services) == 0, \
            "Found non running services `{0}` after reboot on node `{1}`".format(non_running_services, rebooted_host)

        PostRebootChecks.LOGGER.info('Finished post-reboot check on node `{0}`'.format(rebooted_host))


def run(blocked=False):
    """
    Run a test

    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return PostRebootChecks().main(blocked)

if __name__ == "__main__":
    run()
