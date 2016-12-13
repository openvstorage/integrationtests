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
Hypervisor/ManagementCenter factory module
Using the module requires libvirt api to be available on the MACHINE THAT EXECUTES THE CODE
"""

from ovs.extensions.generic.filemutex import file_mutex


class HypervisorFactory(object):
    """
    HypervisorFactory class provides functionality to get abstracted hypervisor
    """

    hypervisors = {}

    @staticmethod
    def get(ip, username, password, hvtype):
        """
        Returns the appropriate hypervisor client class for a given PMachine
        """
        key = '{0}_{1}'.format(ip, username)
        if key not in HypervisorFactory.hypervisors:
            mutex = file_mutex('hypervisor_{0}'.format(key))
            try:
                mutex.acquire(30)
                if key not in HypervisorFactory.hypervisors:
                    if hvtype == 'VMWARE':
                        # Not yet tested. Needs to be rewritten
                        raise NotImplementedError("{0} has not yet been implemented".format(hvtype))
                        from ci.helpers.hypervisor.hypervisors.vmware import VMware
                        hypervisor = VMware(ip, username, password)
                    elif hvtype == 'KVM':
                        from ci.helpers.hypervisor.hypervisors.kvm import KVM
                        hypervisor = KVM(ip, username, password)
                    else:
                        raise NotImplementedError('Hypervisor {0} is not yet supported'.format(hvtype))
                    HypervisorFactory.hypervisors[key] = hypervisor
            finally:
                mutex.release()
        return HypervisorFactory.hypervisors[key]
