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

from ovs.dal.hybrids.vdisk import VDisk
from ovs.dal.lists.vdisklist import VDiskList
from ovs.dal.lists.vpoollist import VPoolList
from ci.helpers.exceptions import VPoolNotFoundError, VDiskNotFoundError


class VDiskHelper(object):
    """
    vDiskHelper class
    """

    def __init__(self):
        pass

    @staticmethod
    def get_vdisk_by_name(vdisk_name, vpool_name):
        """
        Fetch disk partitions by disk guid

        :param vdisk_name: location of a vdisk on a vpool
                           (e.g. /mnt/vpool/test.raw = test.raw, /mnt/vpool/volumes/test.raw = volumes/test.raw )
        :type vdisk_name: str
        :param vpool_name: name of a existing vpool
        :type vpool_name: str
        :return: a vdisk object
        :rtype: ovs.dal.hybrids.vdisk
        """

        vpool = VPoolList.get_vpool_by_name(vpool_name)
        if vpool:
            if not vdisk_name.startswith("/"):
                vdisk_name = "/{0}".format(vdisk_name)
            vdisk = VDiskList.get_by_devicename_and_vpool(vdisk_name, vpool)
            if vdisk:
                return vdisk
            else:
                raise VDiskNotFoundError("VDisk with name `{0}` not found on vPool `{1}`!"
                                         .format(vdisk_name, vpool_name))
        else:
            raise VPoolNotFoundError("vPool with name `{0}` cannot be found!".format(vpool_name))

    @staticmethod
    def get_vdisk_by_guid(vdisk_guid):
        """
        Fetch vdisk object by vdisk guid

        :param vdisk_guid: guid of a existing vdisk
        :type vdisk_guid: str
        :return: a vdisk object
        :rtype: ovs.dal.hybrids.vdisk.VDISK
        """

        return VDisk(vdisk_guid)

    @staticmethod
    def get_snapshot_by_guid(snapshot_guid, vdisk_name, vpool_name):
        """
        Fetch vdisk object by vdisk guid

        :param snapshot_guid: guid of a existing snapshot
        :type snapshot_guid: str
        :param vdisk_name: name of a existing vdisk
        :type vdisk_name: str
        :param vpool_name: name of a existing vpool
        :type vpool_name: str
        :return: a vdisk object
        :rtype: ovs.dal.hybrids.vdisk
        """

        vdisk = VDiskHelper.get_vdisk_by_name(vdisk_name=vdisk_name, vpool_name=vpool_name)
        try:
            return next((snapshot for snapshot in vdisk.snapshots if snapshot['guid'] == snapshot_guid))
        except StopIteration:
            raise RuntimeError("Did not find snapshot with guid `{0}` on vdisk `{1}` on vpool `{2}`"
                               .format(snapshot_guid, vdisk_name, vpool_name))
