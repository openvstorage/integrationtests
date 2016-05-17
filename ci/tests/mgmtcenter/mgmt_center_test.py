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

"""
Management center testsuite
"""

from ci.tests.general.general import General
from ci.tests.general.general_mgmtcenter import GeneralManagementCenter
from ci.tests.general.general_pmachine import GeneralPMachine
from ci.tests.general.logHandler import LogHandler

logger = LogHandler.get('mgmtcenter', name='setup')
logger.logger.propagate = False


class TestMgmtCenter(object):
    """
    Management center testsuite
    """
    @staticmethod
    def check_reachability_test():
        """
        Verify the management center is reachable
        """
        if GeneralManagementCenter.is_devstack_installed() is False:
            logger.info('No devstack/openstack present')
            return

        management_centers = GeneralManagementCenter.get_mgmt_centers()
        issues_found = ""

        for mgmtcenter in management_centers:
            out, err, _ = General.execute_command("ping {0} -c 1".format(mgmtcenter.ip))
            if "Destination Host Unreachable" in out:
                issues_found += "Management center {0} with ip {1}\n".format(mgmtcenter.name, mgmtcenter.ip)

        assert issues_found == "", "Following management centers could not be reached:\n{0}".format(issues_found)

    @staticmethod
    def management_center_connection_test():
        """
        Verify the management center connectivity
        """
        if GeneralManagementCenter.is_devstack_installed() is False:
            logger.info('No devstack/openstack present')
            return

        management_centers = GeneralManagementCenter.get_mgmt_centers()
        issues_found = ""

        for mgmtcenter in management_centers:
            if not GeneralManagementCenter.test_connection(mgmtcenter.guid):
                issues_found += "Management center {0}\n".format(mgmtcenter.name)

        assert issues_found == "", "Following management centers failed the connection test:\n{0}".format(issues_found)

    @staticmethod
    def check_configured_management_center_test():
        """
        Verify if the management center has been configured correctly
        """
        if GeneralManagementCenter.is_devstack_installed() is False:
            logger.info('No devstack/openstack present')
            return

        management_centers = GeneralManagementCenter.get_mgmt_centers()
        issues_found = ""

        for mgmtcenter in management_centers:
            for physical_machine in mgmtcenter.pmachines:
                if not GeneralManagementCenter.is_host_configured(physical_machine):
                    issues_found += "Mgmtcenter {0} has an unconfigured pmachine with guid {1}\n".format(mgmtcenter.name, physical_machine.guid)

        assert issues_found == "", "Following pmachines were not configured with their management center:\n{0}".format(issues_found)

    @staticmethod
    def check_unconfigured_management_center_test():
        """
        Verify if the management center has been un-configured correctly
        """
        if GeneralManagementCenter.is_devstack_installed() is False:
            logger.info('No devstack/openstack present')
            return

        management_centers = GeneralManagementCenter.get_mgmt_centers()
        issues_found = ""

        for mgmtcenter in management_centers:
            for physical_machine in GeneralPMachine.get_pmachines():
                GeneralManagementCenter.unconfigure_pmachine_with_mgmtcenter(physical_machine, mgmtcenter)
                if GeneralManagementCenter.is_host_configured(physical_machine):
                    issues_found += "Machine {0} is still configured with {1} management center".format(physical_machine.name, mgmtcenter.name)
                GeneralManagementCenter.configure_pmachine_with_mgmtcenter(physical_machine, mgmtcenter)

        assert issues_found == "", "Following pmachines were still configured with their management center:\n{0}".format(issues_found)
