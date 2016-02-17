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

from ci.tests.general import general
from ci.tests.general.connection import Connection
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.hypervisor.factory import Factory
from ovs.extensions.os.os import OSManager
from ovs.extensions.services.service import ServiceManager
from ovs.lib.mgmtcenter import MgmtCenterController


class GeneralManagementCenter(object):
    """
    A general class dedicated to Management Center logic
    """
    api = Connection.get_connection()

    @staticmethod
    def is_devstack_installed():
        """
        Check if OpenStack or DevStack is installed
        :return: True if installed
        """
        client = SSHClient('127.0.0.1', username='root')
        is_openstack = ServiceManager.has_service(OSManager.get_openstack_cinder_service_name(), client)
        is_devstack = 'stack' in str(client.run('ps aux | grep SCREEN | grep stack | grep -v grep || true'))
        return is_openstack or is_devstack

    @staticmethod
    def get_mgmt_center(pmachine=None, mgmt_center=None):
        """
        Retrieve the management center
        :param pmachine: DAL Physical machine to retrieve management center for
        :param mgmt_center: DAL Management center to retrieve the actual management center for
        :return: Management Center
        """
        return Factory.get_mgmtcenter(pmachine=pmachine,
                                      mgmt_center=mgmt_center)

    @staticmethod
    def create_mgmt_center(name, username, password, ip, center_type, port):
        """
        Create a management center
        :param name: Name of the management center
        :param username: Username to connect to the management center
        :param password: Password to connect to the management center
        :param ip: Public IP for the management center
        :param center_type: Type of the management center
        :param port: Port to connect on
        :return: Management Center information
        """
        return GeneralManagementCenter.api.add('mgmtcenters', {'name': name,
                                                               'username': username,
                                                               'password': password,
                                                               'ip': ip,
                                                               'type': center_type,
                                                               'port': port})

    @staticmethod
    def create_generic_mgmt_center():
        """
        Create and configure a management center
        :return: None
        """
        autotest_config = general.get_config()
        management_centers = GeneralManagementCenter.api.get_components('mgmtcenters')
        if len(management_centers) == 0 and GeneralManagementCenter.is_devstack_installed():
            mgmtcenter = GeneralManagementCenter.create_mgmt_center(name=autotest_config.get("mgmtcenter", "name"),
                                                                    username=autotest_config.get("mgmtcenter", "username"),
                                                                    password=autotest_config.get("mgmtcenter", "password"),
                                                                    ip=autotest_config.get('mgmtcenter', 'ip'),
                                                                    center_type=autotest_config.get('mgmtcenter', 'type'),
                                                                    port=autotest_config.get('mgmtcenter', 'port'))
            for physical_machine in GeneralManagementCenter.api.get_components('pmachines'):
                GeneralManagementCenter.configure_pmachine_with_mgmtcenter(pmachine_guid=physical_machine['guid'],
                                                                           mgmtcenter_guid=mgmtcenter['guid'])

    @staticmethod
    def remove_mgmt_center(mgmtcenter_guid):
        """
        Remove a management center
        :param mgmtcenter_guid: Guid of the management center
        :return: None
        """
        management_center = GeneralManagementCenter.api.fetch('mgmtcenters', mgmtcenter_guid)
        for pmachine_guid in management_center['pmachines_guids']:
            GeneralManagementCenter.unconfigure_pmachine_with_mgmtcenter(pmachine_guid=pmachine_guid,
                                                                         mgmtcenter_guid=mgmtcenter_guid)
        GeneralManagementCenter.api.remove('mgmtcenters', mgmtcenter_guid)

    @staticmethod
    def configure_pmachine_with_mgmtcenter(pmachine_guid, mgmtcenter_guid):
        """
        Configure the management center on the physical machine
        :param pmachine_guid: Guid of the physical machine
        :param mgmtcenter_guid: Guid of the management center
        :return: None
        """
        MgmtCenterController.configure_host(pmachine_guid, mgmtcenter_guid, True)

    @staticmethod
    def unconfigure_pmachine_with_mgmtcenter(pmachine_guid, mgmtcenter_guid):
        """
        Unconfigure the management center on the physical machine
        :param pmachine_guid: Guid of the physical machine
        :param mgmtcenter_guid: Guid of the management center
        :return: None
        """
        MgmtCenterController.unconfigure_host(pmachine_guid, mgmtcenter_guid, True)

    @staticmethod
    def is_host_configured(pmachine_guid):
        """
        Verify if the pmachine has been configured
        :param pmachine_guid: Guid of the physical machine
        :return: None
        """
        return MgmtCenterController.is_host_configured(pmachine_guid)

    @staticmethod
    def test_connection(mgmtcenter_guid):
        """
        Test the connectivity to the management center
        :param mgmtcenter_guid: Guid of the management center
        :return: True if connectivity is OK
        """
        return MgmtCenterController.test_connection(mgmtcenter_guid)
