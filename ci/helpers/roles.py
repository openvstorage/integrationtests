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


class RoleHelper(object):

    CONFIGURE_DISK_TIMEOUT = 300
    LOGGER = LogHandler.get(source="setup", name="ci_role_helper")

    @staticmethod
    def _configure_disk(storagerouter_guid, disk_guid, offset, size, roles, api, partition_guid=None,
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
            RoleHelper.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
        else:
            RoleHelper.LOGGER.info("Adjusting disk `{0}` should have succeeded on storagerouter `{1}`"
                                  .format(disk_guid, storagerouter_guid))
            return disk_guid, storagerouter_guid