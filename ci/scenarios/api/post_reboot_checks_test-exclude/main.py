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
import paramiko
import timeout_decorator
from ovs.log.log_handler import LogHandler
from ci.helpers.system import SystemHelper
from ovs.extensions.generic.sshclient import SSHClient
from ci.helpers.storagerouter import StoragerouterHelper
from timeout_decorator.timeout_decorator import TimeoutError


class PostRebootChecks(object):

    CASE_TYPE = 'AT_QUICK'
    LOGGER = LogHandler.get(source="scenario", name="ci_scenario_post_reboot_checks")
    POST_REBOOT_TIMEOUT = 5
    POST_REBOOT_TRIES = 5
    SSH_REBOOT_DELAY = 5
    SSH_WAIT_TRIES = 200

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

        storagerouter_ips = list(StoragerouterHelper.get_storagerouter_ips())
        assert len(storagerouter_ips) >= 2, "We need at least 2 storagerouters!"

        PostRebootChecks.LOGGER.info('Starting election of node to reboot')
        local_host = SystemHelper.get_local_storagerouter().ip  # ip address of node where tests are being executed
        storagerouter_ips.remove(local_host)  # remove local ip address so we don't reboot where the tests are running
        host_to_reboot = storagerouter_ips[0]  # pick first node that we can find
        PostRebootChecks.LOGGER.info('Finished election of node to reboot: {0}'.format(host_to_reboot))

        # setup beginning ssh connection
        client = PostRebootChecks.create_client(host_to_reboot)

        # reboot server and wait for it to come up
        PostRebootChecks.LOGGER.info('Starting reboot of host `{0}`!'.format(host_to_reboot))
        client.run(" ( sleep {0} ; reboot ) &".format(PostRebootChecks.SSH_REBOOT_DELAY))
        time.sleep(10)

        tries = 0
        while tries < PostRebootChecks.SSH_WAIT_TRIES:
            try:
                client = PostRebootChecks.create_client(host_to_reboot)
                PostRebootChecks.LOGGER.info('host `{0}` is up again!'.format(host_to_reboot))
                break
            except Exception:
                tries += 1
                PostRebootChecks.LOGGER.warning('Host `{0}` still not up at try {1}/{2} ...'
                                                .format(host_to_reboot, tries, PostRebootChecks.SSH_WAIT_TRIES))
                time.sleep(10)  # timeout or else its going too fast
                if tries == PostRebootChecks.SSH_WAIT_TRIES:
                    # if we reach max tries, throw exception
                    raise RuntimeError("Max amounts of attempts reached ({0}) for host `{1}`, host still not up ..."
                                       .format(tries, host_to_reboot))

        # commence test
        PostRebootChecks.LOGGER.info('Starting post-reboot service check on node `{0}`'.format(host_to_reboot))
        amount_tries = 0
        non_running_services = None
        while tries >= amount_tries:
            non_running_services = SystemHelper.get_non_running_ovs_services(host_to_reboot)

            if len(non_running_services) == 0:
                break
            else:
                amount_tries += 1
                time.sleep(timeout)

        assert len(non_running_services) == 0, \
            "Found non running services `{0}` after reboot on node `{1}`".format(non_running_services, host_to_reboot)

        PostRebootChecks.LOGGER.info('Starting post-reboot vPool check on node `{0}`'.format(host_to_reboot))

        PostRebootChecks.LOGGER.info('Finished post-reboot check on node `{0}`'.format(host_to_reboot))

    @staticmethod
    @timeout_decorator.timeout(10)
    def create_client(host):
        """
        Create a new SSH client with a timeout

        :param host: ip address of a existing host
        :rtype host: str
        :return: SSHClient
        :rtype: ovs.extensions.generic.sshclient.SSHClient
        """
        return SSHClient(host, username='root')


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