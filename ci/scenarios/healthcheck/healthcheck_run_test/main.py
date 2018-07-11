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
from ci.autotests import gather_results
from ci.scenario_helpers.ci_constants import CIConstants
from ovs.dal.lists.storagerouterlist import StorageRouterList
from ovs.extensions.generic.sshclient import SSHClient
from ovs.log.log_handler import LogHandler


class HealthCheckCI(CIConstants):

    CASE_TYPE = 'FUNCTIONALITY'
    TEST_NAME = 'ci_scenario_healthcheck'
    LOGGER = LogHandler.get(source='scenario', name=TEST_NAME)

    def __init__(self):
        pass

    @staticmethod
    @gather_results(CASE_TYPE, LOGGER, TEST_NAME, log_components=[{'framework': ['ovs-workers']}])
    def main(blocked):
        """
        Run all required methods for the test
        Based on: https://github.com/openvstorage/home/issues/29 &
                  https://github.com/openvstorage/framework/issues/884
        :param blocked: was the test blocked by other test? Picked up by the decorator
        :type blocked: bool
        :return: results of test
        :rtype: dict
        """
        _ = blocked
        return HealthCheckCI.validate_healthcheck()

    @staticmethod
    def validate_healthcheck():
        """
        Validate if the healthcheck works
        Will always check: localhost & master
        Will check if available: slave
        :return:
        """
        HealthCheckCI.LOGGER.info('Starting to validate the healthcheck')
        storagerouter_master_ips = [storagerouter.ip for storagerouter in StorageRouterList.get_masters()]
        assert len(storagerouter_master_ips) >= 1, 'Not enough MASTER storagerouters'
        storagerouter_slave_ips = [storagerouter.ip for storagerouter in StorageRouterList.get_slaves()]

        # setup base information
        node_ips = [storagerouter_master_ips[0], '127.0.0.1']
        HealthCheckCI.LOGGER.info('Added master `{0}` & `127.0.0.1` to the nodes to be tested by the healthcheck'
                                  .format(storagerouter_master_ips[0]))

        # add a slave if possible
        if len(storagerouter_slave_ips) != 0:
            node_ips.append(storagerouter_slave_ips[0])
            HealthCheckCI.LOGGER.info('Added slave `{0}` to be checked by the healthcheck ...'
                                      .format(storagerouter_slave_ips[0]))
        else:
            HealthCheckCI.LOGGER.warning('Did not add a slave to the list of to be tested nodes because '
                                         'none were available')

        # check if there are missing packages
        for ip in node_ips:
            HealthCheckCI.LOGGER.info('Starting the healthcheck on node `{0}`'.format(ip))
            ##########################
            # Testing by code import #
            ##########################
            from ovs.extensions.healthcheck.expose_to_cli import HealthCheckCLIRunner
            hc_output = HealthCheckCLIRunner.run_method()

            if type(hc_output) is dict:
                assert hc_output is not None, 'No results found in the healthcheck output'
                assert 'result' in hc_output, 'the result section is missing in the healthcheck output'
                assert 'recap' in hc_output, 'the recap section is missing in the healthcheck output'
                hc_result = hc_output['result']
            else:
                hc_result = hc_output.result_dict

            mapped_result = {'FAILED': {}, 'EXCEPTION': {}}
            for test_name, result in hc_result.iteritems():
                if result['state'] == 'EXCEPTION':
                    mapped_result['EXCEPTION'].update({test_name: result})
                if result['state'] == 'FAILED':
                    mapped_result['FAILED'].update({test_name: result})

            if type(hc_output) is dict:
                recap = hc_output['recap']
                assert recap['EXCEPTION'] == 0, '{0} exception(s) found during the healthcheck run: {1}'.format(recap['EXCEPTION'], dict(mapped_result['EXCEPTION'], **mapped_result['FAILED']))
                assert recap['FAILED'] == 0, '{0} failure(s) found during the healthcheck run: {1}'.format(recap['FAILED'], mapped_result['FAILED'])

            HealthCheckCI.LOGGER.info('Finished validating the healthcheck')
            return hc_output


def run(blocked=False):
    """
    Run a test
    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return HealthCheckCI().main(blocked)


if __name__ == '__main__':
    run()

