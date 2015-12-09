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

from ci.tests.backend import alba, generic
from ci.tests.general.general import test_config
from ovs.extensions.generic.system import System
from ci.tests.disklayout import disklayout
from ovs.dal.lists.backendlist import BackendList
from ovs.lib.storagerouter import StorageRouterController

VPOOL_NAME = test_config.get('vpool', 'vpool_name')
assert VPOOL_NAME, "Please fill out a valid vpool name in autotest.cfg file"

BACKEND_NAME = test_config.get('backend', 'name')
BACKEND_TYPE = test_config.get('backend', 'type')
assert BACKEND_NAME, "Please fill out a valid backend name in autotest.cfg file"
assert BACKEND_TYPE in generic.VALID_BACKEND_TYPES, "Please fill out a valid backend type in autotest.cfg file"

GRID_IP = test_config.get('main', 'grid_ip')
NR_OF_DISKS_TO_CLAIM = int(test_config.get('backend', 'nr_of_disks_to_claim'))
TYPE_OF_DISKS_TO_CLAIM = test_config.get('backend', 'type_of_disks_to_claim')


def remove_alba_backend():
    be = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    if be:
        alba_backend = alba.get_alba_backend(be['alba_backend_guid'])
        alba.unclaim_disks(alba_backend)
        alba.remove_alba_backend(be['alba_backend_guid'])


def add_alba_backend():
    my_sr = System.get_my_storagerouter()
    disklayout.add_db_role(my_sr.guid)
    disklayout.add_read_write_scrub_roles(my_sr.guid)
    backend = generic.get_backend_by_name_and_type(BACKEND_NAME, BACKEND_TYPE)
    if not backend:
        backend_guid = alba.add_alba_backend(BACKEND_NAME)
        backend = generic.get_backend(backend_guid)
    alba.claim_disks(backend['alba_backend_guid'], NR_OF_DISKS_TO_CLAIM, TYPE_OF_DISKS_TO_CLAIM)


def add_generic_vpool():
    backend = BackendList.get_by_name(BACKEND_NAME)
    add_vpool_params = {'storagerouter_ip': GRID_IP,
                        'vpool_name': VPOOL_NAME,
                        'type': 'alba',
                        'readcache_size': 10,
                        'writecache_size': 10,
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
    StorageRouterController.add_vpool.apply_async(kwargs={'parameters': add_vpool_params}).get(timeout=500)
