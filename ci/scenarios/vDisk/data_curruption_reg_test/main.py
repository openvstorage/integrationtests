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
from ci.api_lib.helpers.vpool import VPoolHelper
from ci.api_lib.helpers.system import SystemHelper
from ci.scenario_helpers.ci_constants import CIConstants
from ovs.extensions.generic.remote import remote
from ovs.extensions.generic.sshclient import SSHClient
from ovs.log.log_handler import LogHandler
from ci.api_lib.helpers.network import NetworkHelper
from ci.scenario_helpers.vm_handler import VMHandler


class DataCorruptionTester(CIConstants):
    """
    This is a regression test for https://github.com/openvstorage/integrationtests/issues/468

    Required packages: qemu-kvm libvirt0 python-libvirt virtinst genisoimage
    Required commands after ovs installation and required packages: usermod -a -G ovs libvirt-qemu
    """

    CASE_TYPE = 'STABILITY'
    TEST_NAME = 'ci_scenario_data_corruption'
    LOGGER = LogHandler.get(source='scenario', name=TEST_NAME)
    SLEEP_TIME = 60
    SLEEP_TIME_BEFORE_SHUTDOWN = 30
    VM_CONNECTING_TIMEOUT = 5
    VM_CREATION_MESSAGE = 'I am created!'
    VM_NAME = 'Data-corruption-test'
    START_PARENT_TIMEOUT = 30
    VDBENCH_ZIP = "http://fileserver.cloudfounders.com/Operations/IT/Software/vdbench/vdbench.zip"
    VM_VDBENCH_ZIP = "/root/vdbench.zip"
    AMOUNT_THREADS = 4  # threads
    AMOUNT_TO_WRITE = 3  # in GB, size
    AMOUNT_DATA_ERRORS = 1  # data_errors
    VDBENCH_TIME = 7200  # in seconds
    VDBENCH_INTERVAL = 1  # in seconds
    WORKLOAD = ['wd1']  # wd
    IO_RATE = 'max'  # iorate
    RUNNAME = 'data_cor_run'  # rd
    # xfersize
    XFERSIZE = '(4k,25.68,8k,26.31,16k,6.4,32k,7.52,60k,10.52,128k,9.82,252k,7.31,504k,6.19,984k,0.23,1032k,0.02)'
    READ_PERCENTAGE = 50  # rdpct
    RANDOM_SEEK_PERCENTAGE = 100  # seekpct
    VM_FILENAME = "/root/vdbench_file"  # lun
    VM_VDBENCH_CFG_PATH = "/root/vdbench_run.cfg"

    @staticmethod
    def main(blocked):
        """
        Run all required methods for the test

        status depends on attributes in class: ci.api_lib.helpers.testtrailapi.TestrailResult
        case_type depends on attributes in class: ci.api_lib.helpers.testtrailapi.TestrailCaseType
        :param blocked: was the test blocked by other test?
        :return: results of test
        :rtype: dict
        """
        if not blocked:
            try:
                DataCorruptionTester.start_test()
                return {'status': 'PASSED', 'case_type': DataCorruptionTester.CASE_TYPE, 'errors': None}
            except Exception as ex:
                return {'status': 'FAILED', 'case_type': DataCorruptionTester.CASE_TYPE, 'errors': str(ex)}
        else:
            return {'status': 'BLOCKED', 'case_type': DataCorruptionTester.CASE_TYPE, 'errors': None}

    @classmethod
    def start_test(cls, vm_amount=1, hypervisor_info=CIConstants.HYPERVISOR_INFO):
        api = cls.get_api_instance()
        storagedriver, cloud_image_path, cloud_init_loc = cls.setup()
        compute_ip = storagedriver.storagerouter.storage_ip
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
                                    workload=cls.WORKLOAD,
                                    xfersize=cls.XFERSIZE,
                                    read_percentage=cls.READ_PERCENTAGE,
                                    random_seek_percentage=cls.RANDOM_SEEK_PERCENTAGE,
                                    name_of_run=cls.RUNNAME,
                                    io_rate=cls.IO_RATE,
                                    duration=cls.VDBENCH_TIME,
                                    interval=cls.VDBENCH_INTERVAL
                                    )
            for vm_name, vm_data in vm_info.iteritems():
                logger.info('Starting VDBENCH on {0}!'.format(vm_name))
                vm_data['client'].run('screen -S fio -dm bash -c "./vdbench -vr -f {0}"'.format(cls.VM_VDBENCH_CFG_PATH).split())
            logger.info('Finished VDBENCH without errors!')
            logger.info('No data corruption detected!')

    @staticmethod
    def _deploy_vdbench(client, zip_remote_location, unzip_location, amount_of_errors, vdbench_config_path, lun_location,
                        thread_amount, write_amount, workload, xfersize, read_percentage, random_seek_percentage,
                        name_of_run, io_rate, duration, interval, logger=LOGGER):
        client.run(['apt-get', 'install', 'unzip', 'openjdk-9-jre-headless', '-y'])
        client.run(['wget', zip_remote_location, '-O', unzip_location])
        logger.info('Successfully fetched vdbench ZIP')
        client.run(['unzip', unzip_location])
        logger.info('Successfully unzipped vdbench ZIP')
        config_lines = [
            '"data_errors={0}"'.format(amount_of_errors),
            '"sd=sd1,lun={0},threads={1},size={2}g"'.format(lun_location, thread_amount, write_amount),
            '"wd={0},sd=(sd1),xfersize={1},rdpct={2},seekpct={3},openflags=directio"'.format(workload, xfersize, read_percentage, random_seek_percentage),
            '"rd={0},iorate={1},elapsed={2},interval={3}"'.format(name_of_run, io_rate, duration, interval)
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
