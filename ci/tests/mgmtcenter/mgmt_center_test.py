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


from ovs.dal.lists.pmachinelist import PMachineList
from ovs.dal.lists.mgmtcenterlist import MgmtCenterList
from ovs.dal.hybrids.mgmtcenter import MgmtCenter
from ovs.lib.mgmtcenter import MgmtCenterController
from ci.tests.general import general
from ci import autotests
from nose.plugins.skip import SkipTest

testsToRun = general.get_tests_to_run(autotests.get_test_level())


def setup():
    management_centers = MgmtCenterList.get_mgmtcenters()
    if len(management_centers) >= 1:
        mgmtcenter = management_centers[0]
    else:
        mgmtcenter = MgmtCenter()
        mgmtcenter.name = general.test_config.get("mgmtcenter", "name")
        mgmtcenter.username = general.test_config.get("mgmtcenter", "username")
        mgmtcenter.password = general.test_config.get("mgmtcenter", "password")
        mgmtcenter.ip = general.test_config.get('main', 'grid_ip')
        mgmtcenter.type = 'OPENSTACK'
        mgmtcenter.port = 443
    mgmtcenter.save()
    for physical_machine in PMachineList.get_pmachines():
        MgmtCenterController.configure_host(physical_machine.guid, mgmtcenter.guid, True)


def teardown():
    management_centers = MgmtCenterList.get_mgmtcenters()

    for mgmtcenter in management_centers:
        for physical_machine in mgmtcenter.pmachines:
            if MgmtCenterController.is_host_configured(physical_machine.guid) == False:
                MgmtCenterController.configure_host(physical_machine.guid, mgmtcenter.guid, True)


def check_reachability_test(management_centers=[]):
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=1,
                          tests_to_run=testsToRun)

    if not len(management_centers):
        management_centers = MgmtCenterList.get_mgmtcenters()

    for mgmtcenter in management_centers:
        out, err = general.execute_command("ping {0} -c 1".format(mgmtcenter.ip))
        assert "Destination Host Unreachable" not in out, "Management center {0} with {1} cannot be reached"\
            .format(mgmtcenter.name, mgmtcenter.ip)


def management_center_connection_test(management_centers=[]):
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=2,
                          tests_to_run=testsToRun)

    if not len(management_centers):
        management_centers = MgmtCenterList.get_mgmtcenters()

    for mgmtcenter in management_centers:
        assert MgmtCenterController.test_connection(mgmtcenter.guid), "Connection test failed for {0} management center"\
            .format(mgmtcenter.name)


def check_configured_management_center_test(management_centers=[]):
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=3,
                          tests_to_run=testsToRun)

    if not len(management_centers):
        management_centers = MgmtCenterList.get_mgmtcenters()

    for mgmtcenter in management_centers:
        if mgmtcenter.type not in ['OPENSTACK']:
            raise SkipTest()

    for mgmtcenter in management_centers:
        for physical_machine in mgmtcenter.pmachines:
            assert MgmtCenterController.is_host_configured(physical_machine.guid) == True, \
                "Machine {0} is not configured in {1} management center".format(physical_machine.name, mgmtcenter.name)


def check_unconfigured_management_center_test(management_centers=[]):
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=4,
                          tests_to_run=testsToRun)

    if not len(management_centers):
        management_centers = MgmtCenterList.get_mgmtcenters()

    for mgmtcenter in management_centers:
        if mgmtcenter.type not in ['OPENSTACK']:
            raise SkipTest()

    for mgmtcenter in management_centers:
        for physical_machine in PMachineList.get_pmachines():
            MgmtCenterController.unconfigure_host(physical_machine.guid, mgmtcenter.guid, True)

    for mgmtcenter in management_centers:
        for physical_machine in mgmtcenter.pmachines:
            assert MgmtCenterController.is_host_configured(physical_machine.guid) == False, \
                "Machine {0} is still configured in {1} management center".format(physical_machine.name, mgmtcenter.name)

    for mgmtcenter in management_centers:
        for physical_machine in PMachineList.get_pmachines():
            MgmtCenterController.configure_host(physical_machine.guid, mgmtcenter.guid, True)
