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

from ovs.dal.lists.storagerouterlist import StorageRouterList


class GeneralStorageRouter(object):
    """
    A general class dedicated to Storage Router logic
    """
    @staticmethod
    def get_storage_routers():
        """
        Retrieve all Storage Routers
        :return: Data-object list of Storage Routers
        """
        return StorageRouterList.get_storagerouters()
