# Copyright 2016 iNuron NV
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
A general class dedicated to Management Center logic
"""

from ci.tests.general.general import General
from ci.tests.general.general_pmachine import GeneralPMachine
from ci.tests.general.connection import Connection
from ovs.dal.lists.mgmtcenterlist import MgmtCenterList
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.hypervisor.factory import Factory
from ovs.extensions.os.os import OSManager
from ovs.extensions.services.service import ServiceManager
from ovs.lib.mgmtcenter import MgmtCenterController


class GeneralManagementCenter(object):
    """
    A general class dedicated to Management Center logic
    """
    api = Connection()

    @staticmethod
    def get_mgmt_centers():
        """
        Retrieve all Management Center
        :return: Data-object Mgmt Center lists
        """
        return MgmtCenterList.get_mgmtcenters()

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
        autotest_config = General.get_config()
        management_centers = GeneralManagementCenter.get_mgmt_centers()
        if len(management_centers) == 0 and GeneralManagementCenter.is_devstack_installed():
            mgmtcenter = GeneralManagementCenter.create_mgmt_center(name=autotest_config.get("mgmtcenter", "name"),
                                                                    username=autotest_config.get("mgmtcenter", "username"),
                                                                    password=autotest_config.get("mgmtcenter", "password"),
                                                                    ip=autotest_config.get('mgmtcenter', 'ip'),
                                                                    center_type=autotest_config.get('mgmtcenter', 'type'),
                                                                    port=autotest_config.get('mgmtcenter', 'port'))
            for physical_machine in GeneralPMachine.get_pmachines():
                GeneralManagementCenter.configure_pmachine_with_mgmtcenter(pmachine=physical_machine,
                                                                           mgmtcenter=mgmtcenter)

    @staticmethod
    def remove_mgmt_center(mgmtcenter):
        """
        Remove a management center
        :param mgmtcenter: Management Center
        :return: None
        """
        for pmachine in mgmtcenter.pmachines:
            GeneralManagementCenter.unconfigure_pmachine_with_mgmtcenter(pmachine=pmachine,
                                                                         mgmtcenter=mgmtcenter)
        GeneralManagementCenter.api.remove('mgmtcenters', mgmtcenter.guid)

    @staticmethod
    def configure_pmachine_with_mgmtcenter(pmachine, mgmtcenter):
        """
        Configure the management center on the physical machine
        :param pmachine: Physical machine
        :param mgmtcenter: Management center
        :return: None
        """
        MgmtCenterController.configure_host(pmachine, mgmtcenter, True)

    @staticmethod
    def unconfigure_pmachine_with_mgmtcenter(pmachine, mgmtcenter):
        """
        Unconfigure the management center on the physical machine
        :param pmachine: Physical machine
        :param mgmtcenter: Management center
        :return: None
        """
        MgmtCenterController.unconfigure_host(pmachine, mgmtcenter, True)

    @staticmethod
    def is_host_configured(pmachine):
        """
        Verify if the pmachine has been configured
        :param pmachine: Physical machine
        :return: None
        """
        return MgmtCenterController.is_host_configured(pmachine.guid)

    @staticmethod
    def test_connection(mgmtcenter_guid):
        """
        Test the connectivity to the management center
        :param mgmtcenter_guid: Guid of the management center
        :return: True if connectivity is OK
        """
        return MgmtCenterController.test_connection(mgmtcenter_guid)
