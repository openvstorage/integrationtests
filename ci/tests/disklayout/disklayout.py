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
from ovs.lib.storagerouter import StorageRouterController


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


def append_disk_role(partition_guid, role):
    api = Connection.get_connection()
    partition = api.fetch('diskpartitions', partition_guid)
    roles = list() if not partition['roles'] else partition['roles']
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
                append_disk_role(partition['guid'], 'DB')
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


def add_read_write_scrub_roles():
    api = Connection.get_connection()
    disks = api.get_components('disks')
    ssds = list()
    ssd_number = 0
    for disk in disks:
        if disk['is_ssd']:
            ssd_number += 1
            ssds.append(disk)

    if ssd_number == 2:
        for partition in api.get_components('diskpartitions'):
            if partition['disk_guid'] == ssds[0]['guid']:
                append_disk_role(partition['guid'], 'READ')
                append_disk_role(partition['guid'], 'SCRUB')
            elif partition['disk_guid'] == ssds[1]['guid']:
                append_disk_role(partition['guid'], 'WRITE')
    elif ssd_number == 1:
        for partition in api.get_components('diskpartitions'):
            if partition['disk_guid'] == ssds[0]['guid']:
                append_disk_role(partition['guid'], 'READ')
                append_disk_role(partition['guid'], 'SCRUB')
                append_disk_role(partition['guid'], 'WRITE')
                break
    elif ssd_number >= 3:
        for partition in api.get_components('diskpartitions'):
            if partition['disk_guid'] == ssds[0]['guid']:
                append_disk_role(partition['guid'], 'READ')
            elif partition['disk_guid'] == ssds[1]['guid']:
                append_disk_role(partition['guid'], 'WRITE')
            elif partition['disk_guid'] == ssds[2]['guid']:
                append_disk_role(partition['guid'], 'SCRUB')
