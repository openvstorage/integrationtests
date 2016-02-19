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

"""
A general class dedicated to Storage Router logic
"""

from ci.tests.general.connection import Connection
from ovs.dal.lists.storagerouterlist import StorageRouterList
from ovs.extensions.generic.system import System


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

    @staticmethod
    def get_local_storagerouter():
        """
        Retrieve the local Storage Router
        :return: Storage Router DAL object
        """
        return System.get_my_storagerouter()

    @staticmethod
    def get_storage_router_by_ip(ip):
        """
        Retrieve Storage Router based on IP
        :param ip: IP of Storage Router
        :return: Storage Router DAL object
        """
        return StorageRouterList.get_by_ip(ip)

    @staticmethod
    def get_masters():
        """
        Retrieve all Storage Router masters
        :return: Data-object list with Storage Routers
        """
        return StorageRouterList.get_masters()

    @staticmethod
    def get_slaves():
        """
        Retrieve all Storage Router slaves
        :return: Data-object list with Storage Routers
        """
        return StorageRouterList.get_slaves()

    @staticmethod
    def sync_with_reality(storagerouter=None):
        """
        Synchronize the disks in the model with the reality on the storagerouter or all storagerouters
        :param storagerouter: Storage Router to synchronize
        :return: None
        """
        storagerouters = [storagerouter]
        if storagerouter is None:
            storagerouters = GeneralStorageRouter.get_storage_routers()
        api = Connection()
        for storagerouter in storagerouters:
            api.execute_post_action(component='storagerouters',
                                    guid=storagerouter.guid,
                                    action='rescan_disks',
                                    data={},
                                    wait=True,
                                    timeout=300)
