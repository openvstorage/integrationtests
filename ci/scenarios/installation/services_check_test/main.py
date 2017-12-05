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

import time

from ci.api_lib.helpers.storagerouter import StoragerouterHelper
from ci.api_lib.helpers.system import SystemHelper

from ci.autotests import gather_results
from ci.scenario_helpers.ci_constants import CIConstants
from ovs.extensions.generic.logger import Logger
from ovs.extensions.generic.sshclient import SSHClient


class ServiceChecks(CIConstants):

    CASE_TYPE = 'AT_QUICK'
    TEST_NAME = "ci_scenario_post_reboot_checks"
    LOGGER = Logger('scenario-{0}'.format(TEST_NAME))
    SERVICE_TIMEOUT = 5
    SERVICE_TRIES = 5

    def __init__(self):
        pass

    @staticmethod
    @gather_results(CASE_TYPE, LOGGER, TEST_NAME, log_components=[{'framework': ['ovs-workers']}])
    def main(blocked):
        """
        Run all required methods for the test
        :param blocked: was the test blocked by other test?
        :type blocked: bool
        :return: results of test
        :rtype: dict
        """
        _ = blocked
        return ServiceChecks.validate_services()

    @staticmethod
    def validate_services(tries=SERVICE_TRIES, timeout=SERVICE_TIMEOUT):
        """
        Validate if all services come up after installation of the setup

        :param tries: amount of tries to check if ovs services are running
        :type tries: int
        :param timeout: timeout between tries
        :type timeout: int
        :return:
        """

        ServiceChecks.LOGGER.info('Starting validating services')
        storagerouter_ips = StoragerouterHelper.get_storagerouter_ips()
        assert len(storagerouter_ips) >= 1, "We need at least 1 storagerouters!"
        # commence test
        for storagerouter_ip in storagerouter_ips:
            ServiceChecks.LOGGER.info('Starting service check on node `{0}`'.format(storagerouter_ip))
            amount_tries = 0
            non_running_services = None
            client = SSHClient(storagerouter_ip, username='root')
            while tries >= amount_tries:
                non_running_services = SystemHelper.get_non_running_ovs_services(client)
                if len(non_running_services) == 0:
                    break
                else:
                    amount_tries += 1
                    time.sleep(timeout)
            assert len(non_running_services) == 0, "Found non running services `{0}` after reboot on node `{1}`".format(non_running_services, storagerouter_ip)
            ServiceChecks.LOGGER.info('Finished validating services on node `{0}`'.format(storagerouter_ip))
        ServiceChecks.LOGGER.info('Finished validating services')


def run(blocked=False):
    """
    Run a test

    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return ServiceChecks().main(blocked)

if __name__ == "__main__":
    run()
