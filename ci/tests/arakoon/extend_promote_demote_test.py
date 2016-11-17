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

# arakoon cluster setup
#
# DB role on node determines if cluster will be extended to that node
#
# possible arakoon clusters:
# - ovsdb
# - voldrv
# - abm
# - nsm_0
#
# promote will extend cluster / demote will reduce cluster
#

"""
Arakoon testsuite
"""

import os
import hashlib
from ci.tests.general.general_arakoon import GeneralArakoon
from ci.tests.general.general_storagerouter import GeneralStorageRouter
from ci.tests.general.logHandler import LogHandler
from ConfigParser import RawConfigParser
from ovs.dal.hybrids.servicetype import ServiceType
from ovs.dal.lists.servicelist import ServiceList
from ovs.extensions.db.arakoon.ArakoonInstaller import ArakoonInstaller
from ovs.extensions.generic.configuration import Configuration
from ovs.extensions.generic.remote import remote
from ovs.extensions.generic.sshclient import SSHClient
from ovs.lib.scheduledtask import ScheduledTaskController
from StringIO import StringIO


class TestArakoon(object):
    """
    Arakoon testsuite
    """

    ####################
    # HELPER FUNCTIONS #
    ####################
    logger = LogHandler.get('arakoon', name='setup')

    @staticmethod
    def get_nr_of_tlogs_in_folder(root_client, tlog_location):
        nr_of_tlogs = 0
        for file_name in root_client.file_list(tlog_location):
            if file_name.endswith('tlx') or file_name.endswith('tlog'):
                nr_of_tlogs += 1
        return nr_of_tlogs

    @staticmethod
    def check_archived_directory(client, archived_files):
        """
        Verify if directory has been archived
        :param client: SSHClient object
        :param archived_files: Files to check
        :return: True if archived
        """
        for archived_file in archived_files:
            file_found = False
            archived_file = archived_file.rstrip('/')
            archived_directory = os.path.dirname(archived_file)
            archived_file_name = os.path.basename(archived_file)
            if client.dir_exists(archived_directory):
                files_in_directory = client.file_list(archived_directory)
                # checking just the last file
                file_name = files_in_directory[-1]
                if file_name.endswith('.tgz'):
                    out = client.run(['tar', '-tf', '/'.join([archived_directory, file_name])])
                    if archived_file_name in out:
                        file_found = True
            if file_found is False:
                return False
        return True

    @staticmethod
    def verify_arakoon_structure(client, cluster_name, config_present, dir_present):
        """
        Verify the expected arakoon structure and configuration
        :param client: SSHClient object
        :param cluster_name: Name of the arakoon cluster
        :param config_present: configuration presence expectancy
        :param dir_present: Directory structure presence expectancy
        :return: True if correct
        """
        tlog_dir = GeneralArakoon.TLOG_DIR.format('/var/tmp', cluster_name)
        home_dir = GeneralArakoon.HOME_DIR.format('/var/tmp', cluster_name)

        key_exists = Configuration.exists(GeneralArakoon.CONFIG_KEY.format(cluster_name), raw=True)
        assert key_exists is config_present,\
            "Arakoon configuration was {0} expected".format('' if config_present else 'not ')
        for directory in [tlog_dir, home_dir]:
            assert client.dir_exists(directory) is dir_present,\
                "Arakoon directory {0} was {1} expected".format(directory, '' if dir_present else 'not ')

    @staticmethod
    def validate_arakoon_config_files(storagerouters, cluster_name=None):
        """
        Verify whether all arakoon configurations are correct
        :param storagerouters: Storage Routers
        :param cluster_name: Name of the Arakoon cluster
        :return:
        """
        storagerouters.sort(key=lambda k: k.ip)
        TestArakoon.logger.info('Validating arakoon files for {0}'.format(', '.join([sr.ip for sr in storagerouters])))

        nr_of_configs_on_master = 0
        nr_of_configs_on_extra = 0

        node_ids = dict()
        matrix = dict()
        for sr in storagerouters:
            node_ids[sr.ip] = sr.machine_id
            configs_to_check = []
            matrix[sr] = dict()
            if cluster_name is not None:
                if Configuration.exists(GeneralArakoon.CONFIG_KEY.format(cluster_name), raw=True):
                    configs_to_check = [GeneralArakoon.CONFIG_KEY.format(cluster_name)]
            else:
                gen = Configuration.list(GeneralArakoon.CONFIG_ROOT)
                for entry in gen:
                    if 'nsm_' not in entry:
                        if Configuration.exists(GeneralArakoon.CONFIG_KEY.format(cluster_name), raw=True):
                            configs_to_check.append(GeneralArakoon.CONFIG_KEY.format(entry))
            for config_name in configs_to_check:
                config_contents = Configuration.get(configs_to_check[0], raw=True)
                matrix[sr][config_name] = hashlib.md5(config_contents).hexdigest()
            if sr.node_type == 'MASTER':
                nr_of_configs_on_master = len(matrix[sr])
            else:
                nr_of_configs_on_extra = len(matrix[sr])

        TestArakoon.logger.info('cluster_ids: {0}'.format(node_ids))
        TestArakoon.logger.info('matrix: {0}'.format(matrix))

        for config_file in matrix[storagerouters[0]].keys():
            TestArakoon.validate_arakoon_config_content(config_file, node_ids)

        assert len(storagerouters) == len(matrix.keys()), "not all nodes have arakoon configs"
        incorrect_nodes = list()
        for sr in matrix:
            is_master = sr.node_type == 'MASTER'
            if (is_master is True and len(matrix[sr]) != nr_of_configs_on_master) or\
                    (is_master is False and len(matrix[sr]) != nr_of_configs_on_extra):
                incorrect_nodes.append(sr.ip)
        assert len(incorrect_nodes) == 0, "Incorrect nr of configs on nodes: {0}".format(incorrect_nodes)

        md5sum_matrix = dict()
        incorrect_configs = list()
        for cfg in matrix[storagerouters[0]]:
            for sr in storagerouters:
                if cfg not in md5sum_matrix:
                    md5sum_matrix[cfg] = matrix[sr][cfg]
                elif matrix[sr][cfg] != md5sum_matrix[cfg]:
                    incorrect_configs.append("Incorrect contents {0} for {1} on {2}, expected {3}"
                                             .format(matrix[sr][cfg], sr.ip, cfg, md5sum_matrix[cfg]))

        assert len(incorrect_configs) == 0,\
            'Incorrect arakoon config contents: \n{0}'.format('\n'.join(incorrect_configs))

    @staticmethod
    def validate_arakoon_config_content(config_file, node_ids):
        """
        Validate the content of an arakoon configuration file
        :param config_file: Config to validate
        :param node_ids: IDs of the expected nodes
        :return: None
        """
        ips = node_ids.keys()
        ips.sort()

        contents = Configuration.get(config_file, raw=True)
        cfg = RawConfigParser()
        cfg.readfp(StringIO(contents))

        TestArakoon.logger.info('Arakoon config to validate:\n{0}'.format(str(contents)))

        cluster_id_from_filename = config_file.split('/')[-2]
        assert cfg.has_section('global'), 'Arakoon config {0} has no global section'.format(config_file)
        assert cfg.has_option('global', 'cluster'),\
            'Arakoon config {0} has no option cluster in global section'.format(config_file)

        cluster = list()
        for entry in cfg.get('global', 'cluster').split(','):
            cluster.append(entry)

        TestArakoon.logger.info('cluster: {0}'.format(cluster))
        TestArakoon.logger.info('node_ids: {0}'.format(node_ids))
        for node_id in node_ids.values():
            TestArakoon.logger.info('node_id: {0}'.format(node_id))
            assert node_id in cluster, 'Node id: {0} missing in global|cluster for {1}'.format(node_id, config_file)
            cluster.pop(cluster.index(node_id))
        assert not cluster, 'Cluster not empty, remaining values: {0}'.format(cluster)

        for cluster_ip, cluster_id in node_ids.iteritems():
            assert cfg.has_section(cluster_id),\
                'Missing section for id: {0} in {1}'.format(cluster_ip, config_file)
            assert cfg.has_option(cluster_id, 'ip'),\
                'Missing ip field in section {0} in {1}'.format(cluster_id, config_file)
            assert cluster_ip == cfg.get(cluster_id, 'ip'),\
                'Incorrect ip: {0} in section {1} for {2}, expected {3}'.format(cluster_ip, cluster_id, config_file,
                                                                                cfg.get(cluster_id, 'ip'))
            assert cfg.has_option(cluster_id, 'name'),\
                'No option name for cluster_id {0} in {1}'.format(cluster_id, config_file)
            assert cluster_id_from_filename == cfg.get('global', 'cluster_id'), \
                'Incorrect name {0} in section {1} for {2} expected: {3}'.format(cfg.get(cluster_id, 'name'),
                                                                                 cluster_id, config_file,
                                                                                 cluster_id_from_filename)

    #########
    # TESTS #
    #########

    @staticmethod
    def ar_0001_validate_create_extend_shrink_delete_cluster_test():
        """
        Validate extending and shrinking of arakoon clusters
        """
        storagerouters = GeneralStorageRouter.get_storage_routers()
        if not len(storagerouters) >= 3:
            TestArakoon.logger.info('Environment has only {0} node(s)'.format(len(storagerouters)))
            return

        cluster_name = 'ar_0001'
        cluster_basedir = '/var/tmp/'
        first_sr = storagerouters[0]
        second_sr = storagerouters[1]
        third_sr = storagerouters[2]
        first_root_client = SSHClient(first_sr, username='root')
        second_root_client = SSHClient(second_sr, username='root')
        third_root_client = SSHClient(third_sr, username='root')

        TestArakoon.logger.info('===================================================')
        TestArakoon.logger.info('setup and validate single node cluster')
        ArakoonInstaller.create_cluster(cluster_name, ServiceType.ARAKOON_CLUSTER_TYPES.FWK, first_sr.ip,
                                        cluster_basedir)
        TestArakoon.validate_arakoon_config_files([first_sr], cluster_name)
        TestArakoon.verify_arakoon_structure(first_root_client, cluster_name, True, True)

        TestArakoon.logger.info('===================================================')
        TestArakoon.logger.info('setup and validate two node cluster')
        ArakoonInstaller.extend_cluster(first_sr.ip, second_sr.ip, cluster_name, cluster_basedir)
        TestArakoon.validate_arakoon_config_files([first_sr, second_sr], cluster_name)
        TestArakoon.verify_arakoon_structure(first_root_client, cluster_name, True, True)
        TestArakoon.verify_arakoon_structure(second_root_client, cluster_name, True, True)

        TestArakoon.logger.info('===================================================')
        TestArakoon.logger.info('setup and validate three node cluster')
        ArakoonInstaller.extend_cluster(first_sr.ip, third_sr.ip, cluster_name, cluster_basedir)
        TestArakoon.validate_arakoon_config_files([first_sr, second_sr, third_sr], cluster_name)

        for client in [first_root_client, second_root_client, third_root_client]:
            TestArakoon.verify_arakoon_structure(client, cluster_name, True, True)

        TestArakoon.logger.info('===================================================')
        TestArakoon.logger.info('reduce and validate three node to two node cluster')
        ArakoonInstaller.shrink_cluster(second_sr.ip, first_sr.ip, cluster_name)
        TestArakoon.validate_arakoon_config_files([first_sr, third_sr], cluster_name)
        TestArakoon.verify_arakoon_structure(first_root_client, cluster_name, True, True)
        TestArakoon.verify_arakoon_structure(second_root_client, cluster_name, True, False)
        TestArakoon.verify_arakoon_structure(third_root_client, cluster_name, True, True)

        TestArakoon.logger.info('===================================================')
        TestArakoon.logger.info('reduce and validate two node to one node cluster')
        ArakoonInstaller.shrink_cluster(first_sr.ip, third_sr.ip, cluster_name)
        TestArakoon.validate_arakoon_config_files([third_sr], cluster_name)

        TestArakoon.verify_arakoon_structure(first_root_client, cluster_name, True, False)
        TestArakoon.verify_arakoon_structure(second_root_client, cluster_name, True, False)
        TestArakoon.verify_arakoon_structure(third_root_client, cluster_name, True, True)

        TestArakoon.logger.info('===================================================')
        TestArakoon.logger.info('remove cluster')
        ArakoonInstaller.delete_cluster(cluster_name, third_sr.ip)

        for client in [first_root_client, second_root_client, third_root_client]:
            TestArakoon.verify_arakoon_structure(client, cluster_name, False, False)

        GeneralArakoon.delete_config(cluster_name)

    @staticmethod
    def ar_0002_arakoon_cluster_validation_test():
        """
        Arakoon cluster validation
        """
        TestArakoon.validate_arakoon_config_files(GeneralStorageRouter.get_storage_routers())

    @staticmethod
    def ovs_3554_4_node_cluster_config_validation_test():
        """
        Arakoon config validation of a 4 node cluster
        """
        TestArakoon.validate_arakoon_config_files(GeneralStorageRouter.get_storage_routers())

    @staticmethod
    def ovs_3671_validate_archiving_of_existing_arakoon_data_on_create_test():
        """
        Validate arakoon archiving on extending a cluster with already existing data
        """
        first_sr = GeneralStorageRouter.get_storage_routers()[0]

        cluster_name = 'OVS_3671-single-node-cluster'
        cluster_basedir = '/var/tmp'

        root_client = SSHClient(first_sr, username='root')
        for directory in ['/'.join([cluster_basedir, 'arakoon']), '/var/log/arakoon']:
            root_client.dir_create(os.path.dirname(directory))
            root_client.dir_chmod(os.path.dirname(directory), 0755, recursive=True)
            root_client.dir_chown(os.path.dirname(directory), 'ovs', 'ovs', recursive=True)

        files_to_create = ['/'.join([cluster_basedir, 'arakoon', cluster_name, 'db', 'one.db']),
                           '/'.join([cluster_basedir, 'arakoon', cluster_name, 'tlogs', 'one.tlog'])]

        client = SSHClient(first_sr, username='ovs')
        for filename in files_to_create:
            client.dir_create(os.path.dirname(filename))
            client.dir_chmod(os.path.dirname(filename), 0755, recursive=True)
            client.dir_chown(os.path.dirname(filename), 'ovs', 'ovs', recursive=True)

        client.file_create(files_to_create)
        for filename in files_to_create:
            assert client.file_exists(filename) is True, 'File {0} not present'.format(filename)

        TestArakoon.logger.info('===================================================')
        TestArakoon.logger.info('setup and validate single node cluster')
        ArakoonInstaller.create_cluster(cluster_name, ServiceType.ARAKOON_CLUSTER_TYPES.FWK, first_sr.ip,
                                        cluster_basedir)
        TestArakoon.validate_arakoon_config_files([first_sr], cluster_name)
        TestArakoon.verify_arakoon_structure(root_client, cluster_name, True, True)
        for filename in files_to_create:
            assert client.file_exists(filename) is False, 'File {0} is missing'.format(filename)

        TestArakoon.logger.info('===================================================')
        TestArakoon.logger.info('remove cluster')
        ArakoonInstaller.delete_cluster(cluster_name, first_sr.ip)
        for filename in files_to_create:
            assert client.file_exists(filename) is False, 'File {0} is missing'.format(filename)
        TestArakoon.verify_arakoon_structure(root_client, cluster_name, False, False)

    @staticmethod
    def ovs_3671_validate_archiving_of_existing_arakoon_data_on_create_and_extend_test():
        """
        Validate arakoon archiving when creating and extending an arakoon cluster
        """
        storagerouters = GeneralStorageRouter.get_storage_routers()
        storagerouters.sort(key=lambda k: k.ip)
        if len(storagerouters) < 2:
            TestArakoon.logger.info('Environment has only {0} node(s)'.format(len(storagerouters)))
            return

        cluster_name = 'OVS_3671-multi-node-cluster'
        cluster_basedir = '/var/tmp'

        archived_files = []
        files_to_create = []
        for index, sr in enumerate(storagerouters):
            root_client = SSHClient(sr, username='root')
            for directory in ['/'.join([cluster_basedir, 'arakoon']), '/var/log/arakoon']:
                root_client.dir_create(os.path.dirname(directory))
                root_client.dir_chmod(os.path.dirname(directory), 0755, recursive=True)
                root_client.dir_chown(os.path.dirname(directory), 'ovs', 'ovs', recursive=True)

            files_to_create = ['/'.join([cluster_basedir, 'arakoon', cluster_name, 'db', 'one.db']),
                               '/'.join([cluster_basedir, 'arakoon', cluster_name, 'tlogs', 'one.tlog'])]

            client = SSHClient(sr, username='ovs')
            for filename in files_to_create:
                client.dir_create(os.path.dirname(filename))
                client.dir_chmod(os.path.dirname(filename), 0755, recursive=True)
                client.dir_chown(os.path.dirname(filename), 'ovs', 'ovs', recursive=True)

            client.file_create(files_to_create)
            for filename in files_to_create:
                assert client.file_exists(filename) is True, 'File {0} not present'.format(filename)

            archived_files = ['/'.join(['/var/log/arakoon', cluster_name, 'archive', 'one.log'])]

            TestArakoon.logger.info('===================================================')
            TestArakoon.logger.info('setup and validate single node cluster')
            if index == 0:
                ArakoonInstaller.create_cluster(cluster_name, ServiceType.ARAKOON_CLUSTER_TYPES.FWK, sr.ip,
                                                cluster_basedir)
            else:
                ArakoonInstaller.extend_cluster(storagerouters[0].ip, sr.ip, cluster_name, cluster_basedir)
            TestArakoon.validate_arakoon_config_files(storagerouters[:index + 1], cluster_name)
            TestArakoon.verify_arakoon_structure(root_client, cluster_name, True, True)
            TestArakoon.check_archived_directory(client, archived_files)
            for filename in files_to_create:
                assert client.file_exists(filename) is False, 'File {0} is missing'.format(filename)

        TestArakoon.logger.info('===================================================')
        TestArakoon.logger.info('remove cluster')
        ArakoonInstaller.delete_cluster(cluster_name, storagerouters[0].ip)

        for sr in storagerouters:
            client = SSHClient(sr, username='ovs')
            TestArakoon.check_archived_directory(client, archived_files)
            for filename in files_to_create:
                assert client.file_exists(filename) is False, 'File {0} is missing'.format(filename)
            TestArakoon.verify_arakoon_structure(client, cluster_name, False, False)

    @staticmethod
    def ovs_4509_validate_arakoon_collapse_test():
        """
        Validate arakoon collapse
        """
        node_ips = [sr.ip for sr in GeneralStorageRouter.get_storage_routers()]
        node_ips.sort()
        for node_ip in node_ips:
            root_client = SSHClient(node_ip, username='root')
            arakoon_clusters = []
            for service in ServiceList.get_services():
                if service.is_internal is True and service.storagerouter.ip == node_ip and \
                    service.type.name in (ServiceType.SERVICE_TYPES.ARAKOON,
                                          ServiceType.SERVICE_TYPES.NS_MGR,
                                          ServiceType.SERVICE_TYPES.ALBA_MGR):
                    arakoon_clusters.append(service.name.replace('arakoon-', ''))

            for arakoon_cluster in arakoon_clusters:
                arakoon_config_path = Configuration.get_configuration_path('/ovs/arakoon/{0}/config'.format(arakoon_cluster))
                tlog_location = '/opt/OpenvStorage/db/arakoon/{0}/tlogs'.format(arakoon_cluster)

                # read_tlog_dir
                with remote(node_ip, [Configuration]) as rem:
                    config_contents = rem.Configuration.get('/ovs/arakoon/{0}/config'.format(arakoon_cluster), raw=True)
                for line in config_contents.splitlines():
                    if 'tlog_dir' in line:
                        tlog_location = line.split()[-1]

                nr_of_tlogs = TestArakoon.get_nr_of_tlogs_in_folder(root_client, tlog_location)
                old_headdb_timestamp = 0
                if root_client.file_exists('/'.join([tlog_location, 'head.db'])):
                    old_headdb_timestamp = root_client.run(['stat', '--format=%Y', tlog_location + '/head.db'])
                if nr_of_tlogs <= 2:
                    benchmark_command = ['arakoon', '--benchmark', '-n_clients', '1', '-max_n', '5_000', '-config', arakoon_config_path]
                    root_client.run(benchmark_command)

                ScheduledTaskController.collapse_arakoon()

                nr_of_tlogs = TestArakoon.get_nr_of_tlogs_in_folder(root_client, tlog_location)
                new_headdb_timestamp = root_client.run(['stat', '--format=%Y', tlog_location + '/head.db'])
                assert nr_of_tlogs <= 2,\
                    'Arakoon collapse left {0} tlogs on the environment, expecting less than 2'.format(nr_of_tlogs)
                assert old_headdb_timestamp != new_headdb_timestamp,\
                    'Timestamp of the head_db file was not changed in the process of collapsing tlogs'
