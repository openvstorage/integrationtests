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

from ovs.log.log_handler import LogHandler
from ci.validate.decorators import check_role_on_disk
from ci.helpers.storagerouter import StoragerouterHelper


class RoleSetup(object):

    LOGGER = LogHandler.get(source="setup", name="ci_role_setup")
    CONFIGURE_DISK_TIMEOUT = 300

    MIN_PARTITION_SIZE = 5

    def __init__(self):
        pass

    @staticmethod
    @check_role_on_disk
    def add_disk_role(storagerouter_ip, diskname, roles, api, min_size=MIN_PARTITION_SIZE):
        """
        Partition and adds roles to a disk

        :param storagerouter_ip: ip address of a existing storagerouter
        :type storagerouter_ip: str
        :param diskname: shortname of a disk (e.g. sdb)
        :type diskname: str
        :param roles: list of roles you want to add to the disk
        :type roles: list
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :param min_size: minimum total_partition_size that is required to allocate the disk role
        :type min_size: int
        :return:
        """

        # Fetch information
        storagerouter_guid = StoragerouterHelper.get_storagerouter_guid_by_ip(storagerouter_ip)
        disk = StoragerouterHelper.get_disk_by_ip(storagerouter_ip, diskname)
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
                RoleSetup.configure_disk(storagerouter_guid=storagerouter_guid, disk_guid=disk.guid, offset=total_partition_size + 1,
                                          size=(disk.size-total_partition_size)-1, roles=roles, api=api)
            elif biggest_unused_partition is not None and (biggest_unused_partition.size/1024**3) > min_size:
                RoleSetup.configure_disk(storagerouter_guid=storagerouter_guid, disk_guid=disk.guid, offset=biggest_unused_partition.offset,
                                          size=biggest_unused_partition.size, roles=roles, api=api, partition_guid=biggest_unused_partition.guid)
            else:
                # disk is too small
                raise RuntimeError("Disk `{0}` on node `{1}` is too small for role(s) `{2}`, min. total_partition_size is `{3}`"
                                   .format(diskname, storagerouter_ip, roles, min_size))
        else:
            # there are no partitions on the disk, go nuke it!
            RoleSetup.configure_disk(storagerouter_guid, disk.guid, 0, disk.size, roles, api)

    @staticmethod
    def configure_disk(storagerouter_guid, disk_guid, offset, size, roles, api, partition_guid=None,
                       timeout=CONFIGURE_DISK_TIMEOUT):
        """
        Partition a disk and add roles to it

        :param storagerouter_guid: guid of a storagerouter
        :type storagerouter_guid: str
        :param disk_guid: guid of a disk
        :type disk_guid: str
        :param offset: start of the partition
        :type offset: int
        :param size: size of the partition
        :type size: int
        :param roles: roles to add to a partition (e.g. ['DB', 'WRITE'])
        :type roles: list
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :param timeout: time to wait for the task to complete
        :type timeout: int
        :param partition_guid: guid of the partition
        :type partition_guid: str
        :return: tuple that consists of disk_guid and storagerouter_guid
        :rtype: tuple
        """
        data = {
            'disk_guid': disk_guid,
            'offset': offset,
            'size': size,
            'roles': roles,
            'partition_guid': partition_guid
        }
        task_guid = api.post(
            api='/storagerouters/{0}/configure_disk/'.format(storagerouter_guid),
            data=data
        )
        task_result = api.wait_for_task(task_id=task_guid, timeout=timeout)

        if not task_result[0]:
            error_msg = "Adjusting disk `{0}` has failed on storagerouter `{1}` with error '{2}'" \
                .format(disk_guid, storagerouter_guid, task_result[1])
            RoleSetup.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
        else:
            RoleSetup.LOGGER.info("Adjusting disk `{0}` should have succeeded on storagerouter `{1}`"
                                  .format(disk_guid, storagerouter_guid))
            return disk_guid, storagerouter_guid
