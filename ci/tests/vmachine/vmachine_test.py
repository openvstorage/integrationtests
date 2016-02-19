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
Virtual Machine testsuite
"""

import time

from ci.tests.general.connection import Connection
from ci.tests.general.general import General
from ci.tests.general.general_alba import GeneralAlba
from ci.tests.general.general_mgmtcenter import GeneralManagementCenter
from ci.tests.general.general_vpool import GeneralVPool
from ci.tests.general.logHandler import LogHandler


class TestVMachine(object):
    """
    Virtual Machine testsuite
    """
    logger = LogHandler.get('vmachines', name='vmachine')
    logger.logger.propagate = False

    api = Connection()
    tests_to_run = General.get_tests_to_run(General.get_test_level())
    template_image = 'debian.qcow2'
    template_target_folder = '/var/tmp/templates/'

    ######################
    # SETUP AND TEARDOWN #
    ######################

    @staticmethod
    def setup():
        """
        Make necessary changes before being able to run the tests
        :return: None
        """
        # Download the template
        cmd = '[ -d {0} ] && echo "Dir exists" || echo "Dir does not exists"'.format(TestVMachine.template_target_folder)
        out, err = General.execute_command(cmd)
        if err:
            TestVMachine.logger.error("Error while executing command {1}: {0}".format(err, cmd))
        if 'not' not in out:
            General.execute_command('rm -rf {0}'.format(TestVMachine.template_target_folder))
            General.execute_command('mkdir {0}'.format(TestVMachine.template_target_folder))
        grid_ip = General.get_config().get('main', 'grid_ip')

        if grid_ip.split('.')[0] == '172' and grid_ip.split('.')[1] == '20':
            server_location = 'http://172.20.3.8/templates/openvstorage'
        else:
            server_location = 'http://sso-qpackages-loch.cloudfounders.com/templates/openvstorage'

        TestVMachine.logger.info("Getting template from {0}".format(server_location))
        out, err = General.execute_command('wget -P {0} {1}{2}{3}'.format(TestVMachine.template_target_folder, server_location, '/fio_debian/', TestVMachine.template_image))
        if err:
            TestVMachine.logger.error("Error while downloading template: {0}".format(err))
        out, err = General.execute_command('chown root {0}{1}'.format(TestVMachine.template_target_folder, TestVMachine.template_image))
        if err:
            TestVMachine.logger.error("Error while changing user owner to root for template: {0}".format(err))

        GeneralAlba.add_alba_backend()
        GeneralManagementCenter.create_generic_mgmt_center()
        GeneralVPool.add_vpool()

    @staticmethod
    def teardown():
        """
        Removal actions of possible things left over after the test-run
        :return: None
        """
        vpool_name = General.get_config().get('vpool', 'name')
        vpool = GeneralVPool.get_vpool_by_name(vpool_name)
        assert vpool is not None, "No vpool found where one was expected"
        TestVMachine.logger.info("Cleaning vpool")
        GeneralVPool.remove_vpool(vpool)
        GeneralAlba.unclaim_disks_and_remove_alba_backend()
        TestVMachine.logger.info("Cleaning management center")
        management_centers = TestVMachine.api.get_components('mgmtcenters')
        for mgmcenter in management_centers:
            GeneralManagementCenter.remove_mgmt_center(mgmcenter['guid'])

    #########
    # TESTS #
    #########

    @staticmethod
    def vms_with_fio_test():
        """
        Test virtual machines with FIO
        """
        General.check_prereqs(testcase_number=1,
                              tests_to_run=TestVMachine.tests_to_run)

        timeout = 30
        timer_step = 5
        nr_of_disks = 10
        vpool_name = General.get_config().get('vpool', 'name')
        vpool_list = TestVMachine.api.get_component_by_name('vpools', vpool_name)
        assert len(vpool_list), "No vpool found where one was expected"
        vpool = vpool_list[0]
        for disk_number in range(nr_of_disks):
            disk_name = "disk-{0}".format(disk_number)
            TestVMachine.logger.info("Starting RAW disk creation")
            template_folder = TestVMachine.template_target_folder
            image_name = TestVMachine.template_image
            out, err = General.execute_command('qemu-img convert -O raw {0}{1} /mnt/{2}/{3}.raw'.format(template_folder, image_name, vpool['name'], disk_name))
            if err:
                TestVMachine.logger.error("Error while creating raw disk: {0}".format(err))

        vpool_list = TestVMachine.api.get_component_by_name('vpools', vpool_name)
        vpool = vpool_list[0]
        assert len(vpool['vdisks_guids']) == nr_of_disks, "Only {0} out of {1} VDisks have been created".format(len(vpool['vdisks_guids']), nr_of_disks)

        for vm_number in range(nr_of_disks):
            machine_name = "machine-{0}".format(vm_number)
            disk_name = "disk-{0}".format(vm_number)
            TestVMachine.logger.info("Starting vmachine creation from RAW disk")
            out, err = General.execute_command('virt-install --connect qemu:///system -n {0} -r 512 --disk /mnt/{1}/{2}.raw,'
                                               'device=disk --noautoconsole --graphics vnc,listen=0.0.0.0 --vcpus=1 --network network=default,mac=RANDOM,'
                                               'model=e1000 --import'.format(machine_name, vpool['name'], disk_name))
            if err:
                TestVMachine.logger.error("Error while creating vmachine: {0}".format(err))

        counter = timeout / timer_step
        while counter > 0:
            vms = TestVMachine.api.get_components('vmachines')
            if len(vms) == nr_of_disks:
                counter = 0
            else:
                counter -= 1
                time.sleep(timer_step)
        vms = TestVMachine.api.get_components('vmachines')
        assert len(vms) == nr_of_disks, "Only {0} out of {1} VMachines have been created after {2} seconds".format(len(vms), nr_of_disks, timeout)

        # Waiting for 5 minutes of FIO activity on the vmachines
        time.sleep(300)
        vms = TestVMachine.api.get_components('vmachines')
        for vm in vms:
            assert vm['hypervisor_status'] in ['RUNNING'], "Machine {0} has wrong status on the hypervisor: {1}".format(vm['name'], vm['hypervisor_status'])

        for vm_number in range(nr_of_disks):
            vmachine_name = "machine-{0}".format(vm_number)
            TestVMachine.logger.info("Removing {0} vmachine".format(vmachine_name))
            out, err = General.execute_command('virsh destroy {0}'.format(vmachine_name))
            if err:
                TestVMachine.logger.error("Error while stopping vmachine: {0}".format(err))
            out, err = General.execute_command('virsh undefine {0}'.format(vmachine_name))
            if err:
                TestVMachine.logger.error("Error while removing vmachine: {0}".format(err))

        counter = timeout / timer_step
        while counter > 0:
            vms = TestVMachine.api.get_components('vmachines')
            if len(vms):
                counter -= 1
                time.sleep(timer_step)
            else:
                counter = 0
        vms = TestVMachine.api.get_components('vmachines')
        assert len(vms) == 0, "Still some machines left on the vpool after waiting for {0} seconds: {1}".format(timeout, vms)

        TestVMachine.logger.info("Removing vpool vdisks from {0} vpool".format(vpool_name))
        out, err = General.execute_command("rm -rf /mnt/{0}/*.raw".format(vpool_name))
        if err:
            TestVMachine.logger.error("Error while removing vdisks: {0}".format(err))

        counter = timeout / timer_step
        while counter > 0:
            vpool = TestVMachine.api.get_component_by_name('vpools', vpool_name)[0]
            if len(vpool['vdisks_guids']):
                counter -= 1
                time.sleep(timer_step)
            else:
                counter = 0
        vpool = TestVMachine.api.get_component_by_name('vpools', vpool_name)[0]
        assert len(vpool['vdisks_guids']) == 0, "Still some disks left on the vpool after waiting {0} seconds: {1}".format(timeout, vpool['vdisks_guids'])
