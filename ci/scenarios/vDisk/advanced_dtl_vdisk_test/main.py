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
import time
from ci.api_lib.helpers.domain import DomainHelper
from ci.api_lib.helpers.hypervisor.hypervisor import HypervisorFactory
from ci.api_lib.helpers.storagedriver import StoragedriverHelper
from ci.api_lib.helpers.system import SystemHelper
from ci.api_lib.helpers.vdisk import VDiskHelper
from ci.autotests import gather_results
from ci.api_lib.helpers.thread import ThreadHelper
from ci.scenario_helpers.ci_constants import CIConstants
from ovs.extensions.generic.remote import remote
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.services.service import ServiceManager
from ovs.log.log_handler import LogHandler
from ci.scenario_helpers.data_writing import DataWriter
from ci.scenario_helpers.threading_handlers import ThreadingHandler
from ci.scenario_helpers.vm_handler import VMHandler
from ci.api_lib.helpers.network import NetworkHelper


class AdvancedDTLTester(CIConstants):
    """
    Exercice HA with a VM via edge & KVM

    Required packages: qemu-kvm libvirt0 python-libvirt virtinst genisoimage
    Required commands after ovs installation and required packages: usermod -a -G ovs libvirt-qemu

    For this test the regular domain can only be 1 choice
    """

    CASE_TYPE = 'FUNCTIONAL'
    TEST_NAME = 'ci_scenario_advanced_dtl_test'
    LOGGER = LogHandler.get(source='scenario', name=TEST_NAME)
    IO_TIME = 60
    VM_NAME = 'DTL-test'

    IO_PATTERN = (100, 0)  # read, write
    # timeout between checks
    MIGRATE_TIMEOUT = 30
    MIGRATE_CHECKS = 10

    # validate dtl
    VM_FILENAME = '/root/dtl_file'
    VM_RANDOM = '/root/random_file'

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
        return AdvancedDTLTester.start_test()

    @classmethod
    def start_test(cls, vm_amount=1, hypervisor_info=CIConstants.HYPERVISOR_INFO):
        api = cls.get_api_instance()
        cluster_info, cloud_image_path, cloud_init_loc = cls.setup()
        compute_ip = cluster_info['storagerouters']['compute'].ip
        listening_port = NetworkHelper.get_free_port(compute_ip)

        source_storagedriver = cluster_info['storagedrivers']['source']
        protocol = source_storagedriver.cluster_node_config['network_server_uri'].split(':')[0]
        edge_details = {'port': source_storagedriver.ports['edge'], 'hostname': source_storagedriver.storage_ip,
                        'protocol': protocol}

        computenode_hypervisor = HypervisorFactory.get(compute_ip,
                                                       hypervisor_info['user'],
                                                       hypervisor_info['password'],
                                                       hypervisor_info['type'])

        vm_info, connection_messages, volume_amount = VMHandler.prepare_vm_disks(
            source_storagedriver=source_storagedriver,
            cloud_image_path=cloud_image_path,
            cloud_init_loc=cloud_init_loc,
            api=api,
            vm_amount=vm_amount,
            port=listening_port,
            hypervisor_ip=compute_ip,
            vm_name=cls.VM_NAME,
            data_disk_size=cls.AMOUNT_TO_WRITE * 2)
        vm_info = VMHandler.create_vms(ip=compute_ip,
                                       port=listening_port,
                                       connection_messages=connection_messages,
                                       vm_info=vm_info,
                                       edge_details=edge_details,
                                       hypervisor_client=computenode_hypervisor,
                                       timeout=cls.VM_WAIT_TIME)
        cls.run_test(vm_info=vm_info, cluster_info=cluster_info, disk_amount=volume_amount)

    @classmethod
    def setup(cls, logger=LOGGER):
        #################
        # PREREQUISITES #
        #################
        """
        Setup the advanced dtl test
        """
        #################
        # PREREQUISITES #
        #################
        destination_str, source_str, compute_str = cls.get_storagerouters_for_ha()
        destination_storagedriver = None
        source_storagedriver = None
        storagedrivers_domain_sorted = DomainHelper.get_storagedrivers_in_same_domain(domain_guid=source_str.regular_domains[0])
        for storagedriver in storagedrivers_domain_sorted:
            if len(storagedriver.vpool.storagedrivers) < 2:
                continue
            if storagedriver.guid in destination_str.storagedrivers_guids:
                if destination_storagedriver is None and (source_storagedriver is None or source_storagedriver.vpool_guid == storagedriver.vpool_guid):
                    destination_storagedriver = storagedriver
                    logger.info('Chosen destination storagedriver is: {0}'.format(destination_storagedriver.storage_ip))
                continue
            if storagedriver.guid in source_str.storagedrivers_guids:
                # Select if the source driver isn't select and destination is also unknown or the storagedriver has matches with the same vpool
                if source_storagedriver is None and (destination_storagedriver is None or destination_storagedriver.vpool_guid == storagedriver.vpool_guid):
                    source_storagedriver = storagedriver
                    logger.info('Chosen source storagedriver is: {0}'.format(source_storagedriver.storage_ip))
                continue
        assert source_storagedriver is not None and destination_storagedriver is not None, 'We require at least two storagedrivers within the same domain.'

        to_be_downed_client = SSHClient(source_str, username='root')  # Build ssh clients
        compute_client = SSHClient(compute_str, username='root')

        # Check if enough images available
        images = cls.get_images()
        assert len(images) >= 1, 'We require an cloud init bootable image file.'
        image_path = images[0]
        assert to_be_downed_client.file_exists(image_path), 'Image `{0}` does not exists on `{1}`!'.format(images[0], to_be_downed_client.ip)

        # Get the cloud init file
        cloud_init_loc = cls.CLOUD_INIT_DATA.get('script_dest')
        to_be_downed_client.run(['wget', cls.CLOUD_INIT_DATA.get('script_loc'), '-O', cloud_init_loc])
        to_be_downed_client.file_chmod(cloud_init_loc, 755)
        assert to_be_downed_client.file_exists(cloud_init_loc), 'Could not fetch the cloud init script'
        missing_packages = SystemHelper.get_missing_packages(to_be_downed_client.ip, cls.REQUIRED_PACKAGE_CLOUD_INIT)
        assert len(missing_packages) == 0, 'Missing {0} package(s) on `{1}`: {2}'.format(len(missing_packages),
                                                                                         to_be_downed_client.ip,
                                                                                         missing_packages)
        missing_packages = SystemHelper.get_missing_packages(compute_client.ip, cls.REQUIRED_PACKAGES_HYPERVISOR)
        assert len(missing_packages) == 0, 'Missing {0} package(s) on `{1}`: {2}'.format(len(missing_packages),
                                                                                         compute_client.ip,
                                                                                         missing_packages)

        cluster_info = {'storagerouters': {'destination': destination_str,
                                           'source': source_str,
                                           'compute': compute_str},
                        'storagedrivers': {'destination': destination_storagedriver,
                                           'source': source_storagedriver}}

        return cluster_info, image_path, cloud_init_loc

    @classmethod
    def run_test(cls, vm_info, cluster_info, disk_amount, logger=LOGGER):
        """
        Tests the DTL using a virtual machine which will write in his own filesystem
        Expects last data to be pulled from the DTL and not backend
        :param cluster_info: information about the cluster, contains all dal objects
        :type cluster_info: dict
        :return: None
        :rtype: NoneType
        """
        source_std = cluster_info['storagedrivers']['source']
        source_client = SSHClient(source_std.storagerouter, username='root')

        compute_str = cluster_info['storagerouters']['compute']
        compute_client = SSHClient(compute_str)

        # setup hypervisor details
        parent_hypervisor = HypervisorFactory.get(AdvancedDTLTester.PARENT_HYPERVISOR_INFO['ip'],
                                                  AdvancedDTLTester.PARENT_HYPERVISOR_INFO['user'],
                                                  AdvancedDTLTester.PARENT_HYPERVISOR_INFO['password'],
                                                  AdvancedDTLTester.PARENT_HYPERVISOR_INFO['type'])

        vm_to_stop = cls.PARENT_HYPERVISOR_INFO['vms'][source_std.storage_ip]['name']
        vdisk_info = {}
        for vm_name, vm_object in vm_info.iteritems():
            for vdisk in vm_object['vdisks']:
                vdisk_info.update({vdisk.name: vdisk})

        # Cache to validate properties
        values_to_check = {
            'source_std': source_std.serialize()
        }
        with remote(compute_str.ip, [SSHClient]) as rem:
            threads = {'evented': {'io': {'pairs': [], 'r_semaphore': None},
                                   'snapshots': {'pairs': [], 'r_semaphore': None}}}
            vm_downed = False
            output_files = []
            try:
                for vm_name, vm_data in vm_info.iteritems():
                    vm_client = rem.SSHClient(vm_data['ip'], cls.VM_USERNAME, cls.VM_PASSWORD)
                    vm_client.file_create('/mnt/data/{0}.raw'.format(vm_data['create_msg']))
                    vm_data['client'] = vm_client
                    # Load dd, md5sum, screen & fio in memory
                    vm_data['client'].run(['dd', 'if=/dev/urandom', 'of={0}'.format(cls.VM_RANDOM), 'bs=1M', 'count=2'])
                    vm_data['client'].run(['md5sum', cls.VM_RANDOM])

                logger.error("Starting to stop proxy services")
                for proxy in source_std.alba_proxies:
                    ServiceManager.restart_service(proxy.service.name, client=source_client)

                logger.info('Starting to WRITE file while proxy is offline. All data should be stored in the DTL!')
                for vm_name, vm_data in vm_info.iteritems():
                    vm_data['client'].run('dd if=/dev/urandom of={0} bs=1M count=2'.format(AdvancedDTLTester.VM_FILENAME).split())
                    original_md5sum = ' '.join(vm_data['client'].run(['md5sum', AdvancedDTLTester.VM_FILENAME]).split())
                    vm_data['original_md5sum'] = original_md5sum
                    logger.info('Original MD5SUM for VM {0}: {1}.'.format(vm_name, original_md5sum))
                logger.info('Finished to WRITE file while proxy is offline!')
                logger.info("Starting fio to generate IO for failing over.".format(AdvancedDTLTester.IO_TIME))
                io_thread_pairs, monitoring_data, io_r_semaphore = ThreadingHandler.start_io_polling_threads(
                    volume_bundle=vdisk_info)
                threads['evented']['io']['pairs'] = io_thread_pairs
                threads['evented']['io']['r_semaphore'] = io_r_semaphore
                for vm_name, vm_data in vm_info.iteritems():  # Write data
                    screen_names, output_files = DataWriter.write_data(client=vm_data['client'],
                                                                       cmd_type='fio',
                                                                       configuration=cls.IO_PATTERN,
                                                                       file_locations=['/mnt/data/{0}.raw'.format(vm_data['create_msg'])],
                                                                       data_to_write=cls.AMOUNT_TO_WRITE)
                    vm_data['screen_names'] = screen_names
                logger.info('Doing IO for {0}s before bringing down the node.'.format(cls.IO_TIME))
                ThreadingHandler.keep_threads_running(r_semaphore=threads['evented']['io']['r_semaphore'],
                                                      threads=threads['evented']['io']['pairs'],
                                                      shared_resource=monitoring_data,
                                                      duration=cls.IO_TIME)
                ##############################################
                # Bringing original owner of the volume down #
                ##############################################
                VMHandler.stop_vm(hypervisor=parent_hypervisor, vmid=vm_to_stop)
                vm_downed = True
                downed_time = time.time()
                # Start IO polling to verify nothing went down
                ThreadingHandler.poll_io(r_semaphore=threads['evented']['io']['r_semaphore'],
                                         required_thread_amount=len(threads),
                                         shared_resource=monitoring_data,
                                         downed_time=downed_time,
                                         timeout=cls.HA_TIMEOUT,
                                         output_files=output_files,
                                         client=compute_client,
                                         disk_amount=disk_amount)
                logger.info('Starting to validate move...')
                AdvancedDTLTester._validate_move(values_to_check)
                logger.info('Finished to validate move!')

                logger.info('Validate if DTL is working correctly!')
                unmatching_checksum_vms = []
                for vm_name, vm_data in vm_info.iteritems():
                    current_md5sum = ' '.join(vm_data['client'].run(['md5sum', AdvancedDTLTester.VM_FILENAME]).split())
                    if vm_data['original_md5sum'] != current_md5sum:
                        unmatching_checksum_vms.append(vm_name)
                assert len(unmatching_checksum_vms) == 0, 'Not all data was read from the DTL. Checksums do not line up for {}'.format(', '.join(unmatching_checksum_vms))
                logger.info('DTL is working correctly!')
            finally:
                if vm_downed is True:
                    VMHandler.start_vm(parent_hypervisor, vm_to_stop)
                for thread_category, thread_collection in threads['evented'].iteritems():
                    ThreadHelper.stop_evented_threads(thread_collection['pairs'], thread_collection['r_semaphore'])
                for vm_name, vm_data in vm_info.iteritems():
                    for screen_name in vm_data.get('screen_names', []):
                        logger.debug('Stopping screen {0} on {1}.'.format(screen_name, vm_data['client'].ip))
                        vm_data['client'].run(['screen', '-S', screen_name, '-X', 'quit'])
                    vm_data['screen_names'] = []

    @staticmethod
    def _validate_move(values_to_check):
        """
        Validates the move test. Checks IO, and checks for dal changes
        :param values_to_check: dict with values to validate if they updated
        :type values_to_check: dict
        :return: None
        :rtype: NoneType
        """
        source_std = StoragedriverHelper.get_storagedriver_by_guid(values_to_check['source_std']['guid'])
        source_std.invalidate_dynamics([])
        vdisk = VDiskHelper.get_vdisk_by_guid(values_to_check['vdisk']['guid'])
        AdvancedDTLTester.LOGGER.info('Source is documented as {0} and vdisk is now on {1}'.format(source_std.storagerouter.guid, vdisk.storagerouter_guid))
        checks = 0
        while checks <= AdvancedDTLTester.MIGRATE_CHECKS:
            if vdisk.storagerouter_guid != source_std.storagerouter.guid:
                AdvancedDTLTester.LOGGER.info('Move vdisk was successful according to the dal, '
                                              'source was {0} and destination is now {1}'
                                              .format(source_std.storagerouter.guid, vdisk.storagerouter_guid))
                return
            else:
                AdvancedDTLTester.LOGGER.info('Move vdisk was NOT YET successful according to the dal, '
                                              'source was {0} and destination is now {1}, sleeping for {2} seconds'
                                              .format(source_std.storagerouter.guid, vdisk.storagerouter_guid,
                                                      AdvancedDTLTester.MIGRATE_TIMEOUT))
                checks += 1
                time.sleep(AdvancedDTLTester.MIGRATE_TIMEOUT)
        raise ValueError("Move vdisk has FAILED!")


def run(blocked=False):
    """
    Run a test
    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return AdvancedDTLTester().main(blocked)

if __name__ == '__main__':
    run()
