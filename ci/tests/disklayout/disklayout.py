# Copyright 2014 iNuron NV
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

from ci.tests.general.connection import Connection
from ovs.lib.storagerouter import StorageRouterController
import os


def is_role_present(role, storagerouter_guid=None):
    api = Connection.get_connection()
    result = api.get_components_with_attribute('diskpartitions', 'roles', role)
    filtered_result = list()
    if storagerouter_guid:
        for partition in result:
            disk = api.fetch('disks', partition['disk_guid'])
            storagerouter = api.fetch('storagerouters', disk['storagerouter_guid'])
            if storagerouter['guid'] == storagerouter_guid:
                filtered_result.append(partition)
        result = filtered_result

    if not result:
        return False
    else:
        return True


def append_disk_role(partition_guid, roles_to_add):
    api = Connection.get_connection()
    partition = api.fetch('diskpartitions', partition_guid)
    roles = list() if not partition['roles'] else partition['roles']
    for role in roles_to_add:
        if role not in roles:
            roles.append(role)
    disk = api.fetch('disks', partition['disk_guid'])
    storagerouter = api.fetch('storagerouters', disk['storagerouter_guid'])
    StorageRouterController.configure_disk(storagerouter['guid'], partition['disk_guid'], partition['guid'],
                                           partition['offset'], partition['size'], roles)


def add_db_role(storagerouter_guid):
    api = Connection.get_connection()
    for partition in api.get_components('diskpartitions'):
        if partition['mountpoint'] in ['/'] or partition['folder'] in ['/mnt/storage']:
            disk = api.fetch('disks', partition['disk_guid'])
            if disk['storagerouter_guid'] == storagerouter_guid:
                append_disk_role(partition['guid'], ['DB'])
                break


def remove_role(storagerouter_guid, role, partition_guid=None):
    api = Connection.get_connection()
    for partition in api.get_components('diskpartitions'):
        disk = api.fetch('disks', partition['disk_guid'])
        if disk['storagerouter_guid'] == storagerouter_guid and role in partition['roles']:
            if not partition_guid or partition['guid'] == partition_guid:
                roles = partition['roles']
                roles.pop(partition['roles'].index(role))
                StorageRouterController.configure_disk(storagerouter_guid, disk['guid'], partition['guid'],
                                                       partition['offset'], partition['size'], roles)


def partition_disk(disk_guid):
    api = Connection.get_connection()
    disk = api.fetch('disks', disk_guid)
    if len(disk['partitions_guids']) == 0:
        StorageRouterController.configure_disk(disk['storagerouter_guid'], disk['guid'], None, 0, disk['size'], [])
    else:
        return disk['partitions_guids'][0]

    disk = api.fetch('disks', disk_guid)
    partition_guids = disk['partitions_guids']
    assert len(partition_guids) >= 1, "Partitioning failed for disk:\n {0} ".format(disk)
    return partition_guids[0]
