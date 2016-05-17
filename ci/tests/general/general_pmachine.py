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
