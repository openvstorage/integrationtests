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
from ci.tests.backend import alba
from ci.tests.general import general, general_alba
from ci.tests.general.general_vdisk import GeneralVDisk
from ci.tests.vpool.general_vpool import GeneralVPool
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.generic.system import System
from ovs.extensions.services.service import ServiceManager


def setup():
    """
    Make necessary changes before being able to run the tests
    :return: None
    """
    # general_alba.add_alba_backend()


def teardown():
    """
    Removal actions of possible things left over after the test-run
    :return: None
    """
    # general_alba.remove_alba_backend()


def add_vpool_test():
    """
    {0}
    Create a vPool using default values (from autotest.cfg)
    If a vPool with name already exists, remove it and create a new vPool
    Validate the newly created vPool is correctly running
    Remove the newly created vPool and validate everything related to the vPool has been cleaned up
    :return: None
    """.format(general.get_function_name())
    vpool_params = GeneralVPool.get_add_vpool_params()
    vpool_name = vpool_params['vpool_name']
    if vpool_name is None or len(vpool_name) < 3:
        raise RuntimeError('Invalid vPool name provided in autotest.cfg')

    # Remove vPool if 1 already exists
    vpool = GeneralVPool.get_vpool_by_name(vpool_name=vpool_name)
    if vpool is not None:
        GeneralVPool.remove_vpool(vpool=vpool)
        vpool = GeneralVPool.get_vpool_by_name(vpool_name=vpool_name)
        if vpool is not None:
            raise RuntimeError('vPool with name "{0}" still exists'.format(vpool_name))

    # Add vPool and validate health
    vpool = GeneralVPool.add_vpool(vpool_parameters=vpool_params)
    assert vpool is not None, 'vPool {0} was not created'.format(vpool_name)
    GeneralVPool.check_vpool_sanity(vpool=vpool,
                                    expected_settings=vpool_params)

    # Retrieve vPool information before removal
    guid = vpool.guid
    name = vpool.name
    backend_type = vpool.backend_type.code
    files = GeneralVPool.get_related_files(vpool)
    directories = GeneralVPool.get_related_directories(vpool)

    # Remove vPool and validate removal
    GeneralVPool.remove_vpool(vpool=vpool)
    vpool = GeneralVPool.get_vpool_by_name(vpool_name=vpool_name)
    assert vpool is None, 'vPool {0} was not deleted'.format(vpool_name)
    GeneralVPool.check_vpool_cleanup(vpool_info={'guid': guid,
                                                 'name': name,
                                                 'type': backend_type,
                                                 'files': files,
                                                 'directories': directories})


def ovs_2263_verify_alba_namespace_cleanup_test():
    """
    {0}
    """.format(general.get_function_name())

    # Create some namespaces in alba
    no_namespaces = 3
    backend_name = general.get_config().get('backend', 'name')
    for nmspc_index in range(no_namespaces):
        alba.create_namespace(backend_name, 'autotest-ns_{0}'.format(nmspc_index), 'default')
    result = alba.list_namespaces(backend_name)
    assert len(result) == no_namespaces, "Expected {0} namespaces present on the {1} backend, found {2}".format(no_namespaces, backend_name, len(result))

    # Create a vPool and create volumes on it
    vpool = GeneralVPool.add_vpool()
    root_client = SSHClient(System.get_my_storagerouter(), username='root')
    if vpool.storagedrivers[0].storagerouter.pmachine.hvtype == 'VMWARE':
        GeneralVPool.mount_vpool(vpool=vpool,
                                 root_client=root_client)

    for disk_index in range(no_namespaces):
        GeneralVDisk.create_volume(size=10,
                                   vpool=vpool,
                                   root_client=root_client)
    result = alba.list_namespaces(backend_name)
    assert len(result) == 2 * no_namespaces + 1, "Expected {0} namespaces present on the {1} backend, found {2}".format(2 * no_namespaces + 1, backend_name, len(result))

    #
    general.execute_command("rm -rf /mnt/{0}/*validate_namespace*".format(vpool.name))
    GeneralVPool.remove_vpool(vpool)
    result = alba.list_namespaces(backend_name)
    assert len(result) == no_namespaces, "Expected {0} namespaces present on the {1} backend, found {2}".format(no_namespaces, backend_name, len(result))
    for namespace in result:
        alba.delete_namespace(backend_name, namespace['name'])
    result = alba.list_namespaces(backend_name)
    assert len(result) == 0, "Expected no namespaces present on the {1} backend, found {2}".format(no_namespaces, backend_name, len(result))


def ovs_2703_kill_various_services_test():
    """
    Kill various services and see if they recover
    %s
    """ % general.get_function_name()

    issues_found = ''
    vpool_name = general.get_config().get('vpool', 'name')
    vpool = GeneralVPool.get_vpool_by_name(vpool_name)
    if vpool is None:
        vpool = GeneralVPool.add_vpool()

    services_folder = '/opt/OpenvStorage/config/templates/systemd/'
    out, err = general.execute_command('ls {0}'.format(services_folder))

    services_to_kill = out.splitlines()
    for index in range(len(services_to_kill)):
        services_to_kill[index] = services_to_kill[index].split('.')[0]

    env_ip = general.get_config().get('main', 'grid_ip')
    client = SSHClient(env_ip, username='root')

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
                    general.execute_command("kill -9 {0}".format(service_proc_id))
                    time.sleep(5)
                    new_out, err = general.execute_command("initctl list | grep {0}".format(service_name))
                    if len(new_out) == 0:
                        issues_found += 'Service {0} not found after kill command issued\n'.format(service_name)
                    else:
                        if new_out.split(' ')[1][:-1] not in 'start/running':
                            issues_found += 'Service {0} not found in running state after kill command issued\n'.format(service_name)
                        if service_proc_id == new_out.split(' ')[3][:-1]:
                            issues_found += 'Kill command did not work on service {0}'.format(service_name)

    GeneralVPool.remove_vpool(vpool)

    assert issues_found == '', "Following issues where found with the services:\n{0}".format(issues_found)
