# Copyright 2016 iNuron NV
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
vPool testsuite
"""

import re
import time
from ci.tests.general.general import General
from ci.tests.general.general_alba import GeneralAlba
from ci.tests.general.general_backend import GeneralBackend
from ci.tests.general.general_disk import GeneralDisk
from ci.tests.general.general_service import GeneralService
from ci.tests.general.general_storagerouter import GeneralStorageRouter
from ci.tests.general.general_vdisk import GeneralVDisk
from ci.tests.general.general_vpool import GeneralVPool
from ci.tests.general.logHandler import LogHandler

from ovs.extensions.generic.sshclient import SSHClient

logger = LogHandler.get('api', name='setup')
logger.logger.propagate = False


class TestVPool(object):
    """
    vPool testsuite
    """
    #########
    # TESTS #
    #########

    @staticmethod
    def add_remove_alba_vpool_test():
        """
        Create a vPool using default values (from autotest.cfg)
        If a vPool with name already exists, remove it and create a new vPool
        Validate the newly created vPool is correctly running
        Remove the newly created vPool and validate everything related to the vPool has been cleaned up
        """
        # Raise if vPool already exists
        vpool_name = 'add-delete-alba-vpool'
        vpool = GeneralVPool.get_vpool_by_name(vpool_name=vpool_name)
        if vpool is not None:
            raise RuntimeError('vPool with name "{0}" still exists'.format(vpool_name))

        # Add vPool and validate health
        vpool, vpool_params = GeneralVPool.add_vpool(vpool_parameters={'vpool_name': vpool_name})
        assert vpool is not None, 'vPool {0} was not created'.format(vpool_name)
        GeneralVPool.validate_vpool_sanity(expected_settings=vpool_params)

        # Retrieve vPool information before removal
        guid = vpool.guid
        name = vpool.name
        backend_type = vpool.backend_type.code
        files = GeneralVPool.get_related_files(vpool)
        directories = GeneralVPool.get_related_directories(vpool)
        storagerouters = [sd.storagerouter for sd in vpool.storagedrivers]

        # Remove vPool and validate removal
        GeneralVPool.remove_vpool(vpool=vpool)
        vpool = GeneralVPool.get_vpool_by_name(vpool_name=vpool_name)
        assert vpool is None, 'vPool {0} was not deleted'.format(vpool_name)
        GeneralVPool.check_vpool_cleanup(vpool_info={'guid': guid,
                                                     'name': name,
                                                     'type': backend_type,
                                                     'files': files,
                                                     'directories': directories},
                                         storagerouters=storagerouters)

    @staticmethod
    def add_remove_distributed_vpool_test():
        """
        Create a vPool with 'distributed' BackendType and remove it
        Related ticket: http://jira.cloudfounders.com/browse/OVS-4050
        """
        # Verify if an unused disk is available to mount
        unused_disks = GeneralDisk.get_unused_disks()
        if len(unused_disks) == 0:
            logger.info('No available disks found to mount locally for the distributed backend')
            return

        # Raise if vPool already exists
        vpool_name = 'add-remove-distr-vpool'
        vpool = GeneralVPool.get_vpool_by_name(vpool_name=vpool_name)
        if vpool is not None:
            raise RuntimeError('vPool with name "{0}" still exists'.format(vpool_name))

        unused_disk = unused_disks[0]
        if not unused_disk.startswith('/dev/'):
            raise ValueError('Unused disk must be absolute path')

        # Create a partition on the disk
        local_sr = GeneralStorageRouter.get_local_storagerouter()
        disk = GeneralDisk.get_disk_by_devicename(storagerouter=local_sr,
                                                  device_name=unused_disk)
        partition = GeneralDisk.partition_disk(disk=disk)

        # Mount the unused disk
        if partition.mountpoint is None:
            GeneralDisk.configure_disk(storagerouter=local_sr, disk=disk, offset=0, size=disk.size, roles=[], partition=partition)
            partition.discard()  # Re-initializes the object

        # Add vPool and validate health
        vpool, vpool_params = GeneralVPool.add_vpool(vpool_parameters={'vpool_name': vpool_name,
                                                                       'type': 'distributed',
                                                                       'distributed_mountpoint': partition.mountpoint})
        assert vpool is not None, 'vPool {0} was not created'.format(vpool_name)
        GeneralVPool.validate_vpool_sanity(expected_settings=vpool_params)

        # Retrieve vPool information before removal
        guid = vpool.guid
        name = vpool.name
        backend_type = vpool.backend_type.code
        files = GeneralVPool.get_related_files(vpool)
        directories = GeneralVPool.get_related_directories(vpool)
        storagerouters = [sd.storagerouter for sd in vpool.storagedrivers]

        # Remove vPool and validate removal
        GeneralVPool.remove_vpool(vpool=vpool)
        vpool = GeneralVPool.get_vpool_by_name(vpool_name=vpool_name)
        assert vpool is None, 'vPool {0} was not deleted'.format(vpool_name)
        GeneralVPool.check_vpool_cleanup(vpool_info={'guid': guid,
                                                     'name': name,
                                                     'type': backend_type,
                                                     'files': files,
                                                     'directories': directories},
                                         storagerouters=storagerouters)
        GeneralDisk.unpartition_disk(disk)

    @staticmethod
    def ovs_2263_verify_alba_namespace_cleanup_test():
        """
        Verify ALBA namespace cleanup
        Create an amount of namespaces in ALBA
        Create a vPool and create some volumes
        Verify the amount of namespaces before and after vPool creation
        Remove the vPool and the manually created namespaces
        Verify the amount of namespaces before and after vPool deletion
        """

        # Create some namespaces in alba
        no_namespaces = 3
        backend_name = General.get_config().get('backend', 'name')
        backend = GeneralBackend.get_by_name(name=backend_name)
        namespace_name = 'autotest-ns_'
        namespace_name_regex = re.compile('^autotest-ns_\d$')
        for nmspc_index in range(no_namespaces):
            GeneralAlba.execute_alba_cli_action(backend.alba_backend, 'create-namespace', ['{0}{1}'.format(namespace_name, nmspc_index), 'default'], False)
        result = GeneralAlba.list_alba_namespaces(alba_backend=backend.alba_backend,
                                                  name=namespace_name_regex)
        assert len(result) == no_namespaces, "Expected {0} namespaces present on the {1} backend, found {2}".format(no_namespaces, backend_name, len(result))

        # Create a vPool and create volumes on it
        vpool, _ = GeneralVPool.add_vpool()
        root_client = SSHClient(GeneralStorageRouter.get_local_storagerouter(), username='root')
        if vpool.storagedrivers[0].storagerouter.pmachine.hvtype == 'VMWARE':
            GeneralVPool.mount_vpool(vpool=vpool,
                                     root_client=root_client)

        vdisks = []
        for disk_index in range(no_namespaces):
            vdisks.append(GeneralVDisk.create_volume(size=10,
                                                     vpool=vpool,
                                                     root_client=root_client))
        result = GeneralAlba.list_alba_namespaces(alba_backend=backend.alba_backend)
        assert len(result) == 2 * no_namespaces + 1, "Expected {0} namespaces present on the {1} backend, found {2}".format(2 * no_namespaces + 1, backend_name, len(result))

        # Remove files and vPool
        for vdisk in vdisks:
            GeneralVDisk.delete_volume(vdisk=vdisk,
                                       vpool=vpool,
                                       root_client=root_client)

        if vpool.storagedrivers[0].storagerouter.pmachine.hvtype == 'VMWARE':
            GeneralVPool.unmount_vpool(vpool=vpool,
                                       root_client=root_client)

        GeneralVPool.remove_vpool(vpool)

        # Verify amount of namespaces
        result = GeneralAlba.list_alba_namespaces(alba_backend=backend.alba_backend,
                                                  name=namespace_name_regex)
        assert len(result) == no_namespaces, "Expected {0} namespaces present on the {1} backend, found {2}".format(no_namespaces, backend_name, len(result))
        for namespace in result:
            GeneralAlba.execute_alba_cli_action(backend.alba_backend, 'delete-namespace', [namespace['name']], False)
        result = GeneralAlba.list_alba_namespaces(alba_backend=backend.alba_backend,
                                                  name=namespace_name_regex)
        assert len(result) == 0, "Expected no namespaces present on the {1} backend, found {2}".format(no_namespaces, backend_name, len(result))

    @staticmethod
    def ovs_2703_kill_various_services_test():
        """
        Kill various services and see if they recover
        """

        # @TODO 1: This test does not belong in the vPool tests, its a service test which happens to create a vPool
        # @TODO 2: Make test smarter to test all required services on all node types
        vpool = GeneralVPool.get_vpool_by_name(General.get_config().get('vpool', 'name'))
        if vpool is None:
            vpool, _ = GeneralVPool.add_vpool()

        errors = []
        root_client = SSHClient(GeneralStorageRouter.get_local_storagerouter(), username='root')
        for service_name in GeneralService.get_all_service_templates():
            if GeneralService.has_service(name=service_name,
                                          client=root_client) is False:
                continue

            if GeneralService.get_service_status(name=service_name,
                                                 client=root_client) is False:
                errors.append('Service {0} not found in running state'.format(service_name))
                continue

            pid_before = GeneralService.get_service_pid(name=service_name,
                                                        client=root_client)
            if pid_before == -1:
                errors.append('Service {0} has unknown PID before being killed'.format(service_name))
                continue
            GeneralService.kill_service(name=service_name,
                                        client=root_client)
            time.sleep(5)
            if GeneralService.get_service_status(name=service_name,
                                                 client=root_client) is False:
                errors.append('Service {0} not found in running state after killing it'.format(service_name))
                continue
            pid_after = GeneralService.get_service_pid(name=service_name,
                                                       client=root_client)
            if pid_after == -1:
                errors.append('Service {0} has unknown PID after being killed'.format(service_name))
                continue
            if pid_before == pid_after:
                errors.append('Kill command did not work on service {0}'.format(service_name))

        GeneralVPool.remove_vpool(vpool)

        assert len(errors) == 0, "Following issues were found with the services:\n - {0}".format('\n - '.join(errors))
