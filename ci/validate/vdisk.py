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
from ci.validate.decorators import required_vdisk


class VDiskValidation(object):

    LOGGER = LogHandler.get(source="validate", name="ci_vdisk_validate")

    def __init__(self):
        pass

    @staticmethod
    @required_vdisk
    def check_required_vdisk(vdisk_name, vpool_name):
        """
        Checks if the given vdisk is present on the vpool

        :param vdisk_name: location of a vdisk on a vpool
                           (e.g. /mnt/vpool/test.raw = test.raw, /mnt/vpool/volumes/test.raw = volumes/test.raw )
        :type vdisk_name: str
        :param vpool_name: name of a existing vpool
        :type vpool_name: str
        :return:
        """

        return vdisk_name, vpool_name
