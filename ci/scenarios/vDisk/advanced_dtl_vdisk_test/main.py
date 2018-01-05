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
from ci.api_lib.helpers.hypervisor.hypervisor import HypervisorFactory
from ci.api_lib.helpers.storagedriver import StoragedriverHelper
from ci.api_lib.helpers.system import SystemHelper
from ci.api_lib.helpers.thread import ThreadHelper
from ci.autotests import gather_results
from ci.scenario_helpers.data_writing import DataWriter
from ci.scenario_helpers.fwk_handler import FwkHandler
from ci.scenario_helpers.setup import SetupHelper
from ci.scenario_helpers.threading_handlers import ThreadingHandler
from ci.scenario_helpers.vm_handler import VMHandler
from ci.scenario_helpers.ci_constants import CIConstants
from ovs.extensions.generic.logger import Logger
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.services.servicefactory import ServiceFactory
from ovs_extensions.generic.remote import remote


class AdvancedDTLTester(CIConstants):
    """
    Trigger HA with a VM via edge & KVM

    Required packages: qemu-kvm libvirt0 python-libvirt virtinst genisoimage
    Required commands after ovs installation and required packages: usermod -a -G ovs libvirt-qemu

    For this test the regular domain can only be 1 choice
    """

    CASE_TYPE = 'FUNCTIONAL'
    TEST_NAME = 'ci_scenario_advanced_dtl_test'
    LOGGER = Logger('scenario-{0}'.format(TEST_NAME))
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
        return AdvancedDTLTester.start_test()

    @classmethod
    def start_test(cls, vm_amount=1):
        """
        Run the entire test advanced_dtl_vdisk_test
        :param vm_amount: number of vms to use in the test
        :type vm_amount: int
        :return:
        """
        cluster_info, cloud_image_path, cloud_init_loc, is_ee = cls.setup()
        compute_ip = cluster_info['storagerouters']['compute'].ip

        source_storagedriver = cluster_info['storagedrivers']['source']
        protocol = source_storagedriver.cluster_node_config['network_server_uri'].split(':')[0]
        edge_details = {'port': source_storagedriver.ports['edge'], 'hostname': source_storagedriver.storage_ip,
                        'protocol': protocol}
        edge_user_info = {}
        if is_ee is True:
            edge_user_info = cls.get_shell_user()
            edge_details.update(edge_user_info)

        vm_handler = VMHandler(hypervisor_ip=compute_ip, amount_of_vms=vm_amount)

        vm_handler.prepare_vm_disks(source_storagedriver=source_storagedriver,
                                    cloud_image_path=cloud_image_path,
                                    cloud_init_loc=cloud_init_loc,
                                    vm_name=cls.VM_NAME,
                                    data_disk_size=cls.AMOUNT_TO_WRITE * 2,
                                    edge_user_info=edge_user_info)
        vm_info = vm_handler.create_vms(edge_configuration=edge_details,
                                        timeout=cls.VM_CREATION_TIMEOUT)
        try:
            cls.run_test(vm_info=vm_info, cluster_info=cluster_info)
        finally:
            vm_handler.destroy_vms(vm_info=vm_info)

    @classmethod
    def setup(cls, logger=LOGGER):
        """
        Set up the environment needed for the test
        :param logger: Logger instance
        :type logger: ovs.log.log_handler.LogHandler
        :return:
        """
        cluster_info = SetupHelper.setup_env(domainbased=True)

        to_be_downed_client = SSHClient(cluster_info['storagerouters']['source'], username='root')  # Build ssh clients

        # Get the cloud init file
        cloud_init_loc, is_ee = SetupHelper.setup_cloud_info(to_be_downed_client, cluster_info['storagedriver']['source'])
        image_path = SetupHelper.check_images(to_be_downed_client)

        return cluster_info, image_path, cloud_init_loc, is_ee

    @classmethod
    def run_test(cls, vm_info, cluster_info, logger=LOGGER):
        """
        Tests the DTL using a virtual machine which will write in his own filesystem
        Expects last data to be pulled from the DTL and not backend
        :param cluster_info: information about the cluster, contains all dal objects
        :type cluster_info: dict
        :param vm_info: info about the vms
        :param logger: logging instance
        :return: None
        :rtype: NoneType
        """
        source_std = cluster_info['storagedrivers']['source']
        source_client = SSHClient(source_std.storagerouter, username='root')

        compute_str = cluster_info['storagerouters']['compute']
        compute_client = SSHClient(compute_str)

        # setup hypervisor details
        parent_hypervisor = HypervisorFactory().get()
        vm_to_stop = cls.HYPERVISOR_INFO['vms'][source_std.storage_ip]['name']

        vdisk_info = {}
        disk_amount = 0
        for vm_name, vm_object in vm_info.iteritems():
            for vdisk in vm_object['vdisks']:
                # Ignore the cd vdisk as no IO will come from it
                if vdisk.name == vm_object['cd_path'].replace('.raw', '').split('/')[-1]:
                    continue
                disk_amount += 1
                vdisk_info.update({vdisk.name: vdisk})

        # Cache to validate properties
        values_to_check = {
            'source_std': source_std.serialize(),
            'vdisks': vdisk_info.values()
        }

        with remote(compute_str.ip, [SSHClient]) as rem:
            threads = {'evented': {'io': {'pairs': [], 'r_semaphore': None}}}
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

                logger.info("Stopping proxy services")
                service_manager = ServiceFactory.get_manager()

                for proxy in source_std.alba_proxies:
                    service_manager.restart_service(proxy.service.name, client=source_client)

                logger.info('Starting to WRITE file while proxy is offline. All data should be stored in the DTL!')
                for vm_name, vm_data in vm_info.iteritems():
                    vm_data['client'].run('dd if=/dev/urandom of={0} bs=1M count=2'.format(cls.VM_FILENAME).split())
                    original_md5sum = ' '.join(vm_data['client'].run(['md5sum', cls.VM_FILENAME]).split())
                    vm_data['original_md5sum'] = original_md5sum
                    logger.info('Original MD5SUM for VM {0}: {1}.'.format(vm_name, original_md5sum))
                logger.info('Finished to WRITE file while proxy is offline!')
                logger.info("Starting fio to generate IO for failing over.".format(cls.IO_TIME))
                io_thread_pairs, monitoring_data, io_r_semaphore = ThreadingHandler.start_io_polling_threads(volume_bundle=vdisk_info)
                threads['evented']['io']['pairs'] = io_thread_pairs
                threads['evented']['io']['r_semaphore'] = io_r_semaphore
                for vm_name, vm_data in vm_info.iteritems():  # Write data
                    screen_names, output_files = DataWriter.write_data_fio(client=vm_data['client'],
                                                                           fio_configuration={
                                                                               'io_size': cls.AMOUNT_TO_WRITE,
                                                                               'configuration': cls.IO_PATTERN},
                                                                           file_locations=['/mnt/data/{0}.raw'.format(vm_data['create_msg'])])
                    vm_data['screen_names'] = screen_names
                logger.info('Doing IO for {0}s before bringing down the node.'.format(cls.IO_TIME))
                ThreadingHandler.keep_threads_running(r_semaphore=io_r_semaphore,
                                                      threads=io_thread_pairs,
                                                      shared_resource=monitoring_data,
                                                      duration=cls.IO_TIME)
                ##############################################
                # Bringing original owner of the volume down #
                ##############################################
                VMHandler.stop_vm(hypervisor=parent_hypervisor, vmid=vm_to_stop)
                vm_downed = True
                downed_time = time.time()
                time.sleep(cls.IO_REFRESH_RATE * 2)
                # Start IO polling to verify nothing went down
                ThreadingHandler.poll_io(r_semaphore=io_r_semaphore,
                                         required_thread_amount=len(io_thread_pairs),
                                         shared_resource=monitoring_data,
                                         downed_time=downed_time,
                                         timeout=cls.HA_TIMEOUT,
                                         output_files=output_files,
                                         client=compute_client,
                                         disk_amount=disk_amount)
                logger.info('Starting to validate move...')
                cls._validate_move(values_to_check)
                logger.info('Finished to validate move!')

                logger.info('Validate if DTL is working correctly!')
                unmatching_checksum_vms = []
                for vm_name, vm_data in vm_info.iteritems():
                    current_md5sum = ' '.join(vm_data['client'].run(['md5sum', cls.VM_FILENAME]).split())
                    if vm_data['original_md5sum'] != current_md5sum:
                        unmatching_checksum_vms.append(vm_name)
                assert len(unmatching_checksum_vms) == 0, 'Not all data was read from the DTL. Checksums do not line up for {}'.format(', '.join(unmatching_checksum_vms))
                logger.info('DTL is working correctly!')
            finally:
                for thread_category, thread_collection in threads['evented'].iteritems():
                    ThreadHelper.stop_evented_threads(thread_collection['pairs'], thread_collection['r_semaphore'])
                if vm_downed is True:
                    VMHandler.start_vm(parent_hypervisor, vm_to_stop)
                    logger.debug('Started {0}'.format(vm_to_stop))
                    SystemHelper.idle_till_ovs_is_up(source_std.storage_ip, **cls.get_shell_user())
                    # @TODO: Remove when https://github.com/openvstorage/integrationtests/issues/540 is fixed
                    FwkHandler.restart_all()
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
        for vdisk in values_to_check['vdisks']:
            AdvancedDTLTester.LOGGER.info('Source is documented as {0} and vdisk is now on {1}'.format(source_std.storagerouter.guid, vdisk.storagerouter_guid))
            checks = 0
            while checks <= AdvancedDTLTester.MIGRATE_CHECKS:
                if vdisk.storagerouter_guid != source_std.storagerouter.guid:
                    AdvancedDTLTester.LOGGER.info('Move vdisk was successful according to the dal, source was {0} and destination is now {1}'
                                                  .format(source_std.storagerouter.guid, vdisk.storagerouter_guid))
                    return
                else:
                    AdvancedDTLTester.LOGGER.info('Move vdisk was NOT YET successful according to the dal, source was {0} and destination is now {1}, sleeping for {2} seconds'
                                                  .format(source_std.storagerouter.guid, vdisk.storagerouter_guid, AdvancedDTLTester.MIGRATE_TIMEOUT))
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
