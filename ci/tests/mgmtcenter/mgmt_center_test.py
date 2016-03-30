# Copyright 2016 iNuron NV
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Management center testsuite
"""

from ci.tests.general.general import General
from ci.tests.general.general_mgmtcenter import GeneralManagementCenter
from ci.tests.general.general_pmachine import GeneralPMachine
from nose.plugins.skip import SkipTest


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
            raise SkipTest('No devstack/openstack present')

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
            raise SkipTest('No devstack/openstack present')

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
            raise SkipTest('No devstack/openstack present')

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
            raise SkipTest('No devstack/openstack present')

        management_centers = GeneralManagementCenter.get_mgmt_centers()
        issues_found = ""

        for mgmtcenter in management_centers:
            for physical_machine in GeneralPMachine.get_pmachines():
                GeneralManagementCenter.unconfigure_pmachine_with_mgmtcenter(physical_machine, mgmtcenter)
                if GeneralManagementCenter.is_host_configured(physical_machine):
                    issues_found += "Machine {0} is still configured with {1} management center".format(physical_machine.name, mgmtcenter.name)
                GeneralManagementCenter.configure_pmachine_with_mgmtcenter(physical_machine, mgmtcenter)

        assert issues_found == "", "Following pmachines were still configured with their management center:\n{0}".format(issues_found)
