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
from ci.api_lib.helpers.hypervisor.hypervisor import HypervisorFactory
from ci.api_lib.helpers.network import NetworkHelper
from ci.api_lib.helpers.vpool import VPoolHelper
from ci.api_lib.helpers.system import SystemHelper
from ci.autotests import gather_results
from ci.scenario_helpers.ci_constants import CIConstants
from ci.scenario_helpers.data_writing import DataWriter
from ci.scenario_helpers.vm_handler import VMHandler
from ovs.extensions.generic.remote import remote
from ovs.extensions.generic.sshclient import SSHClient
from ovs.log.log_handler import LogHandler


# @ todo fix this test. No validation and offloads to fio. Done refactoring though
# Initial fix also done. vdbench actually runs >>
class DataCorruptionTester(CIConstants):
    """
    This is a regression test for https://github.com/openvstorage/integrationtests/issues/468

    Required packages: qemu-kvm libvirt0 python-libvirt virtinst genisoimage
    Required commands after ovs installation and required packages: usermod -a -G ovs libvirt-qemu
    """

    CASE_TYPE = 'STABILITY'
    TEST_NAME = 'ci_scenario_data_corruption'
    LOGGER = LogHandler.get(source='scenario', name=TEST_NAME)

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
    @gather_results(CASE_TYPE, LOGGER, TEST_NAME)
    def main(blocked):
        """
        Run all required methods for the test

        status depends on attributes in class: ci.api_lib.helpers.testtrailapi.TestrailResult
        case_type depends on attributes in class: ci.api_lib.helpers.testtrailapi.TestrailCaseType
        :param blocked: was the test blocked by other test?
        :return: results of test
        :rtype: dict
        """
        DataCorruptionTester.start_test()

    @classmethod
    def start_test(cls, vm_amount=1, hypervisor_info=CIConstants.HYPERVISOR_INFO):
        api = cls.get_api_instance()
        storagedriver, cloud_image_path, cloud_init_loc = cls.setup()
        compute_ip = storagedriver.storage_ip
        listening_port = NetworkHelper.get_free_port(compute_ip)
        protocol = storagedriver.cluster_node_config['network_server_uri'].split(':')[0]
        edge_details = {'port': storagedriver.ports['edge'],
                        'hostname': storagedriver.storage_ip,
                        'protocol': protocol}

        computenode_hypervisor = HypervisorFactory.get(compute_ip,
                                                       hypervisor_info['user'],
                                                       hypervisor_info['password'],
                                                       hypervisor_info['type'])
        vm_info, connection_messages, volume_amount = VMHandler.prepare_vm_disks(
            source_storagedriver=storagedriver,
            cloud_image_path=cloud_image_path,
            cloud_init_loc=cloud_init_loc,
            api=api,
            vm_amount=vm_amount,
            port=listening_port,
            hypervisor_ip=compute_ip,
            vm_name=cls.VM_NAME,
            data_disk_size=cls.AMOUNT_TO_WRITE)
        vm_info = VMHandler.create_vms(ip=compute_ip,
                                       port=listening_port,
                                       connection_messages=connection_messages,
                                       vm_info=vm_info,
                                       edge_details=edge_details,
                                       hypervisor_client=computenode_hypervisor,
                                       timeout=cls.HA_TIMEOUT)
        cls.run_test(storagedriver=storagedriver, vm_info=vm_info)

    @classmethod
    def setup(cls, logger=LOGGER):
        vpool = None
        for vp in VPoolHelper.get_vpools():  # Get a suitable vpool with min. 2 storagedrivers
            if len(vp.storagedrivers) >= 2 and vp.configuration['dtl_mode'] == 'sync':
                vpool = vp
                break
        assert vpool is not None, 'Not enough vPools to test. We need at least a vPool with 2 storagedrivers'

        source_storagedriver = random.choice(vpool.storagedrivers)
        logger.info('Chosen source storagedriver is: {0}'.format(source_storagedriver.storage_ip))

        client = SSHClient(source_storagedriver.storagerouter, username='root')  # Build ssh clients

        # Check if enough images available
        images = cls.get_images()
        assert len(images) >= 1, 'We require an cloud init bootable image file.'
        image_path = images[0]
        assert client.file_exists(image_path), 'Image `{0}` does not exists on `{1}`!'.format(images[0], client.ip)

        # Get the cloud init file
        cloud_init_loc = cls.CLOUD_INIT_DATA.get('script_dest')
        client.run(['wget', cls.CLOUD_INIT_DATA.get('script_loc'), '-O', cloud_init_loc])
        client.file_chmod(cloud_init_loc, 755)
        assert client.file_exists(cloud_init_loc), 'Could not fetch the cloud init script'
        missing_packages = SystemHelper.get_missing_packages(client.ip, cls.REQUIRED_PACKAGE_CLOUD_INIT)
        assert len(missing_packages) == 0, 'Missing {0} package(s) on `{1}`: {2}'.format(len(missing_packages), client.ip, missing_packages)
        missing_packages = SystemHelper.get_missing_packages(client.ip, cls.REQUIRED_PACKAGES_HYPERVISOR)
        assert len(missing_packages) == 0, 'Missing {0} package(s) on `{1}`: {2}'.format(len(missing_packages), client.ip, missing_packages)

        return source_storagedriver, image_path, cloud_init_loc

    @classmethod
    def run_test(cls, storagedriver, vm_info, logger=LOGGER):
        """
        Deploy a vdbench and see if the following bug is triggered (or other datacorruption bugs)
        https://github.com/openvstorage/integrationtests/issues/468
        :param storagedriver: storagedriver to use for the VM its vdisks
        :type storagedriver: ovs.dal.hybrids.storagedriver.StorageDriver
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
                    cls._deploy_vdbench(client=vm_data['client'],
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
                    DataWriter.write_data(vm_data['client'], 'vdbench', vdbench_config={'bin_location': cls.VM_VDBENCH_ZIP.replace('.zip', ''),
                                                                                        'config_location': cls.VM_VDBENCH_CFG_PATH})
                    vm_data['client'].run('screen -S fio -dm bash -c "./vdbench -vr -f {0}"'.format(cls.VM_VDBENCH_CFG_PATH).split())
                    vm_data['screen_names'] = ['fio']
                logger.info('Finished VDBENCH without errors!')
                logger.info('No data corruption detected!')
            finally:
                for vm_name, vm_data in vm_info.iteritems():
                    for screen_name in vm_data.get('screen_names', []):
                        logger.debug('Stopping screen {0} on {1}.'.format(screen_name, vm_data['client'].ip))
                        vm_data['client'].run(['screen', '-S', screen_name, '-X', 'quit'])
                    vm_data['screen_names'] = []

    @staticmethod
    def _deploy_vdbench(client, zip_remote_location, unzip_location, amount_of_errors, vdbench_config_path, lun_location,
                        thread_amount, write_amount, xfersize, read_percentage, random_seek_percentage,
                        io_rate, duration, interval, logger=LOGGER):
        """
        Deploy a vdbench config file
        :param client: client location
        :param zip_remote_location: zip location to fetch vdbench from
        :param unzip_location: destination for download and unzip location
        :param amount_of_errors: how many errors before vdbench stops
        :param vdbench_config_path: configuration file path for vdbench
        :param lun_location: what file to use to write/read to
        :param thread_amount: amount of worker threads
        :param write_amount: amount of data to process in bytes
        :param xfersize: data transfer size 
        :param read_percentage: percentage to read
        :param random_seek_percentage: how often a seek to a random lba will be generated
        :param io_rate: 
        :param duration: 
        :param interval: 
        :param logger: 
        :return: 
        """
        client.run(['apt-get', 'install', 'unzip', 'openjdk-9-jre-headless', '-y'])
        client.run(['wget', zip_remote_location, '-O', unzip_location])
        logger.info('Successfully fetched vdbench ZIP')
        client.run(['unzip', unzip_location])
        logger.info('Successfully unzipped vdbench ZIP')
        config_lines = [
            'data_errors={0}'.format(amount_of_errors),
            'sd=sd1,lun={0},threads={1},size={2}'.format(lun_location, thread_amount, write_amount),  # Storage definition
            'wd=wd1,sd=(sd1),xfersize={0},rdpct={1},seekpct={2},openflags=directio'.format(xfersize, read_percentage, random_seek_percentage),  # Set the workload
            'rd=rd1,wd=wd1,iorate={0},elapsed={1},interval={2}'.format(io_rate, duration, interval)  # Setup a run definition
        ]
        client.file_write(vdbench_config_path, '\n'.join(config_lines))
        logger.info('Successfully deployed config')


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
