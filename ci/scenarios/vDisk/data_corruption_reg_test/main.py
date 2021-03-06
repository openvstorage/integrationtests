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
import random
from ci.autotests import gather_results
from ci.scenario_helpers.ci_constants import CIConstants
from ci.scenario_helpers.data_writing import DataWriter
from ci.scenario_helpers.setup import SetupHelper
from ci.scenario_helpers.vm_handler import VMHandler
from ovs.extensions.generic.logger import Logger
from ovs_extensions.generic.remote import remote
from ovs.extensions.generic.sshclient import SSHClient


# @ todo fix this test. No validation, just launches the vdbench async
class DataCorruptionTester(CIConstants):
    """
    This is a regression test for https://github.com/openvstorage/integrationtests/issues/468

    Required packages: qemu-kvm libvirt0 python-libvirt virtinst genisoimage
    Required commands after ovs installation and required packages: usermod -a -G ovs libvirt-qemu
    """

    CASE_TYPE = 'STABILITY'
    TEST_NAME = 'ci_scenario_data_corruption'
    LOGGER = Logger('scenario-{0}'.format(TEST_NAME))

    VM_NAME = 'Data-corruption-test'
    VDBENCH_ZIP = "http://fileserver.cloudfounders.com/Operations/IT/Software/vdbench/vdbench.zip"  # Fetch location
    VM_VDBENCH_ZIP = "/root/vdbench.zip"  # Fetch destination

    AMOUNT_THREADS = 4  # Amount of workers
    AMOUNT_DATA_ERRORS = 1  # Nr of data errors that may occur
    VDBENCH_TIME = 120 * 60  # Time of run (seconds)
    VDBENCH_INTERVAL = 1  # Reporting interval (seconds)
    IO_RATE = 'max'  # Rate of the IO
    XFERSIZE = '(4k,25.68,8k,26.31,16k,6.4,32k,7.52,60k,10.52,128k,9.82,252k,7.31,504k,6.19,984k,0.23,1032k,0.02)'  # Transfer sizes
    READ_PERCENTAGE = 50  # RW percent
    RANDOM_SEEK_PERCENTAGE = 100  # Random seeks to throw in

    VM_FILENAME = "/root/vdbench_file"  # File to use for IO
    VM_VDBENCH_CFG_PATH = "/root/vdbench_run.cfg"

    @staticmethod
    @gather_results(CASE_TYPE, LOGGER, TEST_NAME, log_components=[{'framework': ['ovs-workers']}, 'volumedriver'])
    def main(blocked):
        """
        Run all required methods for the test

        status depends on attributes in class: ci.api_lib.helpers.testtrailapi.TestrailResult
        case_type depends on attributes in class: ci.api_lib.helpers.testtrailapi.TestrailCaseType
        :param blocked: was the test blocked by other test?
        :return: results of test
        :rtype: dict
        """
        _ = blocked
        DataCorruptionTester.start_test()

    @classmethod
    def start_test(cls):
        """
        Run the entire data_corruption_reg_test
        :return:
        """
        storagedriver, cloud_image_path, cloud_init_loc, is_ee = cls.setup()
        compute_ip = storagedriver.storage_ip
        protocol = storagedriver.cluster_node_config['network_server_uri'].split(':')[0]
        edge_details = {'port': storagedriver.ports['edge'],
                        'hostname': storagedriver.storage_ip,
                        'protocol': protocol}
        edge_user_info = {}
        if is_ee is True:
            edge_user_info = cls.get_shell_user()
            edge_details.update(edge_user_info)
        vm_handler = VMHandler(hypervisor_ip=compute_ip)
        vm_handler.prepare_vm_disks(source_storagedriver=storagedriver,
                                    cloud_image_path=cloud_image_path,
                                    cloud_init_loc=cloud_init_loc,
                                    vm_name=cls.VM_NAME,
                                    data_disk_size=cls.AMOUNT_TO_WRITE,
                                    edge_user_info=edge_user_info)
        vm_info = vm_handler.create_vms(edge_configuration=edge_details,
                                        timeout=cls.VM_CREATION_TIMEOUT)
        try:
            cls.run_test(storagedriver=storagedriver, vm_info=vm_info)
        finally:
            vm_handler.destroy_vms(vm_info=vm_info)

    @classmethod
    def setup(cls, logger=LOGGER):
        """
        Set up suitable environment for the test
        :param logger: Logger instance
        :return: ovs.log.log_handler.LogHandler
        """
        vpool = SetupHelper.get_vpool_with_2_storagedrivers()

        source_storagedriver = random.choice(vpool.storagedrivers)
        logger.info('Chosen source storagedriver is: {0}'.format(source_storagedriver.storage_ip))

        client = SSHClient(source_storagedriver.storagerouter, username='root')  # Build ssh clients

        cloud_init_loc, is_ee = SetupHelper.setup_cloud_info(client, src_std=source_storagedriver)
        image_path = SetupHelper.check_images(client)
        return source_storagedriver, image_path, cloud_init_loc, is_ee

    @classmethod
    def run_test(cls, storagedriver, vm_info, logger=LOGGER):
        """
        Deploy a vdbench and see if the following bug is triggered (or other datacorruption bugs)
        https://github.com/openvstorage/integrationtests/issues/468
        :param storagedriver: storagedriver to use for the VM its vdisks
        :type storagedriver: ovs.dal.hybrids.storagedriver.StorageDriver
        :param logger: logging instance
        :type logger: ovs.log.log_handler.LogHandler
        :param vm_info: information about all vms
        :type vm_info: dict
        :return: None
        :rtype: NoneType
        """
        with remote(storagedriver.storage_ip, [SSHClient]) as rem:
            try:
                for vm_name, vm_data in vm_info.iteritems():
                    vm_client = rem.SSHClient(vm_data['ip'], cls.VM_USERNAME, cls.VM_PASSWORD)
                    vm_client.file_create('/mnt/data/{0}.raw'.format(vm_data['create_msg']))
                    vm_data['client'] = vm_client
                    # install fio on the VM
                    logger.info('Installing vdbench on {0}.'.format(vm_name))
                    DataWriter.deploy_vdbench(client=vm_data['client'],
                                              zip_remote_location=cls.VDBENCH_ZIP,
                                              unzip_location=cls.VM_VDBENCH_ZIP,
                                              amount_of_errors=cls.AMOUNT_DATA_ERRORS,
                                              vdbench_config_path=cls.VM_VDBENCH_CFG_PATH,
                                              lun_location=cls.VM_FILENAME,
                                              thread_amount=cls.AMOUNT_THREADS,
                                              write_amount=cls.AMOUNT_TO_WRITE,
                                              xfersize=cls.XFERSIZE,
                                              read_percentage=cls.READ_PERCENTAGE,
                                              random_seek_percentage=cls.RANDOM_SEEK_PERCENTAGE,
                                              io_rate=cls.IO_RATE,
                                              duration=cls.VDBENCH_TIME,
                                              interval=cls.VDBENCH_INTERVAL
                                              )
                for vm_name, vm_data in vm_info.iteritems():
                    logger.info('Starting VDBENCH on {0}!'.format(vm_name))
                    screen_names, output_files = DataWriter.write_data_vdbench(client=vm_data['client'],
                                                                               binary_location=cls.VM_VDBENCH_ZIP.replace('.zip', ''),
                                                                               config_location=cls.VM_VDBENCH_CFG_PATH)
                    vm_data['screen_names'] = screen_names
                logger.info('Finished VDBENCH without errors!')
                logger.info('No data corruption detected!')
            finally:
                for vm_name, vm_data in vm_info.iteritems():
                    for screen_name in vm_data.get('screen_names', []):
                        logger.debug('Stopping screen {0} on {1}.'.format(screen_name, vm_data['client'].ip))
                        vm_data['client'].run(['screen', '-S', screen_name, '-X', 'quit'])
                    vm_data['screen_names'] = []


def run(blocked=False):
    """
    Run a test
    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return DataCorruptionTester().main(blocked)


if __name__ == '__main__':
    # @todo remove print
    print run()
