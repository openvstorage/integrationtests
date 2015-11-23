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
import os


def is_role_present(role):
    api = Connection.get_connection()
    result = api.get_components_with_attribute('diskpartitions', 'roles', role)
    if not result:
        return False
    else:
        return True


def append_disk_role(disk, roles, data):
    api = Connection.get_connection()
    my_sr = System.get_my_storagerouter()
    for role in roles:
        if is_role_present(role):
            data['roles'].remove(role)
    if data['roles']:
        api.execute_action('storagerouters', my_sr.guid, 'configure_disk', data)


def add_db_role():
    api = Connection.get_connection()
    roles = ["DB"]
    disks = api.get_components('disks')
    for partition in api.get_components('diskpartitions'):
        if partition['mountpoint'] in ['/'] or partition['folder'] in ['/mnt/storage']:
            for disk in disks:
                if partition['disk_guid'] == disk['guid']:
                    data = {'disk_guid': disk['guid'], 'offset': 0, 'size': disk['size'], 'roles': roles, 'partition_guid': partition['guid']}
                    append_disk_role(disk, roles, data)
                    break
            break


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
        roles = ["READ", "SCRUB"]
        data = {'disk_guid': ssds[0]['guid'], 'offset': 0, 'size': ssds[0]['size'], 'roles': roles,
                'partition_guid': ssds[0]['partitions_guids'][0] if len(ssds[0]['partitions_guids']) else None}
        append_disk_role(ssds[0], roles, data)
        roles = ["WRITE"]
        data = {'disk_guid': ssds[1]['guid'], 'offset': 0, 'size': ssds[1]['size'], 'roles': roles,
                'partition_guid': ssds[1]['partitions_guids'][0] if len(ssds[1]['partitions_guids']) else None}
        append_disk_role(ssds[1], roles, data)
    elif ssd_number == 1:
        roles = ["READ", "SCRUB", "WRITE"]
        data = {'disk_guid': ssds[0]['guid'], 'offset': 0, 'size': ssds[0]['size'], 'roles': roles,
                'partition_guid': ssds[0]['partitions_guids'][0] if len(ssds[0]['partitions_guids']) else None}
        append_disk_role(ssds[0], roles, data)
    elif ssd_number >= 3:
        roles = ["READ"]
        data = {'disk_guid': ssds[0]['guid'], 'offset': 0, 'size': ssds[0]['size'], 'roles': roles,
                'partition_guid': ssds[0]['partitions_guids'][0] if len(ssds[0]['partitions_guids']) else None}
        append_disk_role(ssds[0], roles, data)
        roles = ["SCRUB"]
        data = {'disk_guid': ssds[1]['guid'], 'offset': 0, 'size': ssds[1]['size'], 'roles': roles,
                'partition_guid': ssds[1]['partitions_guids'][0] if len(ssds[1]['partitions_guids']) else None}
        append_disk_role(ssds[1], roles, data)
        roles = ["WRITE"]
        data = {'disk_guid': ssds[2]['guid'], 'offset': 0, 'size': ssds[2]['size'], 'roles': roles,
                'partition_guid': ssds[2]['partitions_guids'][0] if len(ssds[2]['partitions_guids']) else None}
        append_disk_role(ssds[2], roles, data)
