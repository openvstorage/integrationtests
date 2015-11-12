# Copyright 2014 iNuron NV
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

from ci.tests.general.connection import Connection
from ovs.extensions.generic.system import System
from ovs.lib.storagerouter import StorageRouterController


def is_db_role_present():
    api = Connection.get_connection()
    result = api.get_components_with_attribute('diskpartitions', 'roles', 'DB')
    if not result:
        return False
    else:
        return True


def add_db_role():
    api = Connection.get_connection()
    if not is_db_role_present():
        my_sr = System.get_my_storagerouter()
        for partition in api.get_components('diskpartitions'):
            if partition['mountpoint'] in ['/'] or partition['folder'] in ['/mnt/storage']:
                roles = list() if not partition['roles'] else partition['roles']
                roles.append('DB')
                # @todo: rework as api call
                StorageRouterController.configure_disk(my_sr.guid, partition['disk_guid'], partition['guid'],
                                                       partition['offset'], partition['size'], roles)
                break
