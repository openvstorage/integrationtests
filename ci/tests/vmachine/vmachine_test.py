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
Virtual Machine testsuite
"""

import time
from ci.tests.general.general import General
from ci.tests.general.general_vmachine import GeneralVMachine
from ci.tests.general.general_vpool import GeneralVPool


class TestVMachine(object):
    """
    Virtual Machine testsuite
    """
    @staticmethod
    def vms_with_fio_test():
        """
        Test virtual machines with FIO
        """
        timeout = 30
        timer_step = 5
        nr_of_disks = 10
        vpool_name = General.get_config().get('vpool', 'name')
        vpool = GeneralVPool.get_vpool_by_name(vpool_name=vpool_name)
        assert vpool, "No vpool found where one was expected"
        for disk_number in range(nr_of_disks):
            disk_name = "disk-{0}".format(disk_number)
            GeneralVMachine.logger.info("Starting RAW disk creation")
            template_folder = GeneralVMachine.template_target_folder
            image_name = GeneralVMachine.template_image
            out, err, _ = General.execute_command('qemu-img convert -O raw {0}{1} /mnt/{2}/{3}.raw'.format(template_folder, image_name, vpool_name, disk_name))
            if err:
                GeneralVMachine.logger.error("Error while creating raw disk: {0}".format(err))

        vpool = GeneralVPool.get_vpool_by_name(vpool_name=vpool_name)
        assert len(vpool.vdisks) == nr_of_disks, "Only {0} out of {1} VDisks have been created".format(len(vpool.vdisks), nr_of_disks)

        for vm_number in range(nr_of_disks):
            machine_name = "machine-{0}".format(vm_number)
            disk_name = "disk-{0}".format(vm_number)
            GeneralVMachine.logger.info("Starting vmachine creation from RAW disk")
            out, err, _ = General.execute_command('virt-install --connect qemu:///system -n {0} -r 512 --disk /mnt/{1}/{2}.raw,'
                                                  'device=disk --noautoconsole --graphics vnc,listen=0.0.0.0 --vcpus=1 --network network=default,mac=RANDOM,'
                                                  'model=e1000 --import'.format(machine_name, vpool_name, disk_name))
            if err:
                GeneralVMachine.logger.error("Error while creating vmachine: {0}".format(err))

        counter = timeout / timer_step
        while counter > 0:
            vms = GeneralVMachine.get_vmachines()
            if len(vms) == nr_of_disks:
                counter = 0
            else:
                counter -= 1
                time.sleep(timer_step)
        vms = GeneralVMachine.get_vmachines()
        assert len(vms) == nr_of_disks, "Only {0} out of {1} VMachines have been created after {2} seconds".format(len(vms), nr_of_disks, timeout)

        # Waiting for 5 minutes of FIO activity on the vmachines
        time.sleep(300)
        vms = GeneralVMachine.get_vmachines()
        for vm in vms:
            assert vm.hypervisor_status == 'RUNNING', "Machine {0} has wrong status on the hypervisor: {1}".format(vm.name, vm.hypervisor_status)

        for vm_number in range(nr_of_disks):
            vmachine_name = "machine-{0}".format(vm_number)
            GeneralVMachine.logger.info("Removing {0} vmachine".format(vmachine_name))
            out, err, _ = General.execute_command('virsh destroy {0}'.format(vmachine_name))
            if err:
                GeneralVMachine.logger.error("Error while stopping vmachine: {0}".format(err))
            out, err, _ = General.execute_command('virsh undefine {0}'.format(vmachine_name))
            if err:
                GeneralVMachine.logger.error("Error while removing vmachine: {0}".format(err))

        counter = timeout / timer_step
        while counter > 0:
            vms = GeneralVMachine.get_vmachines()
            if len(vms):
                counter -= 1
                time.sleep(timer_step)
            else:
                counter = 0
        vms = GeneralVMachine.get_vmachines()
        assert len(vms) == 0, "Still some machines left on the vpool after waiting for {0} seconds: {1}".format(timeout, [vm.name for vm in vms])

        GeneralVMachine.logger.info("Removing vpool vdisks from {0} vpool".format(vpool_name))
        out, err, _ = General.execute_command("rm -rf /mnt/{0}/*.raw".format(vpool_name))
        if err:
            GeneralVMachine.logger.error("Error while removing vdisks: {0}".format(err))

        counter = timeout / timer_step
        while counter > 0:
            vpool = GeneralVPool.get_vpool_by_name(vpool_name=vpool_name)
            if len(vpool.vdisks):
                counter -= 1
                time.sleep(timer_step)
            else:
                counter = 0
        vpool = GeneralVPool.get_vpool_by_name(vpool_name=vpool_name)
        assert len(vpool.vdisks) == 0, "Still some disks left on the vpool after waiting {0} seconds: {1}".format(timeout, vpool.vdisks_guids)
