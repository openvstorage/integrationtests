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

from ci.tests.general import general
from ci.tests.general.general import test_config
from ci.tests.backend import alba, generic
from ovs.dal.lists.backendlist import BackendList
from ovs.dal.lists.albanodelist import AlbaNodeList
from ovs.lib.storagerouter import StorageRouterController
from ovs.dal.lists.vpoollist import VPoolList
from ci.tests.disklayout import disklayout

VPOOL_NAME = test_config.get('vpool', 'vpool_name')
VPOOL_NAME = 'vpool-' + VPOOL_NAME
BACKEND_NAME = test_config.get('backend', 'name')
BACKEND_TYPE = test_config.get('backend', 'type')
GRID_IP = test_config.get('main', 'grid_ip')


def setup():
    disklayout.add_db_role()
    disklayout.add_read_write_scrub_roles()
    if not generic.is_backend_present(BACKEND_NAME, BACKEND_TYPE):
        alba.add_alba_backend(BACKEND_NAME)
    backend = BackendList.get_by_name(BACKEND_NAME)
    alba_node = AlbaNodeList.get_albanode_by_ip(GRID_IP)
    alba.initialise_disks(alba_node)
    alba.claim_disks(backend, len(alba_node.all_disks), 'SATA')


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
    StorageRouterController.add_vpool.apply_async(kwargs={'parameters': add_vpool_params}).get(timeout=300)
    vpool = VPoolList.get_vpool_by_name(VPOOL_NAME)
    assert vpool, 'Vpool {0} was not created'.format(VPOOL_NAME)
    general.api_remove_vpool(VPOOL_NAME)
    vpool = VPoolList.get_vpool_by_name(VPOOL_NAME)
    assert not vpool, 'Vpool {0} was not deleted'.format(VPOOL_NAME)
