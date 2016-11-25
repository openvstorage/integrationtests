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
from ovs.lib.vdisk import VDiskController
from ovs.log.log_handler import LogHandler
from ovs.dal.exceptions import ObjectNotFoundException
from ci.validate.decorators import required_vtemplate


class VDiskRemover(object):

    LOGGER = LogHandler.get(source="remove", name="ci_vdisk_remover")
    REMOVE_SNAPSHOT_TIMEOUT = 60
    REMOVE_VTEMPLATE_TIMEOUT = 60

    def __init__(self):
        pass

    @staticmethod
    def remove_snapshot(snapshot_guid, vdisk_name, vpool_name, api, timeout=REMOVE_SNAPSHOT_TIMEOUT):
        """
        Remove a existing snapshot from a existing vdisk

        :param vdisk_name: location of a vdisk on a vpool
                           (e.g. /mnt/vpool/test.raw = test.raw, /mnt/vpool/volumes/test.raw = volumes/test.raw )
        :type vdisk_name: str
        :param snapshot_guid: unique guid of a snapshot
        :type snapshot_guid: str
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

        data = {"snapshot_id": snapshot_guid}
        task_guid = api.post(
            api='/vdisks/{0}/remove_snapshot/'.format(vdisk_guid),
            data=data
        )
        task_result = api.wait_for_task(task_id=task_guid, timeout=timeout)

        if not task_result[0]:
            error_msg = "Deleting snapshot `{0}` for vdisk `{1}` has failed".format(snapshot_guid, vdisk_name)
            VDiskRemover.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
        else:
            VDiskRemover.LOGGER.info("Deleting snapshot `{0}` for vdisk `{1}` should have succeeded"
                                     .format(snapshot_guid, vdisk_name))
            return True

    @staticmethod
    def remove_vdisk(vdisk_guid):
        """
        Remove a vdisk from a vPool

        :param vdisk_guid: guid of a existing vdisk
        :type vdisk_guid: str
        :return: if success
        :rtype: bool
        """

        VDiskController.delete(vdisk_guid)
        try:
            VDiskHelper.get_vdisk_by_guid(vdisk_guid)
            error_msg = "vDisk with guid `{0}` should be deleted but it isn't!".format(vdisk_guid)
            VDiskRemover.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
        except ObjectNotFoundException:
            VDiskRemover.LOGGER.info("Successfully deleted vDisk `{0}`".format(vdisk_guid))
            return True

    @staticmethod
    def remove_vdisk_by_name(vdisk_name, vpool_name):
        """
        Remove a vdisk from a vPool

        :param vdisk_name: name of a existing vdisk (e.g. test.raw)
        :type vdisk_name: str
        :param vpool_name: name of a existing vpool
        :type vpool_name: str
        :return: if success
        :rtype: bool
        """

        vdisk_guid = VDiskHelper.get_vdisk_by_name(vdisk_name, vpool_name).guid
        return VDiskRemover.remove_vdisk(vdisk_guid)

    @staticmethod
    @required_vtemplate
    def remove_vtemplate_by_name(vdisk_name, vpool_name, api, timeout=REMOVE_VTEMPLATE_TIMEOUT):
        """
        Remove a vTemplate from a cluster

        :param vdisk_name: name of a existing vdisk (e.g. test.raw)
        :type vdisk_name: str
        :param vpool_name: name of a existing vpool
        :type vpool_name: str
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :param timeout: time to wait for the task to complete
        :type timeout: int
        :return: if success
        :rtype: bool
        """

        vdisk_guid = VDiskHelper.get_vdisk_by_name(vdisk_name, vpool_name).guid

        task_guid = api.post(
            api='/vdisks/{0}/delete_vtemplate/'.format(vdisk_guid)
        )
        task_result = api.wait_for_task(task_id=task_guid, timeout=timeout)

        if not task_result[0]:
            error_msg = "Deleting vTemplate `{0}` has failed".format(vdisk_name)
            VDiskRemover.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
        else:
            VDiskRemover.LOGGER.info("Deleting vTemplate `{0}` should have succeeded".format(vdisk_name))
            return True
