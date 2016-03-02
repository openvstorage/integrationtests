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

"""
A general class dedicated to vPool logic
"""

import json
from ci.tests.general.connection import Connection
from ci.tests.general.general import General
from ci.tests.general.general_arakoon import GeneralArakoon
from ci.tests.general.general_backend import GeneralBackend
from ci.tests.general.general_mgmtcenter import GeneralManagementCenter
from ci.tests.general.general_service import GeneralService
from ci.tests.general.general_storagedriver import GeneralStorageDriver
from ci.tests.general.general_storagerouter import GeneralStorageRouter
from ci.tests.general.general_vdisk import GeneralVDisk
from ovs.dal.hybrids.diskpartition import DiskPartition
from ovs.dal.hybrids.vpool import VPool
from ovs.dal.lists.backendlist import BackendList
from ovs.dal.lists.vpoollist import VPoolList
from ovs.extensions.db.etcd.configuration import EtcdConfiguration
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.services.service import ServiceManager
from ovs.extensions.storageserver.storagedriver import StorageDriverClient
from ovs.lib.helpers.toolbox import Toolbox


class GeneralVPool(object):
    """
    A general class dedicated to vPool logic
    """
    api = Connection()

    @staticmethod
    def add_vpool(vpool_parameters=None, extend=False, storagerouters=None):
        """
        Create a vPool based on the kwargs provided or default parameters found in the autotest.cfg
        :param vpool_parameters: Parameters to be used for vPool creation
        :param extend: Boolean indicating this is to extend an existing vPool or create a new vPool
        :param storagerouters: Guids of the Storage Routers on which to create and extend this vPool
        :return: Created or extended vPool
        """
        if vpool_parameters is None:
            vpool_parameters = GeneralVPool.get_add_vpool_params(extend=extend)

        if 'type' not in vpool_parameters:
            raise ValueError('"Type" is a required keyword in the set of vpool parameters')

        required_params = {'type': (str, ['local', 'distributed', 'alba', 'ceph_s3', 'amazon_s3', 'swift_s3']),
                           'storage_ip': (str, Toolbox.regex_ip),
                           'vpool_name': (str, Toolbox.regex_vpool),
                           'integratemgmt': (bool, None),
                           'readcache_size': (int, {'min': 1, 'max': 10240}),
                           'writecache_size': (int, {'min': 1, 'max': 10240}),
                           'connection_backend': (dict, None),
                           'config_params': (dict, {'dtl_mode': (str, StorageDriverClient.VPOOL_DTL_MODE_MAP.keys()),
                                                    'sco_size': (int, StorageDriverClient.TLOG_MULTIPLIER_MAP.keys()),
                                                    'dedupe_mode': (str, StorageDriverClient.VPOOL_DEDUPE_MAP.keys()),
                                                    'cluster_size': (int, StorageDriverClient.CLUSTER_SIZES),
                                                    'write_buffer': (int, {'min': 128, 'max': 10240}),
                                                    'dtl_transport': (str, StorageDriverClient.VPOOL_DTL_TRANSPORT_MAP.keys()),
                                                    'cache_strategy': (str, StorageDriverClient.VPOOL_CACHE_MAP.keys())})}

        vpool_type = vpool_parameters['type']
        if extend is False and vpool_type not in ['local', 'distributed']:
            required_params['connection_host'] = (str, Toolbox.regex_ip, False)
            required_params['connection_port'] = (int, {'min': 1, 'max': 65535})
            required_params['connection_username'] = (str, None)
            required_params['connection_password'] = (str, None)

        if vpool_type == 'alba':
            required_params['connection_backend'] = (dict, {'backend': (str, Toolbox.regex_guid),
                                                            'metadata': (str, Toolbox.regex_preset)})

        if vpool_type == 'distributed':
            required_params['distributed_mountpoint'] = (str, None)

        Toolbox.verify_required_params(required_params=required_params,
                                       actual_params=vpool_parameters,
                                       exact_match=True)

        if storagerouters is None:
            storagerouters = [GeneralStorageRouter.get_local_storagerouter()]

        for sr in storagerouters:
            task_result = GeneralVPool.api.execute_post_action(component='storagerouters',
                                                               guid=sr.guid,
                                                               action='add_vpool',
                                                               data={'call_parameters': vpool_parameters},
                                                               wait=True,
                                                               timeout=500)
            if task_result[0] is not True:
                raise RuntimeError('vPool was not {0} successfully'.format('extended' if extend is True else 'created'))

        vpool = GeneralVPool.get_vpool_by_name(vpool_parameters['vpool_name'])
        if vpool is None:
            raise RuntimeError('vPool with name {0} could not be found in model'.format(vpool_parameters['vpool_name']))
        return vpool

    @staticmethod
    def remove_vpool(vpool):
        """
        Remove a vPool and all of its storagedrivers
        :param vpool: vPool to remove
        :return: None
        """
        for storage_driver in vpool.storagedrivers:
            GeneralVPool.shrink_vpool(storage_driver)

    @staticmethod
    def shrink_vpool(storage_driver):
        """
        Remove a Storage Driver from a vPool
        :param storage_driver: Storage Driver to remove from the vPool
        :return: None
        """
        vpool = storage_driver.vpool
        if storage_driver.storagerouter.pmachine.hvtype == 'VMWARE':
            root_client = SSHClient(storage_driver.storagerouter, username='root')
            if storage_driver.mountpoint in General.get_mountpoints(root_client):
                root_client.run('umount {0}'.format(storage_driver.mountpoint))
        task_result = GeneralVPool.api.execute_post_action(component='vpools',
                                                           guid=vpool.guid,
                                                           action='shrink_vpool',
                                                           data={'storagerouter_guid': storage_driver.storagerouter.guid},
                                                           wait=True,
                                                           timeout=500)
        if task_result[0] is not True:
            raise RuntimeError('Storage Driver with ID {0} was not successfully removed from vPool {1}'.format(storage_driver.storagedriver_id, vpool.name))
        return GeneralVPool.get_vpool_by_name(vpool_name=vpool.name)

    @staticmethod
    def get_configuration(vpool):
        """
        Retrieve the Storage Driver configuration for the vPool
        :param vpool: vPool to retrieve configuration for
        :return: Storage Driver configuration
        """
        task_result = GeneralVPool.api.execute_get_action(component='vpools',
                                                          guid=vpool.guid,
                                                          action='get_configuration',
                                                          wait=True,
                                                          timeout=60)
        if task_result[0] is not True:
            raise RuntimeError('Failed to retrieve the configuration for vPool {0}'.format(vpool.name))
        return task_result[1]

    @staticmethod
    def get_vpools():
        """
        Retrieve all vPool objects
        :return: Data object list of vPools
        """
        return VPoolList.get_vpools()

    @staticmethod
    def get_add_vpool_params(extend=False, **kwargs):
        """
        Retrieve the default configuration settings to create a vPool
        :param extend: Retrieve config for extending a vPool
        :return: Dictionary with default settings
        """
        test_config = General.get_config()
        config_params = json.loads(test_config.get('vpool', 'config_params'))
        vpool_type = kwargs.get('type', test_config.get('vpool', 'type'))
        vpool_params = {'type': vpool_type,
                        'vpool_name': kwargs.get('name', test_config.get('vpool', 'name')),
                        'storage_ip': kwargs.get('storage_ip', test_config.get('vpool', 'storage_ip')),
                        'integratemgmt': kwargs.get('integrate_mgmt', test_config.getboolean('vpool', 'integrate_mgmt')),
                        'readcache_size': kwargs.get('readcache_size', test_config.getint('vpool', 'readcache_size')),
                        'writecache_size': kwargs.get('writecache_size', test_config.getint('vpool', 'writecache_size')),
                        'connection_backend': {},
                        'config_params': {'dtl_mode': kwargs.get('dtl_mode', config_params.get('dtl_mode', 'a_sync')),
                                          'sco_size': kwargs.get('sco_size', config_params.get('sco_size', 4)),
                                          'dedupe_mode': kwargs.get('dedupe_mode', config_params.get('dedupe_mode', 'dedupe')),
                                          'cluster_size': kwargs.get('cluster_size', config_params.get('cluster_size', 4)),
                                          'write_buffer': kwargs.get('write_buffer', config_params.get('write_buffer', 128)),
                                          'dtl_transport': kwargs.get('dtl_transport', config_params.get('dtl_transport', 'tcp')),
                                          'cache_strategy': kwargs.get('cache_strategy', config_params.get('cache_strategy', 'on_read'))}}
        if extend is False and vpool_type not in ['local', 'distributed']:
            vpool_params['connection_host'] = kwargs.get('alba_connection_host', test_config.get('vpool', 'alba_connection_host'))
            vpool_params['connection_port'] = kwargs.get('alba_connection_port', test_config.getint('vpool', 'alba_connection_port'))
            vpool_params['connection_password'] = kwargs.get('alba_connection_user', test_config.get('vpool', 'alba_connection_user'))
            vpool_params['connection_username'] = kwargs.get('alba_connection_pass', test_config.get('vpool', 'alba_connection_pass'))
        if vpool_type == 'alba':
            backend = BackendList.get_by_name(kwargs.get('backend_name', test_config.get('backend', 'name')))
            if backend is not None:
                vpool_params['connection_backend'] = {'backend': backend.alba_backend_guid,
                                                      'metadata': kwargs.get('preset_name', 'default')}
        if vpool_type == 'distributed':
            vpool_params['distributed_mountpoint'] = kwargs.get('distributed_mountpoint', '/tmp')
        return vpool_params

    @staticmethod
    def get_vpool_by_name(vpool_name):
        """
        Retrieve the vPool object by its name
        :param vpool_name: Name of the vPool
        :return: vPool DAL object
        """
        return VPoolList.get_vpool_by_name(vpool_name)

    @staticmethod
    def get_related_files(vpool):
        """
        Retrieve the files generated during vPool creation
        :param vpool: vPool to retrieve the related files for
        :return: List of file locations
        """
        all_files = {}
        for storagedriver in vpool.storagedrivers:
            files = set()
            if storagedriver.storagerouter.pmachine.hvtype == 'VMWARE':
                volumedriver_mode = EtcdConfiguration.get('/ovs/framework/hosts/{0}/storagedriver|vmware_mode'.format(storagedriver.storagerouter.machine_id))
                if volumedriver_mode == 'ganesha':
                    files.add('/opt/OpenvStorage/config/storagedriver/storagedriver/{0}_ganesha.conf'.format(vpool.name))
            for partition in storagedriver.partitions:
                if partition.role == DiskPartition.ROLES.READ:
                    files.add('{0}/read.dat'.format(partition.path))
            all_files[storagedriver.storagerouter.guid] = files
        return all_files

    @staticmethod
    def get_related_directories(vpool):
        """
        Retrieve the directories generated during vPool creation
        :param vpool: vPool to retrieve the related directories for
        :return: List of directories
        """
        all_directories = {}
        for storagedriver in vpool.storagedrivers:
            directories = set()
            directories.add('/mnt/{0}'.format(vpool.name))
            directories.add('{0}/{1}'.format(EtcdConfiguration.get('/ovs/framework/hosts/{0}/storagedriver|rsp'.format(storagedriver.storagerouter.machine_id)), vpool.name))
            for partition in storagedriver.partitions:
                if partition.role != DiskPartition.ROLES.READ:
                    directories.add(partition.path)
            if vpool.backend_type.code == 'distributed' and storagedriver.mountpoint_dfs is not None:
                directories.add('{0}/fd-{1}-{2}'.format(storagedriver.mountpoint_dfs, vpool.name, vpool.guid))
            all_directories[storagedriver.storagerouter.guid] = directories
        return all_directories

    @staticmethod
    def check_vpool_sanity(vpool, expected_settings):
        """
        Check if all requirements are met for a healthy vPool
        :param vpool: vPool to check sanity for
        :param expected_settings: Parameters used to create a vPool, which will be verified
        :return: None
        """
        mountpoint = '/mnt/{0}'.format(vpool.name)
        vpool_name = expected_settings['vpool_name']
        backend_type = expected_settings['type']
        rdma_enabled = expected_settings['config_params']['dtl_transport'] == StorageDriverClient.FRAMEWORK_DTL_TRANSPORT_RSOCKET
        vpool_config = GeneralVPool.get_configuration(vpool)

        # Verify some basic vPool attributes
        assert vpool.name == vpool_name, 'Expected name {0} for vPool'.format(vpool_name)
        assert vpool.backend_type.code == backend_type, 'Expected backend type {0}'.format(backend_type)
        assert vpool.status == VPool.STATUSES.RUNNING, 'vPool does not have RUNNING status'
        assert vpool.rdma_enabled == rdma_enabled, 'RDMA enabled setting is incorrect'

        # Verify vPool Storage Driver configuration
        expected_vpool_config = expected_settings['config_params']
        for key, value in vpool_config.iteritems():
            if key == 'dtl_enabled' or key == 'tlog_multiplier':
                continue
            if key not in expected_vpool_config:
                raise ValueError('Expected settings does not contain key {0}'.format(key))

            if value != expected_vpool_config[key]:
                raise ValueError('vPool does not have expected configuration {0} for key {1}'.format(expected_vpool_config[key], key))
            expected_vpool_config.pop(key)

        for key in expected_vpool_config.iterkeys():
            raise ValueError('Actual vPool configuration does not contain key {0}'.format(key))

        # Prepare some fields to check
        vpool_services = {'all': ['ovs-watcher-volumedriver',
                                  'ovs-dtl_{0}'.format(vpool.name),
                                  'ovs-volumedriver_{0}'.format(vpool.name),
                                  'ovs-volumerouter-consumer'],
                          'extra': [],
                          'master': ['ovs-arakoon-voldrv']}
        sd_partitions = {'DB': ['MD', 'MDS', 'TLOG'],
                         'READ': ['None'],
                         'WRITE': ['FD', 'DTL', 'SCO'],
                         'SCRUB': ['None']}
        expected_config_sections = ['content_addressed_cache',
                                    'distributed_lock_store',
                                    'volume_manager',
                                    'filesystem',
                                    'threadpool_component',
                                    'distributed_transaction_log',
                                    'metadata_server',
                                    'scocache',
                                    'file_driver',
                                    'volume_registry',
                                    'volume_router_cluster',
                                    'volume_router',
                                    'backend_connection_manager',
                                    'event_publisher']

        if backend_type == 'alba':
            required = {'name': (str, None),
                        'preset': (str, None),
                        'metadata': (dict, None),
                        'backend_guid': (str, Toolbox.regex_guid),
                        'backend_info': (dict, {'policies': (list, None),
                                                'sco_size': (float, None),
                                                'frag_size': (float, None),
                                                'total_size': (float, None),
                                                'nsm_partition_guids': (list, Toolbox.regex_guid)})}
            Toolbox.verify_required_params(required_params=required,
                                           actual_params=vpool.metadata)
            vpool_services['all'].append("ovs-albaproxy_{0}".format(vpool.name))
            sd_partitions['WRITE'].append('FCACHE')

        assert EtcdConfiguration.exists('/ovs/arakoon/voldrv/config', raw=True), 'Volumedriver arakoon does not exist'

        # Do some verifications for all SDs
        storage_ip = None
        voldrv_config = GeneralArakoon.get_config('voldrv')
        all_files = GeneralVPool.get_related_files(vpool=vpool)
        all_directories = GeneralVPool.get_related_directories(vpool=vpool)
        for storagedriver in vpool.storagedrivers:
            storagerouter = storagedriver.storagerouter
            root_client = SSHClient(storagerouter, username='root')

            assert EtcdConfiguration.exists('/ovs/vpools/{0}/hosts/{1}/config'.format(vpool.guid, storagedriver.storagedriver_id), raw=True), 'vPool config not found in etcd'
            current_config_sections = set([item for item in EtcdConfiguration.list('/ovs/vpools/{0}/hosts/{1}/config'.format(vpool.guid, storagedriver.storagedriver_id))])
            assert not current_config_sections.difference(set(expected_config_sections)), 'New section appeared in the storage driver config in etcd'
            assert not set(expected_config_sections).difference(current_config_sections), 'Config section expected for storage driver, but not found in etcd'

            # Check services
            if storagerouter.node_type == 'MASTER':
                for service_name in vpool_services['all'] + vpool_services['master']:
                    if service_name == 'ovs-arakoon-voldrv' and GeneralStorageDriver.has_role(storagedriver, 'DB') is False:
                        continue
                    if ServiceManager.get_service_status(name=service_name,
                                                         client=root_client) is not True:
                        raise ValueError('Service {0} is not running on node {1}'.format(service_name, storagerouter.ip))
            else:
                for service_name in vpool_services['all'] + vpool_services['extra']:
                    if ServiceManager.get_service_status(name=service_name,
                                                         client=root_client) is not True:
                        raise ValueError('Service {0} is not running on node {1}'.format(service_name, storagerouter.ip))

            # Check arakoon config
            if not voldrv_config.has_section(storagerouter.machine_id):
                raise ValueError('Voldrv arakoon cluster does not have section {0}'.format(storagerouter.machine_id))

            # Basic SD checks
            assert storagedriver.cluster_ip == storagerouter.ip, 'Incorrect cluster IP. Expected: {0}  -  Actual: {1}'.format(storagerouter.ip, storagedriver.cluster_ip)
            assert storagedriver.mountpoint == '/mnt/{0}'.format(vpool.name), 'Incorrect mountpoint. Expected: {0}  -  Actual: {1}'.format(mountpoint, storagedriver.mountpoint)
            if storage_ip is not None:
                assert storagedriver.storage_ip == storage_ip, 'Incorrect storage IP. Expected: {0}  -  Actual: {1}'.format(storage_ip, storagedriver.storage_ip)
            storage_ip = storagedriver.storage_ip

            # Check required directories and files
            if storagerouter.guid not in all_directories:
                raise ValueError('Could not find directory information for Storage Router {0}'.format(storagerouter.ip))
            if storagerouter.guid not in all_files:
                raise ValueError('Could not find file information for Storage Router {0}'.format(storagerouter.ip))

            for directory in all_directories[storagerouter.guid]:
                if root_client.dir_exists(directory) is False:
                    raise ValueError('Directory {0} does not exist on Storage Router {1}'.format(directory, storagerouter.ip))
            for file_name in all_files[storagerouter.guid]:
                if root_client.file_exists(file_name) is False:
                    raise ValueError('File {0} does not exist on Storage Router {1}'.format(file_name, storagerouter.ip))

            for partition in storagedriver.partitions:
                if partition.role in sd_partitions and partition.sub_role in sd_partitions[partition.role]:
                    sd_partitions[partition.role].remove(partition.sub_role)
                elif partition.role in sd_partitions and partition.sub_role is None:
                    sd_partitions[partition.role].remove('None')

            # Verify vPool writeable
            if storagerouter.pmachine.hvtype == 'VMWARE':
                GeneralVPool.mount_vpool(vpool=vpool,
                                         root_client=root_client)

            vdisk = GeneralVDisk.create_volume(size=10,
                                               vpool=vpool,
                                               root_client=root_client)
            GeneralVDisk.write_to_volume(vdisk=vdisk,
                                         vpool=vpool,
                                         root_client=root_client,
                                         count=10,
                                         bs='1M',
                                         input_type='random')
            GeneralVDisk.delete_volume(vdisk=vdisk,
                                       vpool=vpool,
                                       root_client=root_client)

        for role, sub_roles in sd_partitions.iteritems():
            for sub_role in sub_roles:
                raise ValueError('Not a single Storage Driver found with partition role {0} and sub-role {1}'.format(role, sub_role))

    @staticmethod
    def check_vpool_cleanup(vpool_info, storagerouters=None):
        """
        Check if everything related to a vPool has been cleaned up on the storagerouters provided
        vpool_info should be a dictionary containing:
            - type
            - guid
            - files
            - directories
            - name (optional)
            - vpool (optional)
            If vpool is provided:
                - storagerouters need to be provided, because on these Storage Routers, we check whether the vPool has been cleaned up
            If name is provided:
                - If storagerouters is NOT provided, all Storage Routers will be checked for a correct vPool removal
                - If storagerouters is provided, only these Storage Routers will be checked for a correct vPool removal

        :param vpool_info: Information about the vPool
        :param storagerouters: Storage Routers to check if vPool has been cleaned up
        :return: None
        """
        for required_param in ['type', 'guid', 'files', 'directories']:
            if required_param not in vpool_info:
                raise ValueError('Incorrect vpool_info provided')
        if 'vpool' in vpool_info and 'name' in vpool_info:
            raise ValueError('vpool and name are mutually exclusive')
        if 'vpool' not in vpool_info and 'name' not in vpool_info:
            raise ValueError('Either vpool or vpool_name needs to be provided')

        vpool = vpool_info.get('vpool')
        vpool_name = vpool_info.get('name')
        vpool_guid = vpool_info['guid']
        vpool_type = vpool_info['type']
        files = vpool_info['files']
        directories = vpool_info['directories']

        supported_backend_types = GeneralBackend.get_valid_backendtypes()
        if vpool_type not in supported_backend_types:
            raise ValueError('Unsupported Backend Type provided. Please choose from: {0}'.format(', '.join(supported_backend_types)))
        if storagerouters is None:
            storagerouters = GeneralStorageRouter.get_storage_routers()

        if vpool_name is not None:
            assert GeneralVPool.get_vpool_by_name(vpool_name=vpool_name) is None, 'A vPool with name {0} still exists'.format(vpool_name)

        # Prepare some fields to check
        vpool_name = vpool.name if vpool else vpool_name
        vpool_services = ['ovs-dtl_{0}'.format(vpool_name),
                          'ovs-volumedriver_{0}'.format(vpool_name)]
        if vpool_type == 'alba':
            vpool_services.append('ovs-albaproxy_{0}'.format(vpool_name))

        # Check etcd
        if vpool is None:
            assert EtcdConfiguration.exists('/ovs/vpools/{0}'.format(vpool_guid), raw=True) is False, 'vPool config still found in etcd'
        else:
            remaining_sd_ids = set([storagedriver.storagedriver_id for storagedriver in vpool.storagedrivers])
            current_sd_ids = set([item for item in EtcdConfiguration.list('/ovs/vpools/{0}/hosts'.format(vpool_guid))])
            assert not remaining_sd_ids.difference(current_sd_ids), 'There are more storagedrivers modelled than present in etcd'
            assert not current_sd_ids.difference(remaining_sd_ids), 'There are more storagedrivers in etcd than present in model'

        # Perform checks on all storagerouters where vpool was removed
        for storagerouter in storagerouters:
            # Check management center
            mgmt_center = GeneralManagementCenter.get_mgmt_center(pmachine=storagerouter.pmachine)
            if mgmt_center is not None:
                assert GeneralManagementCenter.is_host_configured(pmachine=storagerouter.pmachine) is False, 'Management Center is still configured on Storage Router {0}'.format(storagerouter.ip)

            # Check MDS services
            mds_services = GeneralService.get_services_by_name('MetadataServer')
            assert len([mds_service for mds_service in mds_services if mds_service.service.storagerouter_guid == storagerouter.guid]) == 0, 'There are still MDS services present for Storage Router {0}'.format(storagerouter.ip)

            # Check services
            root_client = SSHClient(storagerouter, username='root')
            for service in vpool_services:
                if ServiceManager.has_service(service, client=root_client):
                    raise RuntimeError('Service {0} is still configured on Storage Router {1}'.format(service, storagerouter.ip))

            # Check KVM vpool
            if storagerouter.pmachine.hvtype == 'KVM':
                vpool_overview = root_client.run('virsh pool-list --all').splitlines()
                vpool_overview.pop(1)
                vpool_overview.pop(0)
                for vpool_info in vpool_overview:
                    kvm_vpool_name = vpool_info.split()[0].strip()
                    if vpool_name == kvm_vpool_name:
                        raise ValueError('vPool {0} is still defined on Storage Router {1}'.format(vpool_name, storagerouter.ip))

            # Check file and directory existence
            if storagerouter.guid not in directories:
                raise ValueError('Could not find directory information for Storage Router {0}'.format(storagerouter.ip))
            if storagerouter.guid not in files:
                raise ValueError('Could not find file information for Storage Router {0}'.format(storagerouter.ip))

            for directory in directories[storagerouter.guid]:
                assert root_client.dir_exists(directory) is False, 'Directory {0} still exists on Storage Router {1}'.format(directory, storagerouter.ip)
            for file_name in files[storagerouter.guid]:
                assert root_client.file_exists(file_name) is False, 'File {0} still exists on Storage Router {1}'.format(file_name, storagerouter.ip)

            # Look for errors in storagedriver log
            for error_type in ['error', 'fatal']:
                cmd = "cat -vet /var/log/ovs/volumedriver/{0}.log | tail -1000 | grep ' {1} '; echo true > /dev/null".format(vpool_name, error_type)
                errors = []
                for line in root_client.run(cmd).splitlines():
                    if "HierarchicalArakoon" in line:
                        continue
                    errors.append(line)
                if len(errors) > 0:
                    if error_type == 'error':
                        print 'Volumedriver log file contains errors on Storage Router {0}\n - {1}'.format(storagerouter.ip, '\n - '.join(errors))
                    else:
                        raise RuntimeError('Fatal errors found in volumedriver log file on Storage Router {0}\n - {1}'.format(storagerouter.ip, '\n - '.join(errors)))

    @staticmethod
    def mount_vpool(vpool, root_client):
        """
        Mount the vPool locally
        :param vpool: vPool to mount locally
        :param root_client: SSHClient object
        :return: None
        """
        mountpoint = '/mnt/{0}'.format(vpool.name)
        if mountpoint not in General.get_mountpoints(root_client):
            root_client.run('mount 127.0.0.1:{0} {0}'.format(mountpoint))

    @staticmethod
    def unmount_vpool(vpool, root_client):
        """
        Umount the vPool
        :param vpool: vPool to umount
        :param root_client: SSHClient object
        :return: None
        """
        mountpoint = '/mnt/{0}'.format(vpool.name)
        if mountpoint in General.get_mountpoints(root_client):
            root_client.run('umount {0}'.format(mountpoint))
