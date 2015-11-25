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

from ovs.lib.storagedriver import StorageDriverController

from ci.tests.backend import alba, generic
from ci.tests.disklayout import disklayout
from ci.tests.general import general_ovs
from ci.tests.general import general
from nose.plugins.skip import SkipTest


def setup():
    pass


def teardown():
    pass


def validate_arakoon_config_files(pmachines):
    def is_master_node(node_ip):
        return pmachines[node_ip]['node_type'] == 'MASTER'

    ips = pmachines.keys()
    ips.sort()
    if not ips:
        return False

    nr_of_configs_on_master = 0
    nr_of_configs_on_extra = 0

    matrix = dict()
    for ip in ips:
        matrix[ip] = dict()
        cmd = """/usr/bin/find /opt/OpenvStorage/config/arakoon -type f -name *.cfg -exec md5sum {} \;"""
        out = general.execute_command_on_node(ip, cmd)
        for entry in out.splitlines():
            md5_sum, filename = entry.split()
            matrix[ip][filename] = md5_sum
        if is_master_node(ip):
            nr_of_configs_on_master = len(matrix[ip])
        else:
            nr_of_configs_on_extra = len(matrix[ip])

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
            if cfg not in md5_matrix:
                md5_matrix[cfg] = matrix[ip][cfg]
            elif matrix[ip][cfg] != md5_matrix[cfg]:
                incorrect_configs.append("Incorrect contents {0} for {1} on {2}, expected {3}"
                                         .format(matrix[ip][cfg], ip, cfg, md5_matrix[cfg]))

    assert len(incorrect_configs) == 0, 'Incorrect arakoon config contents: \n{0}'.format('\n'.join(incorrect_configs))


def ovs_3554_4_node_cluster_config_validation_test():
    backend_name = 'OVS-3554'
    backend_type = 'alba'

    pmachines = general_ovs.get_pmachines_by_ip()
    if not len(pmachines) >= 4:
        raise SkipTest()

    master_ips = [ip for ip in pmachines.keys() if pmachines[ip]['node_type'] == 'MASTER']
    master_ips.sort()

    first_ip = master_ips[0]
    disklayout.add_db_role(general_ovs.get_storagerouter_by_ip(first_ip))
    StorageDriverController.manual_voldrv_arakoon_checkup()
    validate_arakoon_config_files(pmachines)

    for ip in pmachines.keys():
        if ip == first_ip:
            continue
        storagerouter = general_ovs.get_storagerouter_by_ip(ip)
        disklayout.add_db_role(storagerouter['guid'])
    StorageDriverController.manual_voldrv_arakoon_checkup()
    validate_arakoon_config_files(pmachines)

    backend = generic.get_backend_by_name_and_type(backend_name, backend_type)
    if not generic.is_backend_present(backend_name, backend_type):
        backend_guid = alba.add_alba_backend(backend_name)
        backend = generic.get_backend(backend_guid)
    validate_arakoon_config_files(pmachines)
    alba.remove_alba_backend(backend['alba_backend_guid'])
