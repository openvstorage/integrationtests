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
