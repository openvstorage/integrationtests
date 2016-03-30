# Copyright 2014 iNuron NV
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
