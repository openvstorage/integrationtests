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

# arakoon cluster setup
#
# DB role on node determines if cluster will be extended to that node
#
# possible arakoon clusters:
# - ovsdb
# - voldrv
# - abm
# - nsm_0 - controlled by voldrv
#
# promote will extend cluster / demote will reduce cluster
#

"""
Arakoon testsuite
"""

import os
import re
import hashlib
from ci.tests.general.general import General
from ci.tests.general.general_arakoon import GeneralArakoon
from ci.tests.general.general_pmachine import GeneralPMachine
from ci.tests.general.general_storagerouter import GeneralStorageRouter
from ci.tests.general.logHandler import LogHandler
from ConfigParser import RawConfigParser
from ovs.dal.hybrids.servicetype import ServiceType
from ovs.extensions.db.arakoon.ArakoonInstaller import ArakoonInstaller
from ovs.extensions.db.etcd.configuration import EtcdConfiguration
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.generic.system import System
from ovs.lib.scheduledtask import ScheduledTaskController
from StringIO import StringIO

logger = LogHandler.get('arakoon', name='setup')
logger.logger.propagate = False


class TestArakoon(object):
    """
    Arakoon testsuite
    """

    ####################
    # HELPER FUNCTIONS #
    ####################

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
                    out = client.run('tar -tf {0}/{1}'.format(archived_directory, file_name))
                    if archived_file_name in out:
                        file_found = True
            if file_found is False:
                return False
        return True

    @staticmethod
    def get_cluster_pmachines(ips):
        """
        Retrieve Physical Machine information
        :param ips: IPs to retrieve information for
        :return: Dictionary with IP and Physical Machine information
        """
        pmachines_to_check = dict()
        for ip in ips:
            pmachines_to_check[ip] = GeneralPMachine.get_pmachine_by_ip(ip)
        return pmachines_to_check

    @staticmethod
    def verify_arakoon_structure(client, cluster_name, etcd_present, dir_present):
        """
        Verify the expected arakoon structure and etcd configuration
        :param client: SSHClient object
        :param cluster_name: Name of the arakoon cluster
        :param etcd_present: Etcd configuration presence expectancy
        :param dir_present: Directory structure presence expectancy
        :return: True if correct
        """
        log_dir = GeneralArakoon.LOG_DIR.format(cluster_name)
        tlog_dir = GeneralArakoon.TLOG_DIR.format('/var/tmp', cluster_name)
        home_dir = GeneralArakoon.HOME_DIR.format('/var/tmp', cluster_name)

        key_exists = EtcdConfiguration.exists(GeneralArakoon.ETCD_CONFIG_KEY.format(cluster_name), raw = True)
        assert key_exists is etcd_present, "Arakoon configuration in Etcd was {0}expected".format('' if etcd_present else 'not ')
        for directory in [tlog_dir, home_dir, log_dir]:
            assert client.dir_exists(directory) is dir_present, "Arakoon directory {0} was {1}expected".format(directory, '' if dir_present else 'not ')

    @staticmethod
    def validate_arakoon_config_files(pmachines, config=None):
        """
        Verify whether all arakoon configurations are correct
        :param pmachines: Physical Machine information
        :param config: Arakoon config
        :return:
        """
        ips = pmachines.keys()
        ips.sort()
        logger.info('Validating arakoon files for {0}'.format(ips))
        if not ips:
            return False

        nr_of_configs_on_master = 0
        nr_of_configs_on_extra = 0

        node_ids = dict()
        extra_ips = list()
        matrix = dict()
        for ip in ips:
            node_type = pmachines[ip].storagerouters[0].node_type
            if node_type == 'MASTER':
                out = General.execute_command_on_node(ip, 'cat /etc/openvstorage_id')
                node_ids[ip] = out
            else:
                extra_ips.append(ip)
            configs_to_check = []
            matrix[ip] = dict()
            if config:
                if EtcdConfiguration.exists(GeneralArakoon.ETCD_CONFIG_KEY.format(config), raw = True):
                    configs_to_check = [GeneralArakoon.ETCD_CONFIG_KEY.format(config)]
            else:
                gen = EtcdConfiguration.list(GeneralArakoon.ETCD_CONFIG_ROOT)
                for entry in gen:
                    if 'nsm_' not in entry:
                        if EtcdConfiguration.exists(GeneralArakoon.ETCD_CONFIG_KEY.format(config), raw = True):
                            configs_to_check.append(GeneralArakoon.ETCD_CONFIG_KEY.format(entry))
            for config_name in configs_to_check:
                config_contents = EtcdConfiguration.get(configs_to_check[0], raw = True)
                matrix[ip][config_name] = hashlib.md5(config_contents).hexdigest()
            if node_type == 'MASTER':
                nr_of_configs_on_master = len(matrix[ip])
            else:
                nr_of_configs_on_extra = len(matrix[ip])

        logger.info('cluster_ids: {0}'.format(node_ids))
        logger.info('matrix: {0}'.format(matrix))

        for config_file in matrix[ips[0]].keys():
            TestArakoon.validate_arakoon_config_content(config_file, node_ids)

        assert len(ips) == len(matrix.keys()), "not all nodes have arakoon configs"
        incorrect_nodes = list()
        for ip in matrix.keys():
            is_master = pmachines[ip].storagerouters[0].node_type == 'MASTER'
            if (is_master is True and len(matrix[ip]) != nr_of_configs_on_master) or\
                    (is_master is False and len(matrix[ip]) != nr_of_configs_on_extra):
                incorrect_nodes.append(ip)
        assert len(incorrect_nodes) == 0, "Incorrect nr of configs on nodes: {0}".format(incorrect_nodes)

        md5sum_matrix = dict()
        incorrect_configs = list()
        for cfg in matrix[ips[0]]:
            for ip in ips:
                if cfg not in md5sum_matrix:
                    md5sum_matrix[cfg] = matrix[ip][cfg]
                elif matrix[ip][cfg] != md5sum_matrix[cfg]:
                    incorrect_configs.append("Incorrect contents {0} for {1} on {2}, expected {3}"
                                             .format(matrix[ip][cfg], ip, cfg, md5sum_matrix[cfg]))

        assert len(incorrect_configs) == 0, 'Incorrect arakoon config contents: \n{0}'.format('\n'.join(incorrect_configs))

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

        contents = EtcdConfiguration.get(config_file, raw = True)
        cfg = RawConfigParser()
        cfg.readfp(StringIO(contents))

        logger.info('Arakoon config to validate:\n{0}'.format(str(contents)))

        cluster_id_from_filename = config_file.split('/')[-2]
        assert cfg.has_section('global'), 'Arakoon config {0} has no global section'.format(config_file)
        assert cfg.has_option('global', 'cluster'), 'Arakoon config {0} has no option cluster in global section'.format(config_file)

        cluster = list()
        for entry in cfg.get('global', 'cluster').split(','):
            cluster.append(entry)

        logger.info('cluster: {0}'.format(cluster))
        logger.info('node_ids: {0}'.format(node_ids))
        for node_id in node_ids.values():
            logger.info('node_id: {0}'.format(node_id))
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
                'Incorrect name {0} in section {1} for {2} expected: {3}'.format(cfg.get(cluster_id, 'name'), cluster_id,
                                                                                 config_file, cluster_id_from_filename)

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
            logger.info('Environment has only {0} node(s)'.format(len(storagerouters)))
            return

        node_ips = [sr.ip for sr in storagerouters]
        node_ips.sort()

        cluster_name = 'ar_0001'
        cluster_basedir = '/var/tmp/'
        first_ip = node_ips[0]
        second_ip = node_ips[1]
        third_ip = node_ips[2]
        first_root_client = SSHClient(first_ip, username='root')
        second_root_client = SSHClient(second_ip, username='root')
        third_root_client = SSHClient(third_ip, username='root')

        logger.info('===================================================')
        logger.info('setup and validate single node cluster')
        ArakoonInstaller.create_cluster(cluster_name, ServiceType.ARAKOON_CLUSTER_TYPES.FWK, first_ip, cluster_basedir)
        TestArakoon.validate_arakoon_config_files(TestArakoon.get_cluster_pmachines([first_ip]), cluster_name)
        TestArakoon.verify_arakoon_structure(first_root_client, cluster_name, True, True)

        logger.info('===================================================')
        logger.info('setup and validate two node cluster')
        ArakoonInstaller.extend_cluster(first_ip, second_ip, cluster_name, cluster_basedir)
        TestArakoon.validate_arakoon_config_files(TestArakoon.get_cluster_pmachines([first_ip, second_ip]), cluster_name)
        TestArakoon.verify_arakoon_structure(first_root_client, cluster_name, True, True)
        TestArakoon.verify_arakoon_structure(second_root_client, cluster_name, True, True)

        logger.info('===================================================')
        logger.info('setup and validate three node cluster')
        ArakoonInstaller.extend_cluster(first_ip, third_ip, cluster_name, cluster_basedir)
        TestArakoon.validate_arakoon_config_files(TestArakoon.get_cluster_pmachines([first_ip, second_ip, third_ip]), cluster_name)

        for client in [first_root_client, second_root_client, third_root_client]:
            TestArakoon.verify_arakoon_structure(client, cluster_name, True, True)

        logger.info('===================================================')
        logger.info('reduce and validate three node to two node cluster')
        ArakoonInstaller.shrink_cluster(second_ip, cluster_name)
        TestArakoon.validate_arakoon_config_files(TestArakoon.get_cluster_pmachines([first_ip, third_ip]), cluster_name)
        TestArakoon.verify_arakoon_structure(first_root_client, cluster_name, True, True)
        TestArakoon.verify_arakoon_structure(second_root_client, cluster_name, True, False)
        TestArakoon.verify_arakoon_structure(third_root_client, cluster_name, True, True)

        logger.info('===================================================')
        logger.info('reduce and validate two node to one node cluster')
        ArakoonInstaller.shrink_cluster(first_ip, cluster_name)
        TestArakoon.validate_arakoon_config_files(TestArakoon.get_cluster_pmachines([third_ip]), cluster_name)

        TestArakoon.verify_arakoon_structure(first_root_client, cluster_name, True, False)
        TestArakoon.verify_arakoon_structure(second_root_client, cluster_name, True, False)
        TestArakoon.verify_arakoon_structure(third_root_client, cluster_name, True, True)

        logger.info('===================================================')
        logger.info('remove cluster')
        ArakoonInstaller.delete_cluster(cluster_name, third_ip)

        for client in [first_root_client, second_root_client, third_root_client]:
            TestArakoon.verify_arakoon_structure(client, cluster_name, False, False)

        GeneralArakoon.delete_etcd_config(cluster_name)

    @staticmethod
    def ar_0002_arakoon_cluster_validation_test():
        """
        Arakoon cluster validation
        """
        storagerouters = GeneralStorageRouter.get_storage_routers()
        if not len(storagerouters) >= 2:
            logger.info('Environment has only {0} node(s)'.format(len(storagerouters)))
            return

        pmachines = TestArakoon.get_cluster_pmachines([sr.ip for sr in storagerouters])
        TestArakoon.validate_arakoon_config_files(pmachines)

    @staticmethod
    def ovs_3554_4_node_cluster_config_validation_test():
        """
        Arakoon config validation of a 4 node cluster
        """
        storagerouters = GeneralStorageRouter.get_storage_routers()
        if not len(storagerouters) >= 4:
            logger.info('Environment has only {0} node(s)'.format(len(storagerouters)))
            return

        pmachines = TestArakoon.get_cluster_pmachines([sr.ip for sr in storagerouters])
        TestArakoon.validate_arakoon_config_files(pmachines)

    @staticmethod
    def ovs_3671_validate_archiving_of_existing_arakoon_data_on_create_test():
        """
        Validate arakoon archiving on extending a cluster with already existing data
        """
        node_ips = [sr.ip for sr in GeneralStorageRouter.get_storage_routers()]
        node_ips.sort()

        cluster_name = 'OVS_3671-single-node-cluster'
        cluster_basedir = '/var/tmp'
        first_ip = node_ips[0]

        root_client = SSHClient(first_ip, username='root')
        for directory in ['/'.join([cluster_basedir, 'arakoon']), '/var/log/arakoon']:
            root_client.dir_create(os.path.dirname(directory))
            root_client.dir_chmod(os.path.dirname(directory), 0755, recursive=True)
            root_client.dir_chown(os.path.dirname(directory), 'ovs', 'ovs', recursive=True)

        files_to_create = ['/'.join([cluster_basedir, 'arakoon', cluster_name, 'db', 'one.db']),
                           '/'.join([cluster_basedir, 'arakoon', cluster_name, 'tlogs', 'one.tlog']),
                           '/'.join(['/var/log', 'arakoon', cluster_name, 'one.log'])]

        client = SSHClient(first_ip, username='ovs')
        for filename in files_to_create:
            client.dir_create(os.path.dirname(filename))
            client.dir_chmod(os.path.dirname(filename), 0755, recursive=True)
            client.dir_chown(os.path.dirname(filename), 'ovs', 'ovs', recursive=True)

        client.file_create(files_to_create)
        for filename in files_to_create:
            assert client.file_exists(filename) is True, 'File {0} not present'.format(filename)

        archived_files = ['/'.join(['/var/log/arakoon', cluster_name, 'archive', 'one.log'])]

        logger.info('===================================================')
        logger.info('setup and validate single node cluster')
        ArakoonInstaller.create_cluster(cluster_name, ServiceType.ARAKOON_CLUSTER_TYPES.FWK, first_ip, cluster_basedir)
        TestArakoon.validate_arakoon_config_files(TestArakoon.get_cluster_pmachines([first_ip]), cluster_name)
        TestArakoon.verify_arakoon_structure(root_client, cluster_name, True, True)
        TestArakoon.check_archived_directory(client, archived_files)
        for filename in files_to_create:
            assert client.file_exists(filename) is False, 'File {0} is missing'.format(filename)

        logger.info('===================================================')
        logger.info('remove cluster')
        ArakoonInstaller.delete_cluster(cluster_name, first_ip)
        TestArakoon.check_archived_directory(client, archived_files)
        for filename in files_to_create:
            assert client.file_exists(filename) is False, 'File {0} is missing'.format(filename)
        TestArakoon.verify_arakoon_structure(root_client, cluster_name, False, False)

    @staticmethod
    def ovs_3671_validate_archiving_of_existing_arakoon_data_on_create_and_extend_test():
        """
        Validate arakoon archiving when creating and extending an arakoon cluster
        """
        node_ips = [sr.ip for sr in GeneralStorageRouter.get_storage_routers()]
        node_ips.sort()
        first_ip = node_ips[0]

        if len(node_ips) < 2:
            logger.info('Environment has only {0} node(s)'.format(len(node_ips)))
            return

        cluster_name = 'OVS_3671-multi-node-cluster'
        cluster_basedir = '/var/tmp'
        ips_to_validate = []

        archived_files = []
        files_to_create = []
        for ip in node_ips:
            ips_to_validate.append(ip)
            root_client = SSHClient(ip, username='root')
            for directory in ['/'.join([cluster_basedir, 'arakoon']), '/var/log/arakoon']:
                root_client.dir_create(os.path.dirname(directory))
                root_client.dir_chmod(os.path.dirname(directory), 0755, recursive=True)
                root_client.dir_chown(os.path.dirname(directory), 'ovs', 'ovs', recursive=True)

            files_to_create = ['/'.join([cluster_basedir, 'arakoon', cluster_name, 'db', 'one.db']),
                               '/'.join([cluster_basedir, 'arakoon', cluster_name, 'tlogs', 'one.tlog']),
                               '/'.join(['/var/log', 'arakoon', cluster_name, 'one.log'])]

            client = SSHClient(ip, username='ovs')
            for filename in files_to_create:
                client.dir_create(os.path.dirname(filename))
                client.dir_chmod(os.path.dirname(filename), 0755, recursive=True)
                client.dir_chown(os.path.dirname(filename), 'ovs', 'ovs', recursive=True)

            client.file_create(files_to_create)
            for filename in files_to_create:
                assert client.file_exists(filename) is True, 'File {0} not present'.format(filename)

            archived_files = ['/'.join(['/var/log/arakoon', cluster_name, 'archive', 'one.log'])]

            logger.info('===================================================')
            logger.info('setup and validate single node cluster')
            if ip == first_ip:
                ArakoonInstaller.create_cluster(cluster_name, ServiceType.ARAKOON_CLUSTER_TYPES.FWK, ip, cluster_basedir)
            else:
                ArakoonInstaller.extend_cluster(first_ip, ip, cluster_name, cluster_basedir)
            TestArakoon.validate_arakoon_config_files(TestArakoon.get_cluster_pmachines(ips_to_validate), cluster_name)
            TestArakoon.verify_arakoon_structure(root_client, cluster_name, True, True)
            TestArakoon.check_archived_directory(client, archived_files)
            for filename in files_to_create:
                assert client.file_exists(filename) is False, 'File {0} is missing'.format(filename)

        logger.info('===================================================')
        logger.info('remove cluster')
        ArakoonInstaller.delete_cluster(cluster_name, first_ip)

        for ip in node_ips:
            client = SSHClient(ip, username='ovs')
            TestArakoon.check_archived_directory(client, archived_files)
            for filename in files_to_create:
                assert client.file_exists(filename) is False, 'File {0} is missing'.format(filename)
            TestArakoon.verify_arakoon_structure(client, cluster_name, False, False)

    @staticmethod
    def ovs_4509_validate_arakoon_collapse_test():
        """
        Validate arakoon collapse
        """
        arakoon_conf_file = '/etc/init/ovs-arakoon-ovsdb.conf'
        etcd_config = 'etcd://127.0.0.1:2379/ovs/arakoon/ovsdb/config'
        tlog_location = '/opt/OpenvStorage/db/arakoon/ovsdb/tlogs'
        first_ip = System.get_my_storagerouter().ip
        root_client = SSHClient(first_ip, username='root')
        # read_conf_settings
        conf_contents = root_client.file_read(arakoon_conf_file)
        for split_item in conf_contents.splitlines()[-1].split():
            if 'etcd' in split_item:
                etcd_config = split_item
        # read_tlog_dir
        etcd_arakoon_conf = re.findall('\d+|\D+', etcd_config)[-1]
        etcd_contents = root_client.run('etcdctl get {0}'.format(etcd_arakoon_conf))
        for line in etcd_contents.splitlines():
            if 'tlog_dir' in line:
                tlog_location = line.split()[-1]

        nr_of_tlogs = TestArakoon.get_nr_of_tlogs_in_folder(root_client, tlog_location)
        old_headdb_timestamp = 0
        if root_client.file_exists('/'.join([tlog_location, 'head.db'])):
            old_headdb_timestamp = root_client.run('stat --format=%Y {0}/{1}'.format(tlog_location, 'head.db'))
        if nr_of_tlogs <= 2:
            # run_arakoon_benchmark
            benchmark_command = 'arakoon --benchmark -n_clients 1 -max_n 10_000 -config {0}'.format(etcd_config)
            root_client.run(benchmark_command)
        # run_collapse
        ScheduledTaskController.collapse_arakoon()

        nr_of_tlogs = TestArakoon.get_nr_of_tlogs_in_folder(root_client, tlog_location)
        new_headdb_timestamp = root_client.run('stat --format=%Y {0}/{1}'.format(tlog_location, 'head.db'))
        assert nr_of_tlogs <= 2, 'Arakoon collapse left {0} tlogs on the environment, expecting less than 2'.format(nr_of_tlogs)
        assert old_headdb_timestamp != new_headdb_timestamp, 'Timestamp of the head_db file was not changed in the process of collapsing tlogs'
