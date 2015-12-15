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

from ConfigParser import RawConfigParser

from ci.tests.backend import alba, generic
from ci.tests.disklayout import disklayout
from ci.tests.general import general
from ci.tests.general import general_ovs
from ci.tests.general.logHandler import LogHandler
from nose.plugins.skip import SkipTest
from nose.tools import assert_raises, assert_false, assert_true
from ovs.extensions.db.arakoon.ArakoonInstaller import ArakoonInstaller, ArakoonClusterConfig
from ovs.extensions.generic.sshclient import SSHClient
from ovs.lib.storagedriver import StorageDriverController

import os
from StringIO import StringIO


logger = LogHandler.get('arakoon', name='setup')
logger.logger.propagate = False

BACKEND_NAME = 'AUTOTEST_ALBA'
BACKEND_TYPE = 'alba'
PMACHINES = general_ovs.get_pmachines_by_ip()
MASTER_IPS = [ip for ip in PMACHINES.keys() if PMACHINES[ip]['node_type'] == 'MASTER']
MASTER_IPS.sort()

BASE_DIR = '/var/tmp'

TEST_CLEANUP = ['{0}/arakoon/OVS*'.format(BASE_DIR), '/etc/init/ovs-arakoon-OVS_*',
                '/opt/OpenvStorage/config/arakoon/OVS*', '/var/log/arakoon/ar_00*', '/var/log/arakoon/OVS_*',
                '{0}/arakoon/archive*'.format(BASE_DIR), '/var/log/arakoon/archive*',
                '{0}/arakoon/ar_00*'.format(BASE_DIR)]


def are_files_present_on(client, files):
    for filename in files:
        assert client.file_exists(filename) == True, 'File {0} not present'.format(filename)


def are_files_missing_on(client, files):
    for filename in files:
        assert client.file_exists(filename) == False, 'File {0} is missing'.format(filename)


def get_cluster_pmachines(ips):
    pmachines_to_check = dict()
    for ip in ips:
        pmachines_to_check[ip] = PMACHINES.get(ip)
    return pmachines_to_check


def setup():
    logger.info('setup alba backend')

    if generic.is_backend_present(BACKEND_NAME, BACKEND_TYPE):
        backend = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
        alba.remove_alba_backend(backend['alba_backend_guid'])

    for ip in MASTER_IPS:
        cmd = 'status ovs-scheduled-tasks'
        output = general.execute_command_on_node(ip, cmd)
        if 'running' in output:
            cmd = 'stop ovs-scheduled-tasks'
            general.execute_command_on_node(ip, cmd)

    for ip in PMACHINES.keys():
        storagerouter = general_ovs.get_storagerouter_by_ip(ip)
        disklayout.add_db_role(storagerouter['guid'])

        for location in TEST_CLEANUP:
            cmd = 'rm -rf {0}'.format(location)
            general.execute_command_on_node(ip, cmd)

    _ = alba.add_alba_backend(BACKEND_NAME)
    logger.info('running voldrv arakoon checkup ...')
    StorageDriverController.manual_voldrv_arakoon_checkup()

    logger.info('validating arakoon config files on all nodes ...')
    validate_arakoon_config_files(PMACHINES)


def teardown():
    if generic.is_backend_present(BACKEND_NAME, BACKEND_TYPE):
        backend = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
        alba.remove_alba_backend(backend['alba_backend_guid'])

    for ip in MASTER_IPS:
        cmd = 'status ovs-scheduled-tasks'
        output = general.execute_command_on_node(ip, cmd)
        if 'stop/waiting' in output:
            cmd = 'start ovs-scheduled-tasks'
            general.execute_command_on_node(ip, cmd)

        for location in TEST_CLEANUP:
            cmd = 'rm -rf {0}'.format(location)
            general.execute_command_on_node(ip, cmd)


def is_arakoon_dir_config_structure_cleaned_up(ip, cluster_name, base_dir='/mnt/storage'):
    config_dir = ArakoonClusterConfig.ARAKOON_CONFIG_DIR.format(cluster_name)
    config_file = ArakoonClusterConfig.ARAKOON_CONFIG_FILE.format(cluster_name)
    tlog_dir = ArakoonInstaller.ARAKOON_TLOG_DIR.format(base_dir, cluster_name)
    log_dir = ArakoonInstaller.ARAKOON_LOG_DIR.format(cluster_name)
    home_dir = ArakoonInstaller.ARAKOON_HOME_DIR.format(base_dir, cluster_name)

    client = SSHClient(ip, username='root')
    assert_false(client.file_exists(config_file)),\
        "Arakoon config file {0} still exists on {1}".format(config_file, ip)
    for directory in [config_dir, tlog_dir, home_dir, log_dir]:
        assert_false(client.dir_exists(directory)),\
            "Arakoon directory {0} still exists on {1}".format(config_file, ip)


def is_arakoon_dir_config_structure_client_only(ip, cluster_name, base_dir='/mnt/storage'):
    config_file = ArakoonClusterConfig.ARAKOON_CONFIG_FILE.format(cluster_name)
    tlog_dir = ArakoonInstaller.ARAKOON_TLOG_DIR.format(base_dir, cluster_name)
    log_dir = ArakoonInstaller.ARAKOON_LOG_DIR.format(cluster_name)
    home_dir = ArakoonInstaller.ARAKOON_HOME_DIR.format(base_dir, cluster_name)

    client = SSHClient(ip)
    assert client.file_exists(config_file) == True,\
        "Arakoon config file {0} no longer exists on {1}".format(config_file, ip)

    for directory in [tlog_dir, home_dir, log_dir]:
        assert_false(client.dir_exists(directory)),\
            "Arakoon directory {0} still exists on {1}".format(config_file, ip)


def is_arakoon_dir_config_structure_present(ip, cluster_name, base_dir='/mnt/storage'):
    config_dir = ArakoonClusterConfig.ARAKOON_CONFIG_DIR.format(cluster_name)
    config_file = ArakoonClusterConfig.ARAKOON_CONFIG_FILE.format(cluster_name)
    tlog_dir = ArakoonInstaller.ARAKOON_TLOG_DIR.format(base_dir, cluster_name)
    log_dir = ArakoonInstaller.ARAKOON_LOG_DIR.format(cluster_name)
    home_dir = ArakoonInstaller.ARAKOON_HOME_DIR.format(base_dir, cluster_name)

    client = SSHClient(ip, username='ovs')
    assert_true(client.file_exists(config_file)),\
        "Arakoon config file {0} still exists on {1}".format(config_file, ip)
    for directory in [config_dir, tlog_dir, home_dir, log_dir]:
        assert_true(client.dir_exists(directory)),\
            "Arakoon directory {0} still exists on {1}".format(config_file, ip)


def cleanup_arakoon_client_config_files(ips, cluster_name):
    config_dir = ArakoonClusterConfig.ARAKOON_CONFIG_DIR.format(cluster_name)
    for ip in ips:
        client = SSHClient(ip, username='ovs')
        client.dir_delete(config_dir)


def validate_arakoon_config_content(config_file, node_ids):
    ips = node_ids.keys()
    ips.sort()

    first_ip = ips[0]
    client = SSHClient(first_ip, username='root')
    contents = client.file_read(config_file)
    cfg = RawConfigParser()
    cfg.readfp(StringIO(contents))

    logger.info('Arakoon config to validate:\n{0}'.format(str(contents)))

    cluster_id_from_filename = os.path.basename(os.path.splitext(config_file)[0])
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


def validate_arakoon_config_files(pmachines, path=None, config=None):
    def is_master_node(node_ip):
        return pmachines[node_ip]['node_type'] == 'MASTER'

    ips = pmachines.keys()
    ips.sort()
    if not ips:
        return False

    nr_of_configs_on_master = 0
    nr_of_configs_on_extra = 0

    node_ids = dict()
    extra_ips = list()
    matrix = dict()
    for ip in ips:
        if pmachines[ip]['node_type'] == 'MASTER':
            cmd = 'cat /etc/openvstorage_id'
            out = general.execute_command_on_node(ip, cmd)
            node_ids[ip] = out
        else:
            extra_ips.append(ip)

        matrix[ip] = dict()
        if path and config:
            cmd = "/usr/bin/find {0} -type f -name {1}.cfg".format(path, config) + " -exec md5sum {} \;"
        else:
            cmd = """/usr/bin/find /opt/OpenvStorage/config/arakoon -type f -name *.cfg -exec md5sum {} \;"""
        logger.info("validate cmd: {0}".format(cmd))
        out = general.execute_command_on_node(ip, cmd)
        for entry in out.splitlines():
            md5_sum, filename = entry.split()
            if 'nsm_' not in filename:
                matrix[ip][filename] = md5_sum
        if is_master_node(ip):
            nr_of_configs_on_master = len(matrix[ip])
        else:
            nr_of_configs_on_extra = len(matrix[ip])

    logger.info('cluster_ids: {0}'.format(node_ids))
    logger.info('matrix: {0}'.format(matrix))

    for config_file in matrix[ips[0]].keys():
        validate_arakoon_config_content(config_file, node_ids)

    assert len(ips) == len(matrix.keys()), "not all nodes have arakoon configs"
    incorrect_nodes = list()
    for ip in matrix.keys():
        if (is_master_node(ip) and len(matrix[ip]) != nr_of_configs_on_master) or\
                (not is_master_node(ip) and len(matrix[ip]) != nr_of_configs_on_extra):
            incorrect_nodes.append(ip)
    assert len(incorrect_nodes) == 0, "Incorrect nr of configs on nodes: {0}".format(incorrect_nodes)

    md5_matrix = dict()
    incorrect_configs = list()
    for cfg in matrix[ips[0]]:
        for ip in ips:
            # nsm configs are not present on extra nodes
            if ip in extra_ips and 'nsm_' in cfg:
                continue
            if cfg not in md5_matrix:
                md5_matrix[cfg] = matrix[ip][cfg]
            elif matrix[ip][cfg] != md5_matrix[cfg]:
                incorrect_configs.append("Incorrect contents {0} for {1} on {2}, expected {3}"
                                         .format(matrix[ip][cfg], ip, cfg, md5_matrix[cfg]))

    assert len(incorrect_configs) == 0, 'Incorrect arakoon config contents: \n{0}'.format('\n'.join(incorrect_configs))


def ar_0001_validate_create_extend_shrink_delete_cluster_test():
    if not len(PMACHINES) >= 3:
        raise SkipTest()

    node_ips = [ip for ip in PMACHINES.keys()]
    node_ips.sort()

    cluster_name = 'ar_0001'
    cluster_basedir = '/var/tmp/'
    first_ip = node_ips[0]
    second_ip = node_ips[1]
    third_ip = node_ips[2]

    logger.info('===================================================')
    logger.info('setup and validate single node cluster')
    ArakoonInstaller.create_cluster(cluster_name, first_ip, [], cluster_basedir)
    validate_arakoon_config_files(get_cluster_pmachines([first_ip]), cluster_basedir, cluster_name)
    is_arakoon_dir_config_structure_present(first_ip, cluster_name, cluster_basedir)

    logger.info('===================================================')
    logger.info('setup and validate two node cluster')
    ArakoonInstaller.extend_cluster(first_ip, second_ip, cluster_name, [], cluster_basedir)
    validate_arakoon_config_files(get_cluster_pmachines([first_ip, second_ip]), cluster_basedir, cluster_name)
    is_arakoon_dir_config_structure_present(first_ip, cluster_name, cluster_basedir)
    is_arakoon_dir_config_structure_present(second_ip, cluster_name, cluster_basedir)

    logger.info('===================================================')
    logger.info('setup and validate three node cluster')
    ArakoonInstaller.extend_cluster(first_ip, third_ip, cluster_name, [], cluster_basedir)
    validate_arakoon_config_files(get_cluster_pmachines([first_ip, second_ip, third_ip]), cluster_basedir, cluster_name)
    is_arakoon_dir_config_structure_present(first_ip, cluster_name, cluster_basedir)
    is_arakoon_dir_config_structure_present(second_ip, cluster_name, cluster_basedir)
    is_arakoon_dir_config_structure_present(third_ip, cluster_name, cluster_basedir)

    logger.info('===================================================')
    logger.info('reduce and validate three node to two node cluster')
    ArakoonInstaller.shrink_cluster(first_ip, second_ip, cluster_name)
    validate_arakoon_config_files(get_cluster_pmachines([first_ip, third_ip]), cluster_basedir, cluster_name)
    is_arakoon_dir_config_structure_present(first_ip, cluster_name, cluster_basedir)
    is_arakoon_dir_config_structure_client_only(second_ip, cluster_name, cluster_basedir)
    is_arakoon_dir_config_structure_present(third_ip, cluster_name, cluster_basedir)

    logger.info('===================================================')
    logger.info('reduce and validate two node to one node cluster')
    ArakoonInstaller.shrink_cluster(third_ip, first_ip, cluster_name)
    validate_arakoon_config_files(get_cluster_pmachines([third_ip]), cluster_basedir, cluster_name)
    is_arakoon_dir_config_structure_client_only(first_ip, cluster_name, cluster_basedir)
    is_arakoon_dir_config_structure_client_only(second_ip, cluster_name, cluster_basedir)
    is_arakoon_dir_config_structure_present(third_ip, cluster_name, cluster_basedir)

    logger.info('===================================================')
    logger.info('remove cluster')
    ArakoonInstaller.delete_cluster(cluster_name, third_ip)
    is_arakoon_dir_config_structure_client_only(first_ip, cluster_name, cluster_basedir)
    is_arakoon_dir_config_structure_client_only(second_ip, cluster_name, cluster_basedir)
    is_arakoon_dir_config_structure_cleaned_up(third_ip, cluster_name, cluster_basedir)

    cleanup_arakoon_client_config_files([first_ip, second_ip], cluster_name)


def ar_0002_arakoon_cluster_validation_test():
    if not len(PMACHINES) >= 2:
        raise SkipTest()

    validate_arakoon_config_files(PMACHINES)


def ovs_3554_4_node_cluster_config_validation_test():
    if not len(PMACHINES) >= 4:
        raise SkipTest()

    validate_arakoon_config_files(PMACHINES)


def ovs_3671_validate_archiving_of_existing_arakoon_data_on_create_test():

    node_ips = [ip for ip in PMACHINES.keys()]
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
    are_files_present_on(client, files_to_create)

    archived_files = ['/'.join([cluster_basedir, 'arakoon', 'archive', cluster_name, 'db', 'one.db']),
                      '/'.join([cluster_basedir, 'arakoon', 'archive', cluster_name, 'tlogs', 'one.tlog']),
                      '/'.join(['/var/log', 'arakoon', 'archive', cluster_name, 'one.log'])]

    logger.info('===================================================')
    logger.info('setup and validate single node cluster')
    ArakoonInstaller.create_cluster(cluster_name, first_ip, [], cluster_basedir)
    validate_arakoon_config_files(get_cluster_pmachines([first_ip]), cluster_basedir, cluster_name)
    is_arakoon_dir_config_structure_present(first_ip, cluster_name, cluster_basedir)
    are_files_present_on(client, archived_files)
    are_files_missing_on(client, files_to_create)

    logger.info('===================================================')
    logger.info('remove cluster')
    ArakoonInstaller.delete_cluster(cluster_name, first_ip)
    are_files_present_on(client, archived_files)
    are_files_missing_on(client, files_to_create)
    is_arakoon_dir_config_structure_cleaned_up(first_ip, cluster_name, cluster_basedir)


def ovs_3671_validate_archiving_of_existing_arakoon_data_on_create_and_extend_test():

    node_ips = [ip for ip in PMACHINES.keys()]
    node_ips.sort()
    first_ip = node_ips[0]

    if len(node_ips) < 2:
        raise SkipTest()

    cluster_name = 'OVS_3671-multi-node-cluster'
    cluster_basedir = '/var/tmp'

    for ip in node_ips:
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
        are_files_present_on(client, files_to_create)

        archived_files = ['/'.join([cluster_basedir, 'arakoon', 'archive', cluster_name, 'db', 'one.db']),
                          '/'.join([cluster_basedir, 'arakoon', 'archive', cluster_name, 'tlogs', 'one.tlog']),
                          '/'.join(['/var/log', 'arakoon', 'archive', cluster_name, 'one.log'])]

        logger.info('===================================================')
        logger.info('setup and validate single node cluster')
        if ip == first_ip:
            ArakoonInstaller.create_cluster(cluster_name, ip, [], cluster_basedir)
        else:
            ArakoonInstaller.extend_cluster(first_ip, ip, cluster_name, [], cluster_basedir)
        validate_arakoon_config_files(get_cluster_pmachines([ip]), cluster_basedir, cluster_name)
        is_arakoon_dir_config_structure_present(ip, cluster_name, cluster_basedir)
        are_files_present_on(client, archived_files)
        are_files_missing_on(client, files_to_create)

    logger.info('===================================================')
    logger.info('remove cluster')
    ArakoonInstaller.delete_cluster(cluster_name, first_ip)

    for ip in node_ips:
        client = SSHClient(ip, username='ovs')
        are_files_present_on(client, archived_files)
        are_files_missing_on(client, files_to_create)
        is_arakoon_dir_config_structure_cleaned_up(ip, cluster_name, cluster_basedir)

