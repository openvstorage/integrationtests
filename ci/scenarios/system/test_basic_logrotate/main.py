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
from ovs.log.log_handler import LogHandler


class LogrotateChecks(object):

    CASE_TYPE = 'AT_QUICK'
    TEST = "ci_scenario_test_basic_logrotate"
    LOGGER = LogHandler.get(source="scenario", name=TEST)

    def __init__(self):
        pass

    @staticmethod
    @gather_results(CASE_TYPE, LOGGER, TEST)
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
                LogrotateChecks.validate_basic_log_rotate()
                return {'status': 'PASSED', 'case_type': LogrotateChecks.CASE_TYPE, 'errors': None}
            except Exception as ex:
                LogrotateChecks.LOGGER.error("Checking basic logrotated failed with error: {0}".format(str(ex)))
                return {'status': 'FAILED', 'case_type': LogrotateChecks.CASE_TYPE, 'errors': ex}
        else:
            return {'status': 'BLOCKED', 'case_type': LogrotateChecks.CASE_TYPE, 'errors': None}

    @staticmethod
    def validate_basic_log_rotate():
        """
        Validate that a basic logrotate script works

        :return:
        """

        LogrotateChecks.LOGGER.info('Starting validating basic logrotate')
        storagerouter_ips = StoragerouterHelper.get_storagerouter_ips()
        assert len(storagerouter_ips) >= 1, "We need at least 1 storagerouters!"

        # @TODO: finish test


def run(blocked=False):
    """
    Run a test

    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return LogrotateChecks().main(blocked)

if __name__ == "__main__":
    run()
