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

from ci.helpers.disk import DiskHelper
from ovs.log.log_handler import LogHandler
from ci.helpers.roles import RoleHelper
from ci.helpers.storagerouter import StoragerouterHelper


class RoleSetup(object):

    LOGGER = LogHandler.get(source="setup", name="ci_role_setup")
    CONFIGURE_DISK_TIMEOUT = 300

    MIN_PARTITION_SIZE = 5

    def __init__(self):
        pass

    @staticmethod
    def add_disk_role(ip, diskname, roles, api, min_size=MIN_PARTITION_SIZE):
        """
        Partition and adds roles to a disk

        :param ip: storagerouter ip where the disk is located
        :type ip: str
        :param diskname: shortname of a disk (e.g. sdb)
        :type diskname: str
        :param roles: list of roles you want to add to the disk
        :type roles: list
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :param min_size: minimum total_partition_size that is required to allocate the disk role
        :type min_size: int
        :param config: configuration file
        :type config: dict
        :return:
        """

        # Fetch information
        storagerouter_guid = StoragerouterHelper.get_storagerouter_guid_by_ip(ip)
        disk = StoragerouterHelper.get_disk_by_ip(ip, diskname)
        # Check if there are any partitions on the disk, if so check if there is enough space
        unused_partitions = []
        if len(disk.partitions) > 0:
            total_partition_size = 0
            for partition in disk.partitions:
                total_partition_size += partition.size
                # Check if the partition is in use - could possibly write role on unused partition
                if partition.mountpoint is None:
                    # Means no output -> partition not mounted
                    # @Todo support partitions that are not sequentional
                    unused_partitions.append(partition)

            # Elect biggest unused partition as potential candidate
            biggest_unused_partition = None
            if len(unused_partitions) > 0:
                # Sort the list based on size
                unused_partitions.sort(key=lambda x: x.size, reverse=True)
                biggest_unused_partition = unused_partitions[0]
            if ((disk.size-total_partition_size)/1024**3) > min_size:
                # disk is still large enough, let the partitioning begin and apply some roles!
                RoleHelper._configure_disk(storagerouter_guid=storagerouter_guid, disk_guid=disk.guid, offset=total_partition_size+1,
                                          size=(disk.size-total_partition_size)-1, roles=roles, api=api)
            elif biggest_unused_partition is not None and (biggest_unused_partition.size/1024**3) > min_size:
                RoleHelper._configure_disk(storagerouter_guid=storagerouter_guid, disk_guid=disk.guid, offset=biggest_unused_partition.offset,
                                          size=biggest_unused_partition.size, roles=roles, api=api, partition_guid=biggest_unused_partition.guid)
            else:
                # disk is too small
                raise RuntimeError("Disk `{0}` on node `{1}` is too small for role(s) `{2}`, min. total_partition_size is `{3}`"
                                   .format(diskname, ip, roles, min_size))
        else:
            # there are no partitions on the disk, go nuke it!
            RoleHelper._configure_disk(storagerouter_guid, disk.guid, 0, disk.size, roles, api)
