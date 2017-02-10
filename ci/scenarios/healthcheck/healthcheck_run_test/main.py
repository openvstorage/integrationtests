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
    LOGGER = LogHandler.get(source='scenario', name='ci_scenario_healthcheck')
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
                HealthCheckCI.LOGGER.error('Healthcheck CI testing failed with error: {0}'.format(str(ex)))
                return {'status': 'FAILED', 'case_type': HealthCheckCI.CASE_TYPE, 'errors': str(ex), 'blocking': False}
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
        HealthCheckCI.LOGGER.info('Starting to validate the healthcheck')
        storagerouter_master_ips = StoragerouterHelper.get_master_storagerouter_ips()
        assert len(storagerouter_master_ips) >= 1, 'Not enough MASTER storagerouters'
        storagerouter_slave_ips = StoragerouterHelper.get_slave_storagerouter_ips()

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

            missing_packages = SystemHelper.get_missing_packages(ip, HealthCheckCI.REQUIRED_PACKAGES)
            assert len(missing_packages) == 0, 'Missing {0} package(s) on `{1}`: {2}'\
                .format(len(missing_packages), ip, missing_packages)

            ########################################
            # Testing command line, on remote node #
            ########################################

            client = SSHClient(ip, username='root')
            assert client.run(['ovs', 'healthcheck']) is not None
            assert client.run(['ovs', 'healthcheck', '--unattended']) is not None
            assert client.run(['ovs', 'healthcheck', '--to-json']) is not None

            # looping the help seperate modules
            help_options = filter(None, client.run(['ovs', 'healthcheck', '--help']).split('\n'))
            ignored_help_options = ['ovs healthcheck X X -- will run all checks', 'ovs healthcheck MODULE X -- will run all checks for module']
            for help_option in help_options:
                if 'Possible' in help_option or help_option in ignored_help_options:
                    continue
                assert client.run(help_option.split()) is not None
            assert client.run(['ovs', 'healthcheck', 'alba', '--help']) is not None
            assert client.run(['ovs', 'healthcheck', 'alba', 'disk-safety-test', '--help']) is not None
            HealthCheckCI.LOGGER.info('Finished running the healthcheck on node `{0}`'.format(ip))
            ##########################
            # Testing by code import #
            ##########################
            from ovs.extensions.healthcheck.expose_to_cli import HealthCheckCLIRunner

            hc_output = HealthCheckCLIRunner.run_method()
            assert hc_output is not None, 'No results found in the healthcheck output'
            assert 'result' in hc_output, 'the result section is missing in the healthcheck output'
            assert 'recap' in hc_output, 'the recap section is missing in the healthcheck output'
            mapped_result = {'FAILED': {}, 'EXCEPTION': {}}
            for test_name, result in hc_output['result'].iteritems():
                if result['state'] == 'EXCEPTION':
                    mapped_result['EXCEPTION'].update({test_name: result})
                if result['state'] == 'FAILED':
                    mapped_result['FAILED'].update({test_name: result})
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
