# Copyright 2016 iNuron NV
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
A general class dedicated to Storage Router logic
"""

from ci.tests.general.connection import Connection
from ovs.dal.hybrids.diskpartition import DiskPartition
from ovs.dal.lists.storagerouterlist import StorageRouterList
from ovs.extensions.generic.system import System
from ovs.lib.helpers.toolbox import Toolbox


class GeneralStorageRouter(object):
    """
    A general class dedicated to Storage Router logic
    """
    api = Connection()

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
        for storagerouter in storagerouters:
            GeneralStorageRouter.api.execute_post_action(component='storagerouters',
                                                         guid=storagerouter.guid,
                                                         action='rescan_disks',
                                                         data={},
                                                         wait=True,
                                                         timeout=300)

    @staticmethod
    def get_metadata(storagerouter):
        """
        Retrieve metadata for a Storage Router
        Example return value:
            {'ipaddresses': ['10.100.174.254', '172.22.1.100', '192.168.122.1'],
             'mountpoints': ['/mnt/ssd1', '/mnt/ssd2'],
             'partitions': {'BACKEND': [{'available': 1000202043392,
                                         'guid': '9ec473ad-5c3f-4fdb-a4ef-c99bb4449025',
                                         'in_use': False,
                                         'mountpoint': u'/mnt/alba-asd/hiu8WiD7sCfVF2IKRa5U1VZLOBS3H75W',
                                         'size': 1000202043392,
                                         'ssd': False,
                                         'storagerouter_guid': u'f5155bc2-b238-4a94-b6ce-b5600e65607a'}],
                            'DB': [{'available': 425200713728,
                                    'guid': 'c0064548-c0be-474d-a66b-da65639831f8',
                                    'in_use': False,
                                    'mountpoint': '/mnt/storage',
                                    'size': 425200713728,
                                    'ssd': False,
                                    'storagerouter_guid': u'f5155bc2-b238-4a94-b6ce-b5600e65607a'}],
                            'READ': [{'available': 60016295936,
                                      'guid': '56cab190-8a16-4c05-bf8c-13d2aae06371',
                                      'in_use': False,
                                      'mountpoint': u'/mnt/ssd1',
                                      'size': 60016295936,
                                      'ssd': True,
                                      'storagerouter_guid': u'f5155bc2-b238-4a94-b6ce-b5600e65607a'}],
                            'SCRUB': [{'available': 340160570983,
                                       'guid': 'c0064548-c0be-474d-a66b-da65639831f8',
                                       'in_use': False,
                                       'mountpoint': '/mnt/storage',
                                       'size': 425200713728,
                                       'ssd': False,
                                       'storagerouter_guid': u'f5155bc2-b238-4a94-b6ce-b5600e65607a'}],
                            'WRITE': [{'available': 60016295936,
                                       'guid': '0d167ced-5a5f-47aa-b890-45b923b686c4',
                                       'in_use': False,
                                       'mountpoint': u'/mnt/ssd2',
                                       'size': 60016295936,
                                       'ssd': True,
                                       'storagerouter_guid': u'f5155bc2-b238-4a94-b6ce-b5600e65607a'}]},
             'readcache_size': 60016295936,
             'scrub_available': True,
             'shared_size': 0,
             'writecache_size': 60016295936}

        :param storagerouter: Storage Router to retrieve metadata for
        :return: Metadata
        """
        result, metadata = GeneralStorageRouter.api.execute_post_action(component='storagerouters',
                                                                        guid=storagerouter.guid,
                                                                        action='get_metadata',
                                                                        data={},
                                                                        wait=True,
                                                                        timeout=300)
        assert result is True, 'Retrieving metadata failed for Storage Router {0}'.format(storagerouter.name)

        required_params = {'ipaddresses': (list, Toolbox.regex_ip),
                           'mountpoints': (list, str),
                           'partitions': (dict, None),
                           'readcache_size': (int, {'min': 0}),
                           'scrub_available': (bool, None),
                           'shared_size': (int, {'min': 0}),
                           'writecache_size': (int, {'min': 0})}
        Toolbox.verify_required_params(required_params = required_params,
                                       actual_params=metadata,
                                       exact_match=True)
        return metadata

    @staticmethod
    def has_roles(storagerouter, roles):
        """
        Check if the Storage Driver has the requested role
        :param storagerouter: Storage Router to check for role existence
        :param roles: Roles to check
        :return: True or False
        """
        if type(roles) in (str, basestring, unicode):
            roles = [roles]
        elif not isinstance(roles, list):
            raise ValueError('Roles should either be a string or a list of roles')

        for role in roles:
            if role not in DiskPartition.ROLES:
                raise ValueError('Role should be 1 of the following:\n - {0}'.format('\n - '.join(DiskPartition.ROLES)))

        storagerouter.invalidate_dynamics('partition_config')
        for known_role in DiskPartition.ROLES:
            assert known_role in storagerouter.partition_config, 'Role {0} is not defined in Storage Router {1} its partition config'.format(known_role, storagerouter.name)

        roles_found = True
        for role in roles:
            roles_found &= len(storagerouter.partition_config[role]) > 0
        return roles_found
