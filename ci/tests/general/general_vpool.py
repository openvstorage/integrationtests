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
A general class dedicated to vPool logic
"""

import copy
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
from ovs.dal.hybrids.servicetype import ServiceType
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
    def add_vpool(vpool_parameters=None, storagerouters=None):
        """
        Create a vPool based on the kwargs provided or default parameters found in the autotest.cfg
        :param vpool_parameters: Parameters to be used for vPool creation
        :type vpool_parameters: dict

        :param storagerouters: Guids of the Storage Routers on which to create and extend this vPool
        :type storagerouters: list

        :return: Created or extended vPool
        :rtype: VPool
        """
        if storagerouters is None:
            storagerouters = list(GeneralStorageRouter.get_storage_routers())
        if vpool_parameters is None:
            vpool_parameters = {}
        if not isinstance(storagerouters, list) or len(storagerouters) == 0:
            raise ValueError('Storage Routers should be a list and contain at least 1 element to add a vPool on')

        vpool_name = None
        storagerouter_param_map = dict((sr, GeneralVPool.get_add_vpool_params(storagerouter=sr, **vpool_parameters)) for sr in storagerouters)
        for index, sr in enumerate(storagerouters):
            vpool_name = storagerouter_param_map[sr]['vpool_name']
            task_result = GeneralVPool.api.execute_post_action(component='storagerouters',
                                                               guid=sr.guid,
                                                               action='add_vpool',
                                                               data={'call_parameters': storagerouter_param_map[sr]},
                                                               wait=True,
                                                               timeout=500)
            if task_result[0] is not True:
                raise RuntimeError('vPool was not {0} successfully'.format('extended' if index > 0 else 'created'),
                                   task_result)

        vpool = GeneralVPool.get_vpool_by_name(vpool_name)
        if vpool is None:
            raise RuntimeError('vPool with name {0} could not be found in model'.format(vpool_name))
        return vpool, storagerouter_param_map

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
            raise RuntimeError('Storage Driver with ID {0} was not successfully removed from vPool {1}'.format(storage_driver.storagedriver_id, vpool.name),
                               task_result)
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
            raise RuntimeError('Failed to retrieve the configuration for vPool {0}'.format(vpool.name),
                               task_result)
        return task_result[1]

    @staticmethod
    def get_vpools():
        """
        Retrieve all vPool objects
        :return: Data object list of vPools
        """
        return VPoolList.get_vpools()

    @staticmethod
    def get_add_vpool_params(storagerouter, **kwargs):
        """
        Retrieve the default configuration settings to create a vPool
        :param storagerouter: Storage Router on which to add or extend the vPool
        :type storagerouter: StorageRouter

        :return: Dictionary with default settings
        :rtype: dict
        """
        test_config = General.get_config()
        config_params = json.loads(test_config.get('vpool', 'config_params'))
        vpool_type = kwargs.get('type', test_config.get('vpool', 'type'))
        vpool_params = {'type': vpool_type,
                        'vpool_name': kwargs.get('vpool_name', test_config.get('vpool', 'name')),
                        'storage_ip': kwargs.get('storage_ip', test_config.get('vpool', 'storage_ip')),
                        'integratemgmt': kwargs.get('integrate_mgmt', test_config.getboolean('vpool', 'integrate_mgmt')),
                        'readcache_size': kwargs.get('readcache_size', test_config.getint('vpool', 'readcache_size')),
                        'writecache_size': kwargs.get('writecache_size', test_config.getint('vpool', 'writecache_size')),
                        'storagerouter_ip': storagerouter.ip,
                        'config_params': {'dtl_mode': kwargs.get('dtl_mode', config_params.get('dtl_mode', 'a_sync')),
                                          'sco_size': kwargs.get('sco_size', config_params.get('sco_size', 4)),
                                          'dedupe_mode': kwargs.get('dedupe_mode', config_params.get('dedupe_mode', 'dedupe')),
                                          'cluster_size': kwargs.get('cluster_size', config_params.get('cluster_size', 4)),
                                          'write_buffer': kwargs.get('write_buffer', config_params.get('write_buffer', 128)),
                                          'dtl_transport': kwargs.get('dtl_transport', config_params.get('dtl_transport', 'tcp')),
                                          'cache_strategy': kwargs.get('cache_strategy', config_params.get('cache_strategy', 'on_read'))}}
        if vpool_type not in ['local', 'distributed']:
            vpool_params['backend_connection_info'] = {'host': kwargs.get('alba_connection_host', test_config.get('vpool', 'alba_connection_host')),
                                                       'port': kwargs.get('alba_connection_port', test_config.getint('vpool', 'alba_connection_port')),
                                                       'username': kwargs.get('alba_connection_user', test_config.get('vpool', 'alba_connection_user')),
                                                       'password': kwargs.get('alba_connection_pass', test_config.get('vpool', 'alba_connection_pass'))}
            if vpool_type == 'alba':
                backend = BackendList.get_by_name(kwargs.get('backend_name', test_config.get('backend', 'name')))
                if backend is not None:
                    vpool_params['fragment_cache_on_read'] = kwargs.get('fragment_cache_on_read', test_config.getboolean('vpool', 'fragment_cache_on_read'))
                    vpool_params['fragment_cache_on_write'] = kwargs.get('fragment_cache_on_write', test_config.getboolean('vpool', 'fragment_cache_on_write'))
                    vpool_params['backend_connection_info']['backend'] = {'backend': backend.alba_backend_guid,
                                                                          'metadata': 'default'}
        elif vpool_type == 'distributed':
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
    def validate_vpool_sanity(expected_settings):
        """
        Check if all requirements are met for a healthy vPool
        :param expected_settings: Parameters used to create a vPool, which will be verified
        :type expected_settings: dict

        :return: None
        """
        if not isinstance(expected_settings, dict) or len(expected_settings) == 0:
            raise ValueError('Cannot validate vpool when no settings are passed')

        generic_settings = expected_settings.values()[0]
        vpool_name = generic_settings['vpool_name']
        mountpoint = '/mnt/{0}'.format(vpool_name)
        backend_type = generic_settings['type']
        rdma_enabled = generic_settings['config_params']['dtl_transport'] == StorageDriverClient.FRAMEWORK_DTL_TRANSPORT_RSOCKET

        vpool = GeneralVPool.get_vpool_by_name(vpool_name=vpool_name)
        assert vpool is not None, 'Could not find vPool with name {0}'.format(vpool_name)
        vpool_config = GeneralVPool.get_configuration(vpool)

        # Verify some basic vPool attributes
        assert vpool.name == vpool_name, 'Expected name {0} for vPool'.format(vpool_name)
        assert vpool.backend_type.code == backend_type, 'Expected backend type {0}'.format(backend_type)
        assert vpool.status == VPool.STATUSES.RUNNING, 'vPool does not have RUNNING status'
        assert vpool.rdma_enabled == rdma_enabled, 'RDMA enabled setting is incorrect'
        assert set(expected_settings.keys()) == set([sd.storagerouter for sd in vpool.storagedrivers]), "vPool storagerouters don't match the expected Storage Routers"

        # Verify vPool Storage Driver configuration
        expected_vpool_config = copy.deepcopy(generic_settings['config_params'])
        for key, value in vpool_config.iteritems():
            if key == 'dtl_enabled' or key == 'tlog_multiplier':
                continue
            if key not in expected_vpool_config:
                raise ValueError('Expected settings does not contain key {0}'.format(key))

            if value != expected_vpool_config[key]:
                raise ValueError('vPool does not have expected configuration {0} for key {1}'.format(expected_vpool_config[key], key))
            expected_vpool_config.pop(key)

        if len(expected_vpool_config) > 0:
            raise ValueError('Actual vPool configuration does not contain keys: {0}'.format(', '.join(expected_vpool_config.keys())))

        # Prepare some fields to check
        config = generic_settings['config_params']
        dtl_mode = config['dtl_mode']
        sco_size = config['sco_size']
        dedupe_mode = config['dedupe_mode']
        cluster_size = config['cluster_size']
        write_buffer = config['write_buffer']
        dtl_transport = config['dtl_transport']
        cache_strategy = config['cache_strategy']
        # @TODO: Add more validations for other expected settings (instead of None)
        expected_config = {'backend_connection_manager': {'backend_interface_retries_on_error': 5,
                                                          'backend_interface_retry_interval_secs': 1,
                                                          'backend_interface_retry_backoff_multiplier': 2.0},
                           'content_addressed_cache': {'clustercache_mount_points': None,
                                                       'read_cache_serialization_path': u'/var/rsp/{0}'.format(vpool.name)},
                           'distributed_lock_store': {'dls_arakoon_cluster_id': None,
                                                      'dls_arakoon_cluster_nodes': None,
                                                      'dls_type': u'Arakoon'},
                           'distributed_transaction_log': {'dtl_path': None,
                                                           'dtl_transport': dtl_transport.upper()},
                           'event_publisher': {'events_amqp_routing_key': u'volumerouter',
                                               'events_amqp_uris': None},
                           'file_driver': {'fd_cache_path': None,
                                           'fd_extent_cache_capacity': u'1024',
                                           'fd_namespace': None},
                           'filesystem': {'fs_dtl_config_mode': u'Automatic',
                                          'fs_dtl_mode': u'{0}'.format(StorageDriverClient.VPOOL_DTL_MODE_MAP[dtl_mode]),
                                          'fs_enable_shm_interface': 1,
                                          'fs_file_event_rules': None,
                                          'fs_metadata_backend_arakoon_cluster_nodes': None,
                                          'fs_metadata_backend_mds_nodes': None,
                                          'fs_metadata_backend_type': u'MDS',
                                          'fs_raw_disk_suffix': None,
                                          'fs_virtual_disk_format': None},
                           'metadata_server': {'mds_nodes': None},
                           'scocache': {'backoff_gap': u'2GB',
                                        'scocache_mount_points': None,
                                        'trigger_gap': u'1GB'},
                           'threadpool_component': {'num_threads': 16},
                           'volume_manager': {'clean_interval': 1,
                                              'default_cluster_size': 1024 * cluster_size,
                                              'dtl_throttle_usecs': 4000,
                                              'metadata_path': None,
                                              'non_disposable_scos_factor': float(write_buffer) / StorageDriverClient.TLOG_MULTIPLIER_MAP[sco_size] / sco_size,
                                              'number_of_scos_in_tlog': StorageDriverClient.TLOG_MULTIPLIER_MAP[sco_size],
                                              'read_cache_default_behaviour': StorageDriverClient.VPOOL_CACHE_MAP[cache_strategy],
                                              'read_cache_default_mode': StorageDriverClient.VPOOL_DEDUPE_MAP[dedupe_mode],
                                              'tlog_path': None},
                           'volume_registry': {'vregistry_arakoon_cluster_id': u'voldrv',
                                               'vregistry_arakoon_cluster_nodes': None},
                           'volume_router': {'vrouter_backend_sync_timeout_ms': 5000,
                                             'vrouter_file_read_threshold': 1024,
                                             'vrouter_file_write_threshold': 1024,
                                             'vrouter_id': None,
                                             'vrouter_max_workers': 16,
                                             'vrouter_migrate_timeout_ms': 5000,
                                             'vrouter_min_workers': 4,
                                             'vrouter_redirect_timeout_ms': u'5000',
                                             'vrouter_routing_retries': 10,
                                             'vrouter_sco_multiplier': 1024,
                                             'vrouter_volume_read_threshold': 1024,
                                             'vrouter_volume_write_threshold': 1024},
                           'volume_router_cluster': {'vrouter_cluster_id': None}}
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

        if backend_type == 'alba':
            backend_metadata = {'name': (str, None),
                                'preset': (str, Toolbox.regex_preset),
                                'backend_guid': (str, Toolbox.regex_guid),
                                'arakoon_config': (dict, None),
                                'connection': (dict, {'host': (str, Toolbox.regex_ip, False),
                                                      'port': (int, {'min': 1, 'max': 65535}),
                                                      'client_id': (str, Toolbox.regex_guid),
                                                      'client_secret': (str, None),
                                                      'local': (bool, None)}),
                                'backend_info': (dict, {'policies': (list, None),
                                                        'sco_size': (float, None),
                                                        'frag_size': (float, None),
                                                        'total_size': (float, None),
                                                        'nsm_partition_guids': (list, Toolbox.regex_guid)})}
            required = {'backend': (dict, backend_metadata),
                        'backend_aa': (dict, backend_metadata, False)}
            Toolbox.verify_required_params(required_params=required,
                                           actual_params=vpool.metadata)
            vpool_services['all'].append("ovs-albaproxy_{0}".format(vpool.name))
            sd_partitions['WRITE'].append('FCACHE')
            expected_config['backend_connection_manager'].update({'alba_connection_host': None,
                                                                  'alba_connection_port': None,
                                                                  'alba_connection_preset': None,
                                                                  'alba_connection_timeout': 15,
                                                                  'backend_type': u'{0}'.format(vpool.backend_type.code.upper())})
        elif backend_type == 'distributed':
            expected_config['backend_connection_manager'].update({'backend_type': u'LOCAL',
                                                                  'local_connection_path': u'{0}'.format(generic_settings['distributed_mountpoint'])})

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
            # @todo: replace next lines with implementation defined in: http://jira.openvstorage.com/browse/OVS-4577
            # current_config_sections = set([item for item in EtcdConfiguration.list('/ovs/vpools/{0}/hosts/{1}/config'.format(vpool.guid, storagedriver.storagedriver_id))])
            # assert not current_config_sections.difference(set(expected_config.keys())), 'New section appeared in the storage driver config in etcd'
            # assert not set(expected_config.keys()).difference(current_config_sections), 'Config section expected for storage driver, but not found in etcd'
            #
            # for key, values in expected_config.iteritems():
            #     current_config = EtcdConfiguration.get('/ovs/vpools/{0}/hosts/{1}/config/{2}'.format(vpool.guid, storagedriver.storagedriver_id, key))
            #     assert set(current_config.keys()).union(set(values.keys())) == set(values.keys()), 'Not all expected keys match for key "{0}" on Storage Driver {1}'.format(key, storagedriver.name)
            #
            #     for sub_key, value in current_config.iteritems():
            #         expected_value = values[sub_key]
            #         if expected_value is None:
            #             continue
            #         assert value == expected_value, 'Key: {0} - Sub key: {1} - Value: {2} - Expected value: {3}'.format(key, sub_key, value, expected_value)

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

            # @TODO: check roles and sub_roles for all storagedrivers and not just once
            for partition in storagedriver.partitions:
                if partition.role in sd_partitions and partition.sub_role in sd_partitions[partition.role]:
                    sd_partitions[partition.role].remove(partition.sub_role)
                elif partition.role in sd_partitions and partition.sub_role is None and len(sd_partitions[partition.role]):
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
            mds_services = GeneralService.get_services_by_name(ServiceType.SERVICE_TYPES.MD_SERVER)
            assert len([mds_service for mds_service in mds_services if mds_service.storagerouter_guid == storagerouter.guid]) == 0, 'There are still MDS services present for Storage Router {0}'.format(storagerouter.ip)

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
