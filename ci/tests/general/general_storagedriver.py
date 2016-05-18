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

"""
A general class dedicated to Storage Driver logic
"""

from ovs.dal.hybrids.diskpartition import DiskPartition
from ovs.dal.hybrids.j_storagedriverpartition import StorageDriverPartition


class GeneralStorageDriver(object):
    """
    A general class dedicated to Storage Driver logic
    """
    @staticmethod
    def has_role(storagedriver, role, sub_role=None):
        """
        Check if the Storage Driver has the requested role
        :param storagedriver: Storage Driver to check for role existence
        :param role: Role to check
        :param sub_role: Sub role to check
        :return: True or False
        """
        if role not in DiskPartition.ROLES:
            raise ValueError('Role should be 1 of the following:\n - {0}'.format('\n - '.join(DiskPartition.ROLES)))
        if sub_role is not None and sub_role not in StorageDriverPartition.SUBROLE:
            raise ValueError('Sub-role should be 1 of the following:\n - {0}'.format('\n - '.join(StorageDriverPartition.SUBROLE)))

        for partition in storagedriver.partitions:
            if partition.role == role:
                if sub_role is None:
                    return True
                else:
                    if partition.sub_role == sub_role:
                        return True
        return False
