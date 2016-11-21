# Copyright (C) 2016 iNuron NV
#
# This file is part of Open vStorage Open Source Edition (OSE),
# as available from
#
#      http://www.openvstorage.org and
#      http://www.openvstorage.com.
#
# This file is free software; you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License v3 (GNU AGPLv3)
# as published by the Free Software Foundation, in version 3 as it comes
# in the LICENSE.txt file of the Open vStorage OSE distribution.
#
# Open vStorage is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY of any kind.

from ovs.dal.lists.disklist import DiskList
from ci.helpers.storagerouter import StoragerouterHelper
from ovs.dal.lists.diskpartitionlist import DiskPartitionList


class DiskHelper(object):
    """
    DiskHelper class
    """

    def __init__(self):
        pass

    @staticmethod
    def get_diskpartitions_by_guid(diskguid):
        """
        Fetch disk partitions by disk guid

        :param diskguid: ip address of a storagerouter
        :type diskguid: str
        :return: list of DiskPartition Objects
        :rtype: list (ovs.dal.hybrids.diskpartition.diskpartition)
        """

        return [dp for dp in DiskPartitionList.get_partitions() if dp.disk_guid == diskguid]

    @staticmethod
    def get_roles_from_disks(storagerouter_ip=None):
        """
        Fetch disk roles from all disks with optional storagerouter_ip

        :param storagerouter_ip: ip address of a storage router
        :type storagerouter_ip: str
        :return: list of lists with roles
        :rtype: list > list
        """
        if not storagerouter_ip:
            return [partition.roles for disk in DiskList.get_disks() for partition in disk.partitions]
        else:
            storagerouter_guid = StoragerouterHelper.get_storagerouter_guid_by_ip(storagerouter_ip)
            return [partition.roles for disk in DiskList.get_disks()
                    if disk.storagerouter_guid == storagerouter_guid for partition in disk.partitions]

    @staticmethod
    def get_disk_by_diskname(storagerouter_ip, disk_name):
        """
        Get a disk object by storagerouter ip and disk name

        :param storagerouter_ip: ip address of a storage router
        :type storagerouter_ip: str
        :param disk_name: name of a disk (e.g. sda)
        :type disk_name: str
        :return: disk object
        :rtype: ovs.dal.hybrids.Disk
        """

        storagerouter = StoragerouterHelper.get_storagerouter_by_ip(storagerouter_ip=storagerouter_ip)
        for disk in storagerouter.disks:
            if disk.name == disk_name:
                return disk

    @staticmethod
    def get_roles_from_disk(storagerouter_ip, disk_name):
        """
        Get the roles from a certain disk

        :param storagerouter_ip: ip address of a storage router
        :type storagerouter_ip: str
        :param disk_name: name of a disk (e.g. sda)
        :type disk_name: str
        :return: list of roles of all partitions on a certain disk
        :rtype: list
        """

        disk = DiskHelper.get_disk_by_diskname(storagerouter_ip, disk_name)
        roles_on_disk = []
        if disk:
            for diskpartition in disk.partitions:
                for role in diskpartition.roles:
                    roles_on_disk.append(role)
            return roles_on_disk
        else:
            raise RuntimeError("Disk with name `{0}` not found on storagerouter `{1}`".format(disk_name,
                                                                                              storagerouter_ip))
