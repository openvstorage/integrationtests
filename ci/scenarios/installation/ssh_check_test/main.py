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
from ci.api_lib.helpers.storagerouter import StoragerouterHelper
from ci.autotests import gather_results
from ci.scenario_helpers.ci_constants import CIConstants
from ovs.extensions.generic.logger import Logger
from ovs.extensions.generic.sshclient import SSHClient


class SshChecks(CIConstants):

    CASE_TYPE = 'AT_QUICK'
    TEST_NAME = "ci_scenario_ssh_checks"
    LOGGER = Logger('scenario-{0}'.format(TEST_NAME))
    CHECK_USERS = ['root', 'ovs']

    def __init__(self):
        pass

    @staticmethod
    @gather_results(CASE_TYPE, LOGGER, TEST_NAME, log_components=[])
    def main(blocked):
        """
        Run all required methods for the test
        :param blocked: was the test blocked by other test?
        :type blocked: bool
        :return: results of test
        :rtype: dict
        """
        _ = blocked
        return SshChecks.validate_ssh()

    @staticmethod
    def validate_ssh():
        """
        Validate if ssh keys are distributed between nodes

        :return:
        """

        SshChecks.LOGGER.info('Starting validating SSH keys')
        storagerouter_ips = StoragerouterHelper.get_storagerouter_ips()
        assert len(storagerouter_ips) >= 2, "We need at least 2 storagerouters!"

        issues_found = []
        for user in SshChecks.CHECK_USERS:
            for env_ip_from in storagerouter_ips:
                client = SSHClient(env_ip_from, username=user)
                cwd = client.run(['pwd'])
                # Check if the home dir is opt/OpenvStorage
                if cwd == 'opt/OpenvStorage':
                    out = client.run(["cat", "./.ssh/known_hosts"])
                    for env_ip_to in storagerouter_ips:
                        if env_ip_from != env_ip_to:
                            if env_ip_to not in out:
                                error_msg = "Host key verification NOT FOUND between `{0}` and `{1}` for user `{2}`"\
                                    .format(env_ip_from, env_ip_to, user)
                                SshChecks.LOGGER.error(error_msg)
                                issues_found.append(error_msg)
                            else:
                                SshChecks.LOGGER.info("Host key verification found between `{0}` and `{1}` for user `{2}`"
                                                      .format(env_ip_from, env_ip_to, user))
                else:
                    SshChecks.LOGGER.error("Could not open ~/.ssh/known_hosts. Current working directory for user {0} is {1}".format(user, cwd))
        if len(issues_found) != 0:
            raise RuntimeError("One or more hosts keys not found on certain nodes! "
                               "Please check /var/log/ovs/scenario.log for more information!")

        SshChecks.LOGGER.info('Finished validating SSH keys')


def run(blocked=False):
    """
    Run a test

    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return SshChecks().main(blocked)

if __name__ == "__main__":
    run()
