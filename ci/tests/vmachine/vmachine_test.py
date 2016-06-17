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
Virtual Machine testsuite
"""

import time
from ci.tests.general.general import General
from ci.tests.general.general_vdisk import GeneralVDisk
from ci.tests.general.general_vmachine import GeneralVMachine
from ci.tests.general.general_vpool import GeneralVPool
from ovs.lib.scheduledtask import ScheduledTaskController
from ovs.lib.vdisk import VDiskController


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
        nr_of_disks = 1
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

        # Waiting for 1 minute of FIO activity on vmachine
        time.sleep(60)
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

    @staticmethod
    def check_scrubbing_test():
        """
        Check scrubbing of vdisks test
        """
        issues_found = ""
        timeout = 360
        timer_step = 60
        nr_of_disks = 1
        vpool_name = General.get_config().get('vpool', 'name')
        vpool = GeneralVPool.get_vpool_by_name(vpool_name=vpool_name)
        assert vpool, "No vpool found where one was expected"

        template_folder = GeneralVMachine.template_target_folder
        image_name = GeneralVMachine.template_image

        for disk_number in range(nr_of_disks):
            disk_name = "scrubdisk-{0}".format(disk_number)
            GeneralVMachine.logger.info("Starting RAW disk creation")
            out, err, _ = General.execute_command('qemu-img convert -O raw {0}{1} /mnt/{2}/{3}.raw'.format(template_folder, image_name, vpool_name, disk_name))
            if err:
                GeneralVMachine.logger.error("Error while creating raw disk: {0}".format(err))

        for vm_number in range(nr_of_disks):
            machine_name = "machine-{0}".format(vm_number)
            disk_name = "scrubdisk-{0}".format(vm_number)
            GeneralVMachine.logger.info("Starting vmachine creation from RAW disk")
            out, err, _ = General.execute_command('virt-install --connect qemu:///system -n {0} -r 512 --disk /mnt/{1}/{2}.raw,'
                                                  'device=disk --noautoconsole --graphics vnc,listen=0.0.0.0 --vcpus=1 --network network=default,mac=RANDOM,'
                                                  'model=e1000 --import'.format(machine_name, vpool_name, disk_name))
            if err:
                GeneralVMachine.logger.error("Error while creating vmachine: {0}".format(err))

        def snapshot_vdisks():
            vds = GeneralVDisk.get_vdisks()
            for disk in vds:
                metadata = {'label': 'snap-' + disk.name,
                            'is_consistent': True,
                            'timestamp': time.time(),
                            'machineguid': disk.vmachine_guid,
                            'is_automatic': False,
                            'is_sticky': False}
                VDiskController.create_snapshot(disk.guid, metadata)

        # snapshoting disks for the first time
        snapshot_vdisks()
        counter = timeout / timer_step
        while counter > 0:
            time.sleep(timer_step)
            counter -= 1
            snapshot_vdisks()

        # stopping machines
        vms = GeneralVMachine.get_vmachines()
        for vm in vms:
            GeneralVMachine.logger.info("Stopping {0} vmachine".format(vm.name))
            out, err, _ = General.execute_command('virsh destroy {0}'.format(vm.name))
            if err:
                GeneralVMachine.logger.error("Error while stopping vmachine: {0}".format(err))

        vds = GeneralVDisk.get_vdisks()
        disk_backend_data = {}
        for disk in vds:
            # saving disk 'stored' info / the only attribute that is lowered after scrubbing
            disk_backend_data[disk.guid] = disk.statistics['stored']

        # deleting middle snapshots
        for disk in vds:
            for snapshot in disk.snapshots[1:-1]:
                VDiskController.delete_snapshot(disk.guid, snapshot['guid'])

        # starting scrubber
        ScheduledTaskController.gather_scrub_work()
        # waiting for model to catch up
        time.sleep(120)
        for disk in vds:
            disk.invalidate_dynamics(['statistics'])
        # checking result of scrub work
        vds = GeneralVDisk.get_vdisks()
        for disk in vds:
            if disk.statistics['stored'] >= disk_backend_data[disk.guid]:
                issues_found += "No scrub work was applied to {0} disk.\nOld stored data:{1}\nNew stored data:{2}\n".format(disk.name,
                                                                                                                            disk_backend_data[disk.guid],
                                                                                                                            disk.statistics['stored'])

        # cleanup
        # removing vmachines
        for vm_number in range(nr_of_disks):
            vmachine_name = "machine-{0}".format(vm_number)
            GeneralVMachine.logger.info("Removing vmachine {0}".format(vmachine_name))
            out, err, _ = General.execute_command('virsh undefine {0}'.format(vmachine_name))
        # removing vdisk
        GeneralVMachine.logger.info("Removing vpool vdisks from {0} vpool".format(vpool_name))
        out, err, _ = General.execute_command("rm -rf /mnt/{0}/*.raw".format(vpool_name))
        if err:
            GeneralVMachine.logger.error("Error while removing vdisks: {0}".format(err))

        assert issues_found == "", "Following issues appeared:\n{0}".format(issues_found)
