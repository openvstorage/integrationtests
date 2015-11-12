# Copyright 2014 iNuron NV
#
# Licensed under the Open vStorage Non-Commercial License, Version 1.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.openvstorage.org/OVS_NON_COMMERCIAL
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ci.tests.general.connection import Connection
api = Connection.get_connection()


def get_backendtype_by_name(name):

    return api.get_component_by_name('backendtypes', name)


def get_backend(guid):

    return api.fetch('backends', guid)


def get_backend_by_name_and_type(backend_name, backend_type_name):
    backends = api.get_components_with_attribute('backends', 'name', backend_name)
    if backends:
        for backend in backends:
            backend_type = api.fetch('backendtypes', backend['backend_type_guid'])
            if backend['name'] == backend_name and backend_type['code'] == backend_type_name:
                return backend
    return None


def is_backend_present(backend_name, backend_type_name):
    if get_backend_by_name_and_type(backend_name, backend_type_name):
        return True

    return False


def add_backend(backend_name, backend_type_name):
    if not is_backend_present(backend_name, backend_type_name):
        backend_type = api.get_component_with_attribute('backendtypes', 'code', backend_type_name)
        new_backend = api.add('backends', {'name': backend_name,
                                           'backend_type_guid': backend_type['guid']})
        return new_backend['guid']
