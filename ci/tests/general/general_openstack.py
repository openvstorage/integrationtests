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
A general class dedicated to OpenStack and DevStack logic
"""

import os
from ci.tests.general.general import General
from ci.tests.general.general_storagerouter import GeneralStorageRouter


# Setup environment
os.environ["OS_USERNAME"] = "admin"
os.environ["OS_PASSWORD"] = "rooter"
os.environ["OS_TENANT_NAME"] = "admin"
os.environ["OS_AUTH_URL"] = "http://{0}:35357/v2.0".format(GeneralStorageRouter.get_local_storagerouter().ip)


class GeneralOpenStack(object):
    """
    A general class dedicated to OpenStack and DevStack logic
    """
    @staticmethod
    def is_openstack_present():
        """
        Check if OpenStack is installed
        :return: Return True if OpenStack is installed
        """
        return bool(General.execute_command("ps aux | awk '/keystone/ && !/awk/'")[0])
