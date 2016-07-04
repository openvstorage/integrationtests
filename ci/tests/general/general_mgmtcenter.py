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
A general class dedicated to Management Center logic
"""

from ci.tests.general.general import General
from ci.tests.general.connection import Connection
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.os.os import OSManager
from ovs.extensions.services.service import ServiceManager


class GeneralManagementCenter(object):
    """
    A general class dedicated to Management Center logic
    """
    api = Connection()

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
