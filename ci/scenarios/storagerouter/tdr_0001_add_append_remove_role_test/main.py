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
from ovs.log.log_handler import LogHandler
from ci.api_lib.helpers.storagerouter import StoragerouterHelper


class RoleChecks(object):

    CASE_TYPE = 'AT_QUICK'
    LOGGER = LogHandler.get(source="scenario", name="ci_scenario_add_append_remove_roles")

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
                RoleChecks.validate_add_append_remove_roles()
                return {'status': 'PASSED', 'case_type': RoleChecks.CASE_TYPE, 'errors': None}
            except Exception as ex:
                RoleChecks.LOGGER.error("Post installation service checks failed with error: {0}".format(str(ex)))
                return {'status': 'FAILED', 'case_type': RoleChecks.CASE_TYPE, 'errors': ex}
        else:
            return {'status': 'BLOCKED', 'case_type': RoleChecks.CASE_TYPE, 'errors': None}

    @staticmethod
    def validate_add_append_remove_roles():
        """
        Validate a add role, remove roles and append

        You need at least 1 free partition on a storagerouter

        :return:
        """

        RoleChecks.LOGGER.info('Starting validating add-append-remove roles')
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
    return RoleChecks().main(blocked)

if __name__ == "__main__":
    run()
