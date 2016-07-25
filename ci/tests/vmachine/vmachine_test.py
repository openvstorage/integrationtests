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
from ci.tests.general.general_hypervisor import Hypervisor
from ci.tests.general.general_vmachine import GeneralVMachine
from ci.tests.general.general_vpool import GeneralVPool
from ovs.dal.lists.vdisklist import VDiskList
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

        hypervisor = Hypervisor.get(vpool)

        for disk_number in range(nr_of_disks):
            disk_name = "disk-{0}".format(disk_number)
            GeneralVMachine.logger.info("Starting RAW disk creation")
            template_folder = GeneralVMachine.template_target_folder
            image_name = GeneralVMachine.template_image
            out, err, _ = General.execute_command('qemu-img convert -O raw {0}{1} /mnt/{2}/{3}.raw'.format(template_folder, image_name, vpool_name, disk_name))
            if err:
                GeneralVMachine.logger.error("Error while creating raw disk: {0}".format(err))

        vpool = GeneralVPool.get_vpool_by_name(vpool_name=vpool_name)
        assert len(vpool.vdisks) == nr_of_disks,\
            "Only {0} out of {1} VDisks have been created".format(len(vpool.vdisks), nr_of_disks)

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
            vms = hypervisor.sdk.get_vms()
            if len(vms) == nr_of_disks:
                counter = 0
            else:
                counter -= 1
                time.sleep(timer_step)
        vms = hypervisor.sdk.get_vms()
        assert len(vms) == nr_of_disks,\
            "Only {0} out of {1} VMachines have been created after {2} seconds".format(len(vms), nr_of_disks, timeout)

        # Waiting for 1 minute of FIO activity on vmachine
        time.sleep(60)
        vms = hypervisor.sdk.get_vms()
        for vm in vms:
            assert hypervisor.sdk.get_power_state(vm.name()) == 'RUNNING',\
                "Machine {0} has wrong status on the hypervisor: {1}".format(vm.name(), vm.hypervisor_status)

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
            vms = hypervisor.sdk.get_vms()
            if len(vms):
                counter -= 1
                time.sleep(timer_step)
            else:
                counter = 0
        vms = hypervisor.sdk.get_vms()
        assert len(vms) == 0,\
            "Still some machines left on the vpool after waiting for {0} seconds: {1}".format(timeout,
                                                                                              [vm.name() for vm in vms])

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
        assert len(vpool.vdisks) == 0,\
            "Still some disks left on the vpool after waiting {0} seconds: {1}".format(timeout, vpool.vdisks_guids)

    @staticmethod
    def check_scrubbing_test():
        """
        Check scrubbing of vdisks test
        """
        initial_counter = 300
        step = 5
        vdisk = None
        vpool_name = General.get_config().get('vpool', 'name')
        vpool = GeneralVPool.get_vpool_by_name(vpool_name=vpool_name)
        assert vpool, "No vpool found where one was expected"

        template_folder = GeneralVMachine.template_target_folder
        image_name = GeneralVMachine.template_image

        disk_name = "scrubdisk"
        GeneralVMachine.logger.info("Starting RAW disk creation")
        out, err, _ = General.execute_command('qemu-img convert -O raw {0}{1} /mnt/{2}/{3}.raw'.format(template_folder, image_name, vpool_name, disk_name))
        if err:
            GeneralVMachine.logger.error("Error while creating raw disk: {0}".format(err))

        def snapshot_vdisk(vdisk):
            metadata = {'label': 'snap-' + vdisk.name,
                        'is_consistent': True,
                        'timestamp': time.time(),
                        'is_automatic': False,
                        'is_sticky': False}
            VDiskController.create_snapshot(vdisk.guid, metadata)

        counter = initial_counter
        while counter and vdisk is None:
            time.sleep(step)
            vdisk = VDiskList.get_by_devicename_and_vpool('/' + disk_name + '.raw', vpool)
            counter -= step
        assert counter > 0, "Vdisk with name {0} didn't appear in the model after 60 seconds".format(disk_name)
        # snapshot disks for the first time
        snapshot_vdisk(vdisk)
        counter = initial_counter
        while counter > 0:
            time.sleep(step)
            out, err, _ = General.execute_command('dd if=/dev/zero of=/mnt/{0}/{1}.raw bs=10K count=1000 conv=notrunc'.format(vpool_name, disk_name))
            counter -= step
            snapshot_vdisk(vdisk)

        # saving disk 'stored' info / the only attribute that is lowered after scrubbing
        vdisk.invalidate_dynamics(['statistics'])
        disk_backend_data = vdisk.statistics['stored']

        # deleting middle snapshots
        for snapshot in vdisk.snapshots[1:-1]:
            VDiskController.delete_snapshot(vdisk.guid, snapshot['guid'])

        # starting scrubber
        ScheduledTaskController.gather_scrub_work()
        # waiting for model to catch up
        counter = initial_counter
        while counter > 0:
            time.sleep(step)
            vdisk.invalidate_dynamics(['statistics'])
            # checking result of scrub work
            if vdisk.statistics['stored'] < disk_backend_data:
                GeneralVMachine.logger.info("It took {0} seconds for the value to change from {1} to {2}\n".format((initial_counter - counter) * step,
                                                                                                                   disk_backend_data,
                                                                                                                   vdisk.statistics['stored']))
                break
            counter -= step
        # removing vdisk
        GeneralVMachine.logger.info("Removing vpool vdisks from {0} vpool".format(vpool_name))
        out, err, _ = General.execute_command("rm -rf /mnt/{0}/*.raw".format(vpool_name))
        if err:
            GeneralVMachine.logger.error("Error while removing vdisk: {0}".format(err))

        assert counter > 0, "Scrubbing didn't run as expected, backend size of vdisk remained at {0}:\n".format(disk_backend_data)
