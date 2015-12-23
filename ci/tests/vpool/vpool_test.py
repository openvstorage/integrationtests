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

from ci.tests.general import general
from ci.tests.general.connection import Connection
from ci.tests.general.general import test_config
from ci.tests.backend import alba, generic
from ovs.dal.lists.backendlist import BackendList
from ovs.extensions.generic.system import System
from ovs.lib.storagerouter import StorageRouterController
from ovs.dal.lists.vpoollist import VPoolList
from ci.tests.disklayout import disklayout


VPOOL_NAME = test_config.get('vpool', 'vpool_name')
assert VPOOL_NAME, "Please fill out a valid vpool name in autotest.cfg file"

BACKEND_NAME = test_config.get('backend', 'name')
BACKEND_TYPE = test_config.get('backend', 'type')
assert BACKEND_NAME, "Please fill out a valid backend name in autotest.cfg file"
assert BACKEND_TYPE in generic.VALID_BACKEND_TYPES, "Please fill out a valid backend type in autotest.cfg file"

GRID_IP = test_config.get('main', 'grid_ip')
NR_OF_DISKS_TO_CLAIM = int(test_config.get('backend', 'nr_of_disks_to_claim'))
TYPE_OF_DISKS_TO_CLAIM = test_config.get('backend', 'type_of_disks_to_claim')


def add_read_write_scrub_roles(storagerouter_guid):
    api = Connection.get_connection()
    disks = api.get_components('disks')

    partition_roles = dict()
    if len(disks) == 1:
        disk = disks[0]
        if not disk['partitions_guids']:
            partition_roles[disklayout.partition_disk(disk['guid'])] = ['READ', 'WRITE', 'SCRUB']
    elif len(disks) > 1:
        disks_to_partition = [disk for disk in disks if disk['storagerouter_guid'] == storagerouter_guid and
                              not disk['partitions_guids'] and disk['is_ssd']]
        for disk in disks_to_partition:
            disklayout.partition_disk(disk['guid'])

        disks = api.get_components('disks')
        hdds = [disk for disk in disks if disk['storagerouter_guid'] == storagerouter_guid and not disk['is_ssd']]
        ssds = [disk for disk in disks if disk['storagerouter_guid'] == storagerouter_guid and disk['is_ssd']]

        if len(ssds) == 0:
            partition_roles[hdds[0]['partitions_guids'][0]] = ['READ']
            partition_roles[hdds[1]['partitions_guids'][0]] = ['WRITE', 'SCRUB']
        elif len(ssds) == 1:
            partition_roles[hdds[0]['partitions_guids'][0]] = ['READ', 'SCRUB']
            partition_roles[ssds[0]['partitions_guids'][0]] = ['WRITE']
        elif len(ssds) >= 2:
            partition_roles[ssds[0]['partitions_guids'][0]] = ['READ', 'SCRUB']
            partition_roles[ssds[1]['partitions_guids'][0]] = ['WRITE']

    for guid, roles in partition_roles.iteritems():
        disklayout.append_disk_role(guid, roles)


def setup():
    my_sr = System.get_my_storagerouter()
    disklayout.add_db_role(my_sr.guid)
    add_read_write_scrub_roles(my_sr.guid)
    backend = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    if not backend:
        backend_guid = alba.add_alba_backend(BACKEND_NAME)
        backend = generic.get_backend(backend_guid)
    alba.claim_disks(backend['alba_backend_guid'], NR_OF_DISKS_TO_CLAIM, TYPE_OF_DISKS_TO_CLAIM)


def teardown():
    be = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    if be:
        alba_backend = alba.get_alba_backend(be['alba_backend_guid'])
        alba.unclaim_disks(alba_backend)
        alba.remove_alba_backend(be['alba_backend_guid'])


def add_vpool_test():
    backend = BackendList.get_by_name(BACKEND_NAME)
    add_vpool_params = {'storagerouter_ip': GRID_IP,
                        'vpool_name': VPOOL_NAME,
                        'type': 'alba',
                        'readcache_size': 10,
                        'writecache_size': 10,
                        'mountpoint_bfs': '/mnt/bfs',
                        'mountpoint_temp': '/mnt/tmp',
                        'mountpoint_md': '/mnt/md',
                        'mountpoint_readcaches': ['/mnt/cache1'],
                        'mountpoint_writecaches': ['/mnt/cache2'],
                        'mountpoint_foc': '/mnt/cache1',
                        'storage_ip': '127.0.0.1',
                        'vrouter_port': 12326,
                        'integratemgmt': True,
                        'connection_backend': {'backend': backend.alba_backend_guid,
                                               'metadata': 'default'},
                        'connection_password': '',
                        'connection_username': '',
                        'connection_host': '',
                        'connection_port': 12326,
                        'config_params': {'dtl_mode': 'sync',
                                          'sco_size': 4,
                                          'dedupe_mode': 'dedupe',
                                          'dtl_enabled': False,
                                          'dtl_location': '/mnt/cache1',
                                          'write_buffer': 128,
                                          'cache_strategy': 'on_read',
                                          'dtl_transport': 'tcp',
                                          }
                        }
    my_sr = System.get_my_storagerouter()
    StorageRouterController.add_vpool.s(add_vpool_params).apply_async(routing_key='sr.{0}'.format(my_sr.machine_id)).get(timeout=500)
    vpool = VPoolList.get_vpool_by_name(VPOOL_NAME)
    assert vpool, 'Vpool {0} was not created'.format(VPOOL_NAME)
    general.api_remove_vpool(VPOOL_NAME)
    vpool = VPoolList.get_vpool_by_name(VPOOL_NAME)
    assert not vpool, 'Vpool {0} was not deleted'.format(VPOOL_NAME)
