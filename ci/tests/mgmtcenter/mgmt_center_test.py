# Copyright 2015 iNuron NV
#
# Licensed under the Open vStorage Modified Apache License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.openvstorage.org/license
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ci.tests.general import general
from ci.tests.mgmtcenter import generic
from nose.plugins.skip import SkipTest
from ci import autotests
from ci.tests.general.connection import Connection

testsToRun = general.get_tests_to_run(autotests.get_test_level())


def setup():
    generic.create_generic_mgmt_center()


def teardown():
    api = Connection.get_connection()
    management_centers = api.get_components('mgmtcenters')
    for mgmcenter in management_centers:
        generic.remove_mgmt_center(mgmcenter['guid'])


def check_reachability_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=1,
                          tests_to_run=testsToRun)

    devstack_installed = generic.is_devstack_installed()
    if devstack_installed is False:
        raise SkipTest

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

    devstack_installed = generic.is_devstack_installed()
    if devstack_installed is False:
        raise SkipTest

    api = Connection.get_connection()
    management_centers = api.get_components('mgmtcenters')
    issues_found = ""

    for mgmtcenter in management_centers:
        if not generic.test_connection(mgmtcenter['guid']):
            issues_found += "Management center {0}\n".format(mgmtcenter['name'])

    assert issues_found == "", "Following management centers failed the connection test:\n{0}".format(issues_found)


def check_configured_management_center_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=3,
                          tests_to_run=testsToRun)

    devstack_installed = generic.is_devstack_installed()
    if devstack_installed is False:
        raise SkipTest

    api = Connection.get_connection()
    management_centers = api.get_components('mgmtcenters')
    issues_found = ""

    for mgmtcenter in management_centers:
        for physical_machine_guid in mgmtcenter['pmachines_guids']:
            if not generic.is_host_configured(physical_machine_guid):
                issues_found += "Mgmtcenter {0} has an unconfigured pmachine with guid {1}\n".format(mgmtcenter['name'], physical_machine_guid)

    assert issues_found == "", "Following pmachines where not configured with their management center:\n{0}".format(issues_found)


def check_unconfigured_management_center_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=4,
                          tests_to_run=testsToRun)

    devstack_installed = generic.is_devstack_installed()
    if devstack_installed is False:
        raise SkipTest

    api = Connection.get_connection()
    management_centers = api.get_components('mgmtcenters')
    issues_found = ""

    for mgmtcenter in management_centers:
        for physical_machine in api.get_components('pmachines'):
            generic.unconfigure_pmachine_with_mgmtcenter(physical_machine['guid'], mgmtcenter['guid'])
            if generic.is_host_configured(physical_machine['guid']):
                issues_found += "Machine {0} is still configured with {1} management center".format(physical_machine['name'], mgmtcenter['name'])
            generic.configure_pmachine_with_mgmtcenter(physical_machine['guid'], mgmtcenter['guid'])

    assert issues_found == "", "Following pmachines where still configured with their management center:\n{0}".format(issues_found)
