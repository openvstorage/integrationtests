# Copyright 2016 iNuron NV
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

"""
A general class dedicated to Physical Disk logic
"""

from ci.tests.general.connection import Connection
from ci.tests.general.general import General


class GeneralDisk(object):
    """
    A general class dedicated to Physical Disk logic
    """
    api = Connection()

    @staticmethod
    def get_unused_disks():
        """
        Retrieve all disks not in use
        :return: List of disks not being used
        """
        all_disks = General.execute_command("""fdisk -l 2>/dev/null| awk '/Disk \/.*:/ {gsub(":","",$s);print $2}'""")[0].splitlines()
        out = General.execute_command("df -h | awk '{print $1}'")[0]

        return [d for d in all_disks if d not in out and not General.execute_command("fuser {0}".format(d))[0]]

    @staticmethod
    def get_physical_disks(client):
        """
        Retrieve physical disk information
        :param client: SSHClient object
        :return: Physical disk information
        """
        disk_by_id = dict()
        result = client.run('ls -la /dev/disk/by-id/')
        for entry in result.splitlines():
            if 'ata-' in entry:
                device = entry.split()
                disk_by_id[device[10][-3:]] = device[8]

        result = client.run('lsblk -n -o name,type,size,rota')
        hdds = dict()
        ssds = dict()
        for entry in result.splitlines():
            disk = entry.split()
            disk_id = disk[0]
            if len(disk_id) > 2 and disk_id[0:2] in ['fd', 'sr', 'lo']:
                continue
            if disk[1] in 'disk':
                if disk[3] == '0':
                    ssds[disk[0]] = {'size': disk[2], 'is_ssd': True, 'name': disk_by_id[disk[0]]}
                else:
                    hdds[disk[0]] = {'size': disk[2], 'is_ssd': False, 'name': disk_by_id[disk[0]]}
        return hdds, ssds

    @staticmethod
    def configure_disk(storagerouter_guid, disk_guid, partition_guid, offset, size, roles):
        """
        Configure a disk
        :param storagerouter_guid: Guid of the Storage Router
        :param disk_guid: Guid of the disk to configure
        :param partition_guid: Guid of a partition in the disk
        :param offset: Offset of the partition
        :param size: Size of the partition
        :param roles: Roles to assign to the partition
        :return: None
        """
        GeneralDisk.api.execute_post_action(component='storagerouters',
                                            guid=storagerouter_guid,
                                            action='configure_disk',
                                            data={'disk_guid': disk_guid,
                                                  'offset': offset,
                                                  'size': size,
                                                  'roles': roles,
                                                  'partition_guid': partition_guid},
                                            wait=True,
                                            timeout=300)

    @staticmethod
    def append_disk_role(partition_guid, roles_to_add):
        """
        Configure a disk
        :param partition_guid: Guid of the disk partition
        :param roles_to_add: Roles to add to the disk
        :return: None
        """
        partition = GeneralDisk.api.fetch('diskpartitions', partition_guid)
        roles = list() if not partition['roles'] else partition['roles']
        for role in roles_to_add:
            if role not in roles:
                roles.append(role)
        disk = GeneralDisk.api.fetch('disks', partition['disk_guid'])
        GeneralDisk.configure_disk(storagerouter_guid=disk['storagerouter_guid'],
                                   disk_guid=partition['disk_guid'],
                                   partition_guid=partition['guid'],
                                   offset=partition['offset'],
                                   size=partition['size'],
                                   roles=roles)

    @staticmethod
    def add_db_role(storagerouter):
        """
        Add a DB role to a Storage Router
        :param storagerouter: Storage Router
        :return: None
        """
        for partition in GeneralDisk.api.get_components('diskpartitions'):
            if partition['mountpoint'] in ['/'] or partition['folder'] in ['/mnt/storage']:
                disk = GeneralDisk.api.fetch('disks', partition['disk_guid'])
                if disk['storagerouter_guid'] == storagerouter.guid:
                    GeneralDisk.append_disk_role(partition['guid'], ['DB'])
                    break

    @staticmethod
    def partition_disk(disk_guid):
        """
        Partition a disk
        :param disk_guid: Guid of the disk
        :return: None
        """
        disk = GeneralDisk.api.fetch('disks', disk_guid)
        if len(disk['partitions_guids']) != 0:
            return disk['partitions_guids'][0]

        GeneralDisk.configure_disk(storagerouter_guid=disk['storagerouter_guid'],
                                   disk_guid=disk['guid'],
                                   partition_guid=None,
                                   offset=0,
                                   size=disk['size'],
                                   roles=[])
        disk = GeneralDisk.api.fetch('disks', disk_guid)
        partition_guids = disk['partitions_guids']
        assert len(partition_guids) >= 1, "Partitioning failed for disk:\n {0} ".format(disk)
        return partition_guids[0]

    @staticmethod
    def add_read_write_scrub_roles(storagerouter):
        """
        Add READ, WRITE, SCRUB roles to a Storage Router
        :param storagerouter: Storage Router
        :return: None
        """
        disks = GeneralDisk.api.get_components('disks')

        partition_roles = dict()
        if len(disks) == 1:
            disk = disks[0]
            if not disk['partitions_guids']:
                partition_roles[GeneralDisk.partition_disk(disk['guid'])] = ['READ', 'WRITE', 'SCRUB']
        elif len(disks) > 1:
            disks_to_partition = [disk for disk in disks if disk['storagerouter_guid'] == storagerouter.guid and
                                  not disk['partitions_guids'] and disk['is_ssd']]
            for disk in disks_to_partition:
                GeneralDisk.partition_disk(disk['guid'])

            disks = GeneralDisk.api.get_components('disks')
            hdds = [disk for disk in disks if disk['storagerouter_guid'] == storagerouter.guid and not disk['is_ssd']]
            ssds = [disk for disk in disks if disk['storagerouter_guid'] == storagerouter.guid and disk['is_ssd']]

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
            GeneralDisk.append_disk_role(guid, roles)
