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
A general class dedicated to Physical Machine logic
"""

from ovs.dal.lists.pmachinelist import PMachineList


class GeneralPMachine(object):
    """
    A general class dedicated to Physical Machine logic
    """
    @staticmethod
    def get_all_ips():
        """
        Retrieve all IPs for all Physical Machines
        :return: List of IPs
        """
        return [str(pmachine.ip) for pmachine in PMachineList.get_pmachines()]

    @staticmethod
    def get_hypervisor_type():
        """
        Retrieve the hypervisor for any Physical Machine
        :return: Hypervisor type (VMWARE, KVM)
        """
        pmachines = GeneralPMachine.get_pmachines()
        if len(pmachines) == 0:
            raise RuntimeError('No Physical Machines found in model')
        hv_type = pmachines[0].hvtype
        if hv_type not in ['VMWARE', 'KVM']:
            raise ValueError('Currently only VMWARE and KVM are supported hypervisor types')
        return hv_type

    @staticmethod
    def get_pmachines():
        """
        Retrieve all Physical Machines
        :return: Data-object list of Physical Machines
        """
        return PMachineList.get_pmachines()

    @staticmethod
    def get_pmachine_by_ip(ip):
        """
        Retrieve Physical Machine object based on its IP
        :param ip: IP of the Physical Machine
        :return: Physical Machine DAL object
        """
        return PMachineList.get_by_ip(ip=ip)
