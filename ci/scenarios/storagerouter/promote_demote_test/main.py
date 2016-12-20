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
from ovs.log.log_handler import LogHandler
from ci.helpers.system import SystemHelper
from ci.helpers.storagerouter import StoragerouterHelper


class PromoteDemoteChecks(object):

    CASE_TYPE = 'AT_QUICK'
    LOGGER = LogHandler.get(source="scenario", name="ci_scenario_promote_demote_test")

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
                PromoteDemoteChecks.validate_promote_demote()
                return {'status': 'PASSED', 'case_type': PromoteDemoteChecks.CASE_TYPE, 'errors': None}
            except Exception as ex:
                PromoteDemoteChecks.LOGGER.error("Post installation service checks failed with error: {0}"
                                                 .format(str(ex)))
                return {'status': 'FAILED', 'case_type': PromoteDemoteChecks.CASE_TYPE, 'errors': ex}
        else:
            return {'status': 'BLOCKED', 'case_type': PromoteDemoteChecks.CASE_TYPE, 'errors': None}

    @staticmethod
    def validate_promote_demote():
        """
        Validate a promote of a extra node and demote of a master node

        :return:
        """




def run(blocked=False):
    """
    Run a test

    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return PromoteDemoteChecks().main(blocked)

if __name__ == "__main__":
    run()
