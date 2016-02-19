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

"""
A general class dedicated to vMachine logic
"""

from ovs.dal.lists.vmachinelist import VMachineList


class GeneralVMachine(object):
    """
    A general class dedicated to vMachine logic
    """
    @staticmethod
    def get_vmachine_by_name(name):
        """
        Retrieve the DAL vMachine object based on its name
        :param name: Name of the virtual machine
        :return: vMachine DAL object
        """
        return VMachineList.get_vmachine_by_name(vmname=name)

    @staticmethod
    def get_vmachines():
        """
        Retrieve all Virtual Machines
        :return: Virtual Machine data-object list
        """
        return VMachineList.get_vmachines()
