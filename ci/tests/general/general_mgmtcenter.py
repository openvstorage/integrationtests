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
        is_devstack = 'stack' in str(client.run(['ps aux | grep SCREEN | grep stack | grep -v grep || true']))
        return is_openstack or is_devstack
