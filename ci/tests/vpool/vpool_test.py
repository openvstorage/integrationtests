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

import time
import os
from ci import autotests
from ci.tests.general import general
from ci.tests.backend import alba
from ci.tests.general.connection import Connection
from ci.tests.general.general import test_config
from ovs.dal.lists.vpoollist import VPoolList
from ovs.dal.lists.pmachinelist import PMachineList
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.services.service import ServiceManager
from ci.tests.vpool import generic
from ci.tests.sanity import sanity_checks_test

testsToRun = general.get_tests_to_run(autotests.get_test_level())

BACKEND_NAME = test_config.get('backend', 'name')
BACKEND_TYPE = test_config.get('backend', 'type')
ENV_IP = test_config.get('main', 'grid_ip')

VPOOL_NAME = test_config.get('vpool', 'vpool_name')
assert VPOOL_NAME, "Please fill out a valid vpool name in autotest.cfg file"


def setup():
    generic.add_alba_backend()


def teardown():
    generic.remove_alba_backend()


def add_vpool_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=1,
                          tests_to_run=testsToRun)

    api = Connection.get_connection()
    vpool_list = api.get_component_by_name('vpools', VPOOL_NAME)
    if not vpool_list:
        generic.add_generic_vpool()
    vpool = VPoolList.get_vpool_by_name(VPOOL_NAME)
    assert vpool, 'Vpool {0} was not created'.format(VPOOL_NAME)
    general.api_remove_vpool(VPOOL_NAME)
    vpool = VPoolList.get_vpool_by_name(VPOOL_NAME)
    assert not vpool, 'Vpool {0} was not deleted'.format(VPOOL_NAME)


def ovs_2263_verify_alba_namespace_cleanup_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=2,
                          tests_to_run=testsToRun)
    no_namespaces = 3

    for nmspc_index in range(no_namespaces):
        alba.create_namespace(BACKEND_NAME, 'nmspc_{0}'.format(nmspc_index), 'default')
    result = alba.list_namespaces(BACKEND_NAME)
    assert len(result) == no_namespaces, "Expected {0} namespaces present on the {1} backend, found {2}".format(no_namespaces, BACKEND_NAME, len(result))
    generic.add_generic_vpool()
    for disk_index in range(no_namespaces):
        pmachine_type = PMachineList.get_pmachines()[0].hvtype
        if pmachine_type == 'VMWARE':
            file_name = os.path.join('/mnt/{0}'.format(VPOOL_NAME), "validate_namespace" + str(time.time()).replace(".", "") + "-flat.vmdk")
        else:
            file_name = os.path.join('/mnt/{0}'.format(VPOOL_NAME), "validate_namespace" + str(time.time()).replace(".", "") + ".raw")
        cmd = "truncate {0} --size 10000000".format(file_name)
        out, error = general.execute_command(cmd)
    result = alba.list_namespaces(BACKEND_NAME)
    assert len(result) == 2 * no_namespaces + 1, "Expected {0} namespaces present on the {1} backend, found {2}".format(2 * no_namespaces + 1, BACKEND_NAME, len(result))
    _, __ = general.execute_command("rm -rf /mnt/{0}/*validate_namespace*".format(VPOOL_NAME))
    general.api_remove_vpool(VPOOL_NAME)
    result = alba.list_namespaces(BACKEND_NAME)
    assert len(result) == no_namespaces, "Expected {0} namespaces present on the {1} backend, found {2}".format(no_namespaces, BACKEND_NAME, len(result))
    for namespace in result:
        alba.delete_namespace(BACKEND_NAME, namespace['name'])
    result = alba.list_namespaces(BACKEND_NAME)
    assert len(result) == 0, "Expected no namespaces present on the {1} backend, found {2}".format(no_namespaces, BACKEND_NAME, len(result))


def ovs_2703_kill_various_services_test():
    """
    Kill various services and see if they recover
    %s
    """ % general.get_function_name()

    general.check_prereqs(testcase_number=3,
                          tests_to_run=testsToRun)
    issues_found = ''
    api = Connection.get_connection()
    vpool_list = api.get_component_by_name('vpools', VPOOL_NAME)
    if not vpool_list:
        generic.add_generic_vpool()

    services_folder = '/opt/OpenvStorage/config/templates/systemd/'
    out, err = general.execute_command('ls {0}'.format(services_folder))

    services_to_kill = out.splitlines()
    for index in range(len(services_to_kill)):
        services_to_kill[index] = services_to_kill[index].split('.')[0]

    client = SSHClient(ENV_IP, username='root')

    for master_service in services_to_kill:
        all_services, err = general.execute_command("initctl list | grep {0}".format(master_service))
        if not err and len(all_services):
            for service in all_services.splitlines():
                service_name = service.split(' ')[0]
                if ServiceManager.has_service(service_name, client) is False:
                    issues_found += 'Service {0} not modeled even if running on system\n'.format(service_name)
                service_status = service.split(' ')[1][:-1]
                service_proc_id = service.split(' ')[3][:-1]
                if service_status not in 'start/running':
                    issues_found += 'Service {0} not found in running state\n'.format(service)
                else:
                    out, err = general.execute_command("kill -9 {0}".format(service_proc_id))
                    time.sleep(5)
                    new_out, err = general.execute_command("initctl list | grep {0}".format(service_name))
                    if len(new_out) == 0:
                        issues_found += 'Service {0} not found after kill command issued\n'.format(service_name)
                    else:
                        if new_out.split(' ')[1][:-1] not in 'start/running':
                            issues_found += 'Service {0} not found in running state after kill command issued\n'.format(service_name)
                        if service_proc_id == new_out.split(' ')[3][:-1]:
                            issues_found += 'Kill command did not work on service {0}'.format(service_name)

    sanity_checks_test.check_vpool_sanity_test()
    general.api_remove_vpool(VPOOL_NAME)

    assert issues_found == '', "Followind issues where found with the services:\n{0}".format(issues_found)
