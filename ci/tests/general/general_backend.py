# Copyright 2015 iNuron NV
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
A general class dedicated to Backend and BackendType logic
"""

from ci.tests.general.connection import Connection
from ovs.dal.lists.backendlist import BackendList
from ovs.dal.lists.backendtypelist import BackendTypeList


class GeneralBackend(object):
    """
    A general class dedicated to Backend and BackendType logic
    """
    api = Connection()

    @staticmethod
    def get_backendtype_by_name(name):
        """
        Retrieve backend type information
        :param name: Name of the backend type
        :return: Backend Type information
        """
        return GeneralBackend.api.get_component_by_name('backendtypes', name)

    @staticmethod
    def get_valid_backendtypes():
        """
        Retrieve a list of supported Backend Types
        :return: List of Backend Type Names
        """
        backendtypes = GeneralBackend.api.get_components('backendtypes')
        return [be['code'] for be in backendtypes]

    @staticmethod
    def get_backend(guid):
        """
        Retrieve Backend information
        :param guid: Guid of the Backend
        :return: Backend information
        """
        return GeneralBackend.api.fetch('backends', guid)

    @staticmethod
    def get_backends():
        """
        Retrieve a list of all backend
        :return: Data-object list of Backends
        """
        return BackendList.get_backends()

    @staticmethod
    def get_by_name(name):
        """
        Retrieve a backend based on name
        :param name: Name of the backend
        :return: Backend DAL object
        """
        return BackendList.get_by_name(name=name)

    @staticmethod
    def get_backendtype_by_code(code):
        """
        Retrieve the Backend Type based on its code
        :param code: Code of the Backend Type
        :return: Backend Type DAL object
        """
        if code not in GeneralBackend.get_valid_backendtypes():
            raise ValueError('Unsupported backend type {0} provided'.format(code))
        return BackendTypeList.get_backend_type_by_code(code=code)

    @staticmethod
    def get_backend_by_name_and_type(backend_name, backend_type_name):
        """
        Retrieve a Backend based on name and type
        :param backend_name: Name of the Backend
        :param backend_type_name: Name of the Backend Type
        :return:
        """
        backends = GeneralBackend.api.get_components_with_attribute('backends', 'name', backend_name)
        if backends:
            for backend in backends:
                backend_type = GeneralBackend.api.fetch('backendtypes', backend['backend_type_guid'])
                if backend['name'] == backend_name and backend_type['code'] == backend_type_name:
                    return backend

    @staticmethod
    def is_backend_present(backend_name, backend_type_name):
        """
        Verify if a backend with name and type is modelled
        :param backend_name: Name of the Backend
        :param backend_type_name: Name of the Backend Type
        :return: True if existent
        """
        return GeneralBackend.get_backend_by_name_and_type(backend_name, backend_type_name) is not None

    @staticmethod
    def add_backend(backend_name, backend_type_name):
        """
        Add a new backend
        :param backend_name: Name of the Backend to add
        :param backend_type_name: Name of the Backend Type to add
        :return: Guid of the new Backend
        """
        if not GeneralBackend.is_backend_present(backend_name, backend_type_name):
            backend_type = GeneralBackend.api.get_components_with_attribute('backendtypes', 'code', backend_type_name, True)
            new_backend = GeneralBackend.api.add('backends', {'name': backend_name,
                                                              'backend_type_guid': backend_type['guid']})
            return new_backend['guid']
