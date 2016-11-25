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

from ci.helpers.vdisk import VDiskHelper
from ci.helpers.vpool import VPoolHelper
from ovs.log.log_handler import LogHandler
from ci.helpers.storagerouter import StoragerouterHelper


class VDiskSetup(object):

    LOGGER = LogHandler.get(source="setup", name="ci_vdisk_setup")
    CREATE_SNAPSHOT_TIMEOUT = 60
    CREATE_VDISK_TIMEOUT = 60

    def __init__(self):
        pass

    @staticmethod
    def create_snapshot(snapshot_name, vdisk_name, vpool_name, api, consistent=True, sticky=True,
                        timeout=CREATE_SNAPSHOT_TIMEOUT):
        """
        Create a new snapshot for a vdisk

        :param vdisk_name: location of a vdisk on a vpool
                           (e.g. /mnt/vpool/test.raw = test.raw, /mnt/vpool/volumes/test.raw = volumes/test.raw )
        :type vdisk_name: str
        :param snapshot_name: name of a new snapshot
        :type snapshot_name: str
        :param consistent: was everything properly flushed to the backend?
        :type consistent: bool
        :param sticky: let this snapshot stick forever?
        :type sticky: bool
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :param timeout: time to wait for the task to complete
        :type timeout: int
        :param vpool_name: name of a existing vpool
        :type vpool_name: str
        :return: if success
        :rtype: bool
        """
        vdisk_guid = VDiskHelper.get_vdisk_by_name(vdisk_name, vpool_name).guid

        data = {
            'name': snapshot_name,
            'consistent': consistent,
            'sticky': sticky
        }

        task_guid = api.post(
            api='/vdisks/{0}/create_snapshot/'.format(vdisk_guid),
            data=data
        )
        task_result = api.wait_for_task(task_id=task_guid, timeout=timeout)

        if not task_result[0]:
            error_msg = "Creating snapshot `{0}` for vdisk `{1}` on vPool `{2}` has failed"\
                .format(snapshot_name, vdisk_name, vpool_name)
            VDiskSetup.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
        else:
            VDiskSetup.LOGGER.info("Creating snapshot `{0}` for vdisk `{1}` on vPool `{2}` should have succeeded"
                                   .format(snapshot_name, vdisk_name, vpool_name))
            return task_result[1]

    @staticmethod
    def create_vdisk(vdisk_name, vpool_name, size, storagerouter_ip, api, timeout=CREATE_VDISK_TIMEOUT):
        """
        Create a new vDisk on a certain vPool/storagerouter

        :param vdisk_name: location of a vdisk on a vpool
                           (e.g. /mnt/vpool/test.raw = test.raw, /mnt/vpool/volumes/test.raw = volumes/test.raw )
        :type vdisk_name: str
        :param vpool_name: name of a existing vpool
        :type vpool_name: str
        :param size: size of the new vdisk in BYTES (e.g 10737418240 = 10G)
        :type size: int
        :param storagerouter_ip: ip address of a existing storagerouter
        :type storagerouter_ip: str
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :param timeout: time to wait for the task to complete
        :type timeout: int
        :param vpool_name: name of a existing vpool
        :type vpool_name: str
        :return: vdisk guid
        :rtype: str
        """
        vpool_guid = VPoolHelper.get_vpool_by_name(vpool_name).guid
        storagerouter_guid = StoragerouterHelper.get_storagerouter_by_ip(storagerouter_ip).guid

        # remove .raw or .vmdk if is present
        if '.raw' in vdisk_name or '.vmdk' in vdisk_name:
            official_vdisk_name = vdisk_name.split('.')[0]
        else:
            official_vdisk_name = vdisk_name

        data = {"name": official_vdisk_name,
                "size": int(size),
                "vpool_guid": vpool_guid,
                "storagerouter_guid": storagerouter_guid}

        task_guid = api.post(
            api='/vdisks/',
            data=data
        )
        task_result = api.wait_for_task(task_id=task_guid, timeout=timeout)

        if not task_result[0]:
            error_msg = "Creating vdisk `{0}` on vPool `{1}` on storagerouter `{2}` has failed with error {3}".format(vdisk_name, vpool_name, storagerouter_ip, task_result[1])
            VDiskSetup.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
        else:
            VDiskSetup.LOGGER.info("Creating vdisk `{0}` on vPool `{1}` on storagerouter `{2}` should have succeeded"
                                   .format(vdisk_name, vpool_name, storagerouter_ip))
            return task_result[1]
