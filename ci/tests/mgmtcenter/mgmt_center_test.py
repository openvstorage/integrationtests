# Copyright 2015 iNuron NV
#
# Licensed under the Open vStorage Non-Commercial License, Version 1.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.openvstorage.org/OVS_NON_COMMERCIAL
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ovs.lib.mgmtcenter import MgmtCenterController
from ci.tests.general import general
from ci.tests.mgmtcenter import generic
from ci import autotests
from ci.tests.general.connection import Connection

testsToRun = general.get_tests_to_run(autotests.get_test_level())
MGMT_NAME = general.test_config.get("mgmtcenter", "name")
MGMT_USERNAME = general.test_config.get("mgmtcenter", "username")
MGMT_PASS = general.test_config.get("mgmtcenter", "password")
MGMT_IP = general.test_config.get('mgmtcenter', 'ip')
MGMT_TYPE = general.test_config.get('mgmtcenter', 'type')
MGMT_PORT = general.test_config.get('mgmtcenter', 'port')

mgmtcenters_todelete = []


def setup():
    api = Connection.get_connection()
    management_centers = api.get_components('mgmtcenters')
    if len(management_centers) == 0:
        mgmtcenter = generic.create_mgmt_center(MGMT_NAME, MGMT_USERNAME, MGMT_PASS, MGMT_IP, MGMT_TYPE, MGMT_PORT)
        mgmtcenters_todelete.append(mgmtcenter['guid'])
        for physical_machine in api.get_components('pmachines'):
            generic.configure_pmachine_with_mgmtcenter(physical_machine['guid'], mgmtcenter['guid'])


def teardown():
    for mgmcenter_guid in mgmtcenters_todelete:
        generic.remove_mgmt_center(mgmcenter_guid)


def check_reachability_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=1,
                          tests_to_run=testsToRun)

    api = Connection.get_connection()
    management_centers = api.get_components('mgmtcenters')
    issues_found = ""

    for mgmtcenter in management_centers:
        out, err = general.execute_command("ping {0} -c 1".format(mgmtcenter['ip']))
        if "Destination Host Unreachable" in out:
            issues_found += "Management center {0} with ip {1}\n".format(mgmtcenter['name'], mgmtcenter['ip'])

    assert issues_found == "", "Following management centers could not be reached:\n{0}".format(issues_found)


def management_center_connection_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=2,
                          tests_to_run=testsToRun)

    api = Connection.get_connection()
    management_centers = api.get_components('mgmtcenters')
    issues_found = ""

    for mgmtcenter in management_centers:
        if not MgmtCenterController.test_connection(mgmtcenter['guid']):
            issues_found += "Management center {0}\n".format(mgmtcenter['name'])

    assert issues_found == "", "Following management centers failed the connection test:\n{0}".format(issues_found)


def check_configured_management_center_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=3,
                          tests_to_run=testsToRun)

    api = Connection.get_connection()
    management_centers = api.get_components('mgmtcenters')
    issues_found = ""

    for mgmtcenter in management_centers:
        # @todo : remove 'if' when OVS-3626 is fixed
        if mgmtcenter['type'] in ['OPENSTACK']:
            for physical_machine_guid in mgmtcenter['pmachines_guids']:
                if not MgmtCenterController.is_host_configured(physical_machine_guid):
                    issues_found += "Mgmtcenter {0} has an unconfigured pmachine with guid {1}\n".format(mgmtcenter['name'], physical_machine_guid)

    assert issues_found == "", "Following pmachines where not configured with their management center:\n{0}".format(issues_found)


def check_unconfigured_management_center_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=4,
                          tests_to_run=testsToRun)

    api = Connection.get_connection()
    management_centers = api.get_components('mgmtcenters')
    issues_found = ""

    for mgmtcenter in management_centers:
        # @todo : remove 'if' when OVS-3626 is fixed
        if mgmtcenter['type'] not in ['OPENSTACK']:
            for physical_machine in api.get_components('pmachines'):
                generic.unconfigure_pmachine_with_mgmtcenter(physical_machine['guid'], mgmtcenter['guid'])
                if MgmtCenterController.is_host_configured(physical_machine['guid']):
                    issues_found += "Machine {0} is still configured with {1} management center".format(physical_machine['name'], mgmtcenter['name'])
                generic.configure_pmachine_with_mgmtcenter(physical_machine['guid'], mgmtcenter['guid'])

    assert issues_found == "", "Following pmachines where still configured with their management center:\n{0}".format(issues_found)
