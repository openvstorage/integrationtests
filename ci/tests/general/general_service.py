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

from ovs.dal.lists.servicetypelist import ServiceTypeList


class GeneralService(object):
    """
    A general class dedicated to Service and ServiceType logic
    """
    @staticmethod
    def get_services_by_name(name):
        """
        Retrieve all services for a certain type
        :param name: Name of the service type
        :return: Data-object list of Services
        """
        service_type_names = [service_type.name for service_type in GeneralService.get_service_types()]
        if name not in service_type_names:
            raise ValueError('Invalid Service Type name specified. Please choose from: {0}'.format(', '.format(service_type_names)))
        return ServiceTypeList.get_by_name(name).services

    @staticmethod
    def get_service_types():
        """
        Retrieve all service types
        :return: Data-object list of ServiceTypes
        """
        return ServiceTypeList.get_servicetypes()
