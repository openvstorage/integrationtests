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
from ovs.dal.hybrids.disk import Disk
from ovs.dal.hybrids.diskpartition import DiskPartition
from ovs.dal.lists.disklist import DiskList
from ovs.dal.lists.diskpartitionlist import DiskPartitionList


class GeneralDisk(object):
    """
    A general class dedicated to Physical Disk logic
    """
    api = Connection()

    @staticmethod
    def get_disk(guid):
        """
        Retrieve a Disk
        :param guid: Guid of the Disk
        :return: Disk DAL object
        """
        return Disk(guid)

    @staticmethod
    def get_disks():
        """
        Retrieve all physical disks
        :return: Data-object Disk list
        """
        return DiskList.get_disks()

    @staticmethod
    def get_disk_by_devicename(storagerouter, device_name):
        """
        Retrieve a disk based on its devicename
        :param storagerouter: Storage Router of the disk
        :param device_name: Device name of the disk
        :return: Disk DAL object
        """
        if device_name.startswith('/dev/'):
            device_name = device_name.replace('/dev/', '')

        for disk in GeneralDisk.get_disks():
            if disk.name == device_name and disk.storagerouter == storagerouter:
                return disk
        raise ValueError('No disk found with devicename {0}'.format(device_name))

    @staticmethod
    def get_disk_partition(guid):
        """
        Retrieve a Disk Partition
        :param guid: Guid of the Disk Partition
        :return: Disk Partition DAL object
        """
        return DiskPartition(guid)

    @staticmethod
    def get_disk_partitions():
        """
        Retrieve all physical disk partitions
        :return: Data-object DiskPartition list
        """
        return DiskPartitionList.get_partitions()

    @staticmethod
    def get_unused_disks():
        """
        Retrieve all disks not in use
        :return: List of disks not being used
        """
        # @TODO: Make this call possible on all nodes, not only on node executing the tests
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
    def configure_disk(storagerouter, disk, offset, size, roles, partition=None):
        """
        Configure a disk
        :param storagerouter: Storage Router
        :param disk: Disk to configure
        :param partition: Partition on the disk
        :param offset: Offset of the partition
        :param size: Size of the partition
        :param roles: Roles to assign to the partition
        :return: None
        """
        GeneralDisk.api.execute_post_action(component='storagerouters',
                                            guid=storagerouter.guid,
                                            action='configure_disk',
                                            data={'disk_guid': disk.guid,
                                                  'offset': offset,
                                                  'size': size,
                                                  'roles': roles,
                                                  'partition_guid': None if partition is None else partition.guid},
                                            wait=True,
                                            timeout=300)

    @staticmethod
    def append_disk_role(partition, roles_to_add):
        """
        Configure a disk
        :param partition: Disk partition
        :param roles_to_add: Roles to add to the disk
        :return: None
        """
        roles = partition.roles
        for role in roles_to_add:
            if role not in roles:
                roles.append(role)
        GeneralDisk.configure_disk(storagerouter=partition.disk.storagerouter,
                                   disk=partition.disk,
                                   partition=partition,
                                   offset=partition.offset,
                                   size=partition.size,
                                   roles=roles)

    @staticmethod
    def add_db_role(storagerouter):
        """
        Add a DB role to a Storage Router
        :param storagerouter: Storage Router
        :return: None
        """
        for partition in GeneralDisk.get_disk_partitions():
            if partition.mountpoint == '/' or partition.folder == '/mnt/storage':
                if partition.disk.storagerouter == storagerouter:
                    GeneralDisk.append_disk_role(partition, ['DB'])
                    break

    @staticmethod
    def partition_disk(disk):
        """
        Partition a disk
        :param disk: Disk DAL object
        :return: None
        """
        if len(disk.partitions) != 0:
            return disk.partitions[0]

        GeneralDisk.configure_disk(storagerouter=disk.storagerouter,
                                   disk=disk,
                                   offset=0,
                                   size=disk.size,
                                   roles=[])
        disk = GeneralDisk.get_disk(guid=disk.guid)
        assert len(disk.partitions) >= 1, "Partitioning failed for disk:\n {0} ".format(disk.name)
        return disk.partitions[0]

    @staticmethod
    def add_read_write_scrub_roles(storagerouter):
        """
        Add READ, WRITE, SCRUB roles to a Storage Router
        :param storagerouter: Storage Router
        :return: None
        """
        disks = GeneralDisk.get_disks()

        partition_roles = dict()
        if len(disks) == 1:
            disk = disks[0]
            if len(disk.partitions) == 0:
                partition_roles[GeneralDisk.partition_disk(disk)] = ['READ', 'WRITE', 'SCRUB']
        elif len(disks) > 1:
            disks_to_partition = [disk for disk in disks if disk.storagerouter == storagerouter and
                                  not disk.partitions_guids and disk.is_ssd]
            for disk in disks_to_partition:
                GeneralDisk.partition_disk(disk)

            disks = GeneralDisk.get_disks()
            hdds = [disk for disk in disks if disk.storagerouter == storagerouter and disk.is_ssd is False]
            ssds = [disk for disk in disks if disk.storagerouter == storagerouter and disk.is_ssd is True]

            if len(ssds) == 0:
                partition_roles[hdds[0].partitions[0]] = ['READ']
                partition_roles[hdds[1].partitions[0]] = ['WRITE', 'SCRUB']
            elif len(ssds) == 1:
                partition_roles[hdds[0].partitions[0]] = ['READ', 'SCRUB']
                partition_roles[ssds[0].partitions[0]] = ['WRITE']
            elif len(ssds) >= 2:
                partition_roles[ssds[0].partitions[0]] = ['READ', 'SCRUB']
                partition_roles[ssds[1].partitions[0]] = ['WRITE']

        for partition, roles in partition_roles.iteritems():
            GeneralDisk.append_disk_role(partition, roles)
