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

from ci.helpers.storagerouter import StoragerouterHelper
from ci.helpers.system import SystemHelper
from ovs.extensions.generic.sshclient import SSHClient
from ovs.log.log_handler import LogHandler


class HealthCheckCI(object):

    CASE_TYPE = 'FUNCTIONAL'
    LOGGER = LogHandler.get(source="scenario", name="ci_scenario_healthcheck")
    REQUIRED_PACKAGES = ['openvstorage-health-check']

    def __init__(self):
        pass

    @staticmethod
    def main(blocked):
        """
        Run all required methods for the test
        Based on: https://github.com/openvstorage/home/issues/29 &
                  https://github.com/openvstorage/framework/issues/884

        :param blocked: was the test blocked by other test?
        :type blocked: bool
        :return: results of test
        :rtype: dict
        """
        if not blocked:
            try:
                result = HealthCheckCI.validate_healthcheck()
                return {'status': 'PASSED', 'case_type': HealthCheckCI.CASE_TYPE, 'errors': result}
            except Exception as ex:
                HealthCheckCI.LOGGER.error("Healthcheck CI testing failed with error: {0}".format(str(ex)))
                return {'status': 'FAILED', 'case_type': HealthCheckCI.CASE_TYPE, 'errors': str(ex)}
        else:
            return {'status': 'BLOCKED', 'case_type': HealthCheckCI.CASE_TYPE, 'errors': None}

    @staticmethod
    def validate_healthcheck():
        """
        Validate if the healthcheck works

        Will always check: localhost & master
        Will check if available: slave

        :return:
        """

        HealthCheckCI.LOGGER.info("Starting to validate the healthcheck")

        storagerouter_master_ips = StoragerouterHelper.get_master_storagerouter_ips()
        assert len(storagerouter_master_ips) >= 1, "Not enough MASTER storagerouters"
        storagerouter_slave_ips = StoragerouterHelper.get_slave_storagerouter_ips()

        # setup base information
        node_ips = [storagerouter_master_ips[0], '127.0.0.1']
        HealthCheckCI.LOGGER.info("Added master `{0}` & `127.0.0.1` to the nodes to be tested by the healthcheck"
                                  .format(storagerouter_master_ips[0]))

        # add a slave if possible
        if len(storagerouter_slave_ips) != 0:
            node_ips.append(storagerouter_slave_ips[0])
            HealthCheckCI.LOGGER.info("Added slave `{0}` to be checked by the healthcheck ..."
                                      .format(storagerouter_slave_ips[0]))
        else:
            HealthCheckCI.LOGGER.warning("Did not add a slave to the list of to be tested nodes because "
                                         "none were available")

        # check if there are missing packages
        for ip in node_ips:
            HealthCheckCI.LOGGER.info("Starting the healthcheck on node `{0}`".format(ip))

            missing_packages = SystemHelper.get_missing_packages(ip, HealthCheckCI.REQUIRED_PACKAGES)
            assert len(missing_packages) == 0, "Missing {0} package(s) on `{1}`: {2}"\
                .format(len(missing_packages), ip, missing_packages)

            ########################################
            # Testing command line, on remote node #
            ########################################

            client = SSHClient(ip, username="root")

            assert client.run(["ovs", "healthcheck"]) is not None
            assert client.run(["ovs", "healthcheck", "silent"]) is not None
            assert client.run(["ovs", "healthcheck", "unattended"]) is not None

            # looping the help seperate modules
            help_options = filter(None, client.run(["ovs", "healthcheck", "help"]).split('\n'))
            for help_option in help_options:
                if "Possible" not in help_option:
                    assert client.run(help_option.split()) is not None

            HealthCheckCI.LOGGER.info("Finished running the healthcheck on node `{0}`".format(ip))

        ##########################
        # Testing by code import #
        ##########################

        from ovs.lib.healthcheck import HealthCheckController

        result = HealthCheckController.check_silent()
        assert result is not None
        assert 'result' in result
        assert 'recap' in result

        HealthCheckCI.LOGGER.info("Finished validating the healthcheck")

        return result


def run(blocked=False):
    """
    Run a test

    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return HealthCheckCI().main(blocked)

if __name__ == "__main__":
    run()
