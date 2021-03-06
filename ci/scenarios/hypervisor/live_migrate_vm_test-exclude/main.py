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
import random
from ci.api_lib.helpers.hypervisor.hypervisor import HypervisorFactory, HypervisorCredentials
from ci.api_lib.helpers.storagedriver import StoragedriverHelper
from ci.api_lib.helpers.storagerouter import StoragerouterHelper
from ci.api_lib.helpers.thread import ThreadHelper
from ci.api_lib.helpers.vdisk import VDiskHelper
from ci.autotests import gather_results
from ci.scenario_helpers.ci_constants import CIConstants
from ci.scenario_helpers.data_writing import DataWriter
from ci.scenario_helpers.setup import SetupHelper
from ci.scenario_helpers.threading_handlers import ThreadingHandler
from ci.scenario_helpers.vm_handler import VMHandler
from ovs.extensions.generic.logger import Logger
from ovs_extensions.generic.remote import remote
from ovs.extensions.generic.sshclient import SSHClient


class MigrateTester(CIConstants):
    """
    Migrate a VM via edge & KVM

    Required packages: qemu-kvm libvirt0 python-libvirt virtinst genisoimage
    Required commands after ovs installation and required packages: usermod -a -G ovs libvirt-qemu
    """
    CASE_TYPE = 'FUNCTIONAL'
    TEST_NAME = "ci_scenario_hypervisor_live_migrate"
    LOGGER = Logger('scenario-{0}'.format(TEST_NAME))
    SLEEP_TIME = 60
    VM_CONNECTING_TIMEOUT = 5
    REQUIRED_PACKAGES = ["qemu-kvm", "libvirt0", "python-libvirt", "virtinst", "genisoimage"]
    # read write patterns to test (read, write)
    VM_NAME = 'migrate-test'
    IO_TIME = 30  # Seconds to do IO
    VM_CREATE_TIMEOUT = 300
    FAILOVER_TIMEOUT = 300  # Amount of seconds to wait before raising an error after the migration started

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
        return MigrateTester.start_test()

    @classmethod
    def start_test(cls, hypervisor_info=CIConstants.HYPERVISOR_INFO):
        """
        Run the entire test live_migrate_vm_test
        :param hypervisor_info: Information needed regarding the hypervisor
        :type hypervisor_info: dict
        :return:
        """
        cluster_info, cloud_init_loc, cloud_image_path, is_ee = cls.setup()
        source_storagedriver = cluster_info['storagedrivers']['source']

        protocol = source_storagedriver.cluster_node_config['network_server_uri'].split(':')[0]
        edge_details = {'port': source_storagedriver.ports['edge'], 'hostname': source_storagedriver.storage_ip,
                        'protocol': protocol}
        edge_user_info = {}
        if is_ee is True:
            edge_user_info = cls.get_shell_user()
            edge_details.update(edge_user_info)
        vm_handler = VMHandler(hypervisor_ip=source_storagedriver.storage_ip)
        vm_handler.prepare_vm_disks(source_storagedriver=source_storagedriver,
                                    cloud_image_path=cloud_image_path,
                                    cloud_init_loc=cloud_init_loc,
                                    vm_name=cls.VM_NAME,
                                    data_disk_size=cls.AMOUNT_TO_WRITE,
                                    edge_user_info=edge_user_info)
        vm_info = vm_handler.create_vms(edge_configuration=edge_details,
                                        timeout=cls.VM_CREATION_TIMEOUT)
        try:
            cls.live_migrate(vm_info, cluster_info, vm_handler.volume_amount, hypervisor_info)
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
        logger.info('Setting up environment for testing')
        cluster_info = SetupHelper.setup_env()
        to_be_downed_client = SSHClient(cluster_info['storagerouters']['source'], username='root')  # Build ssh clients

        cloud_init_loc, is_ee = SetupHelper.setup_cloud_info(to_be_downed_client, cluster_info['storagedrivers']['source'])
        image_path = SetupHelper.check_images(to_be_downed_client)
        logger.info('Finished setting up environment')
        return cluster_info, cloud_init_loc, image_path, is_ee

    @classmethod
    def live_migrate(cls, vm_info, cluster_info, disk_amount, hypervisor_info, logger=LOGGER):
        """
        Execute the live migration test
        Migrates the vm away using libvirt migrate call
        Expects the DAL to be updated due to the IO causing volumedriver to move the volume
        """
        failed_configurations = []

        destination_storagedriver = cluster_info['storagedrivers']['destination']
        source_storagedriver = cluster_info['storagedrivers']['source']

        hv_credentials = HypervisorCredentials(ip=source_storagedriver.storage_ip,
                                               user=hypervisor_info['user'],
                                               password=hypervisor_info['password'],
                                               type=hypervisor_info['type'])
        source_hypervisor = HypervisorFactory().get(hv_credentials=hv_credentials)
        client = SSHClient(source_storagedriver.storagerouter)
        # Cache to validate properties
        values_to_check = {
            'source_std': source_storagedriver.serialize(),
            'target_std': destination_storagedriver.serialize()
        }

        # Extract vdisk info from vm_info
        vdisk_info = {}
        for vm_name, vm_object in vm_info.iteritems():
            for vdisk in vm_object['vdisks']:
                vdisk_info.update({vdisk.name: vdisk})

        with remote(source_storagedriver.storage_ip, [SSHClient]) as rem:
            test_run_nr = 0
            configuration = random.choice(cls.DATA_TEST_CASES)
            threads = {'evented': {'io': {'pairs': [], 'r_semaphore': None}}}
            output_files = []
            try:
                logger.info('Starting the following configuration: {0}'.format(configuration))
                if test_run_nr == 0:  # Build reusable ssh clients
                    for vm_name, vm_data in vm_info.iteritems():
                        vm_client = rem.SSHClient(vm_data['ip'], cls.VM_USERNAME, cls.VM_PASSWORD)
                        vm_client.file_create('/mnt/data/{0}.raw'.format(vm_data['create_msg']))
                        vm_data['client'] = vm_client
                else:
                    for vm_name, vm_data in vm_info.iteritems():
                        vm_data['client'].run(['rm', '/mnt/data/{0}.raw'.format(vm_data['create_msg'])])
                io_thread_pairs, monitoring_data, io_r_semaphore = ThreadingHandler.start_io_polling_threads(volume_bundle=vdisk_info)
                threads['evented']['io']['pairs'] = io_thread_pairs
                threads['evented']['io']['r_semaphore'] = io_r_semaphore
                for vm_name, vm_data in vm_info.iteritems():  # Write data
                    screen_names, output_files = DataWriter.write_data_fio(client=vm_data['client'],
                                                                           fio_configuration={
                                                                               'io_size': cls.AMOUNT_TO_WRITE,
                                                                               'configuration': configuration},
                                                                           file_locations=['/mnt/data/{0}.raw'.format(vm_data['create_msg'])])
                    vm_data['screen_names'] = screen_names
                logger.info('Doing IO for {0}s before bringing down the node.'.format(cls.IO_TIME))
                ThreadingHandler.keep_threads_running(r_semaphore=io_r_semaphore,
                                                      threads=io_thread_pairs,
                                                      shared_resource=monitoring_data,
                                                      duration=cls.IO_TIME)
                # Threads ready for monitoring at this point
                #########################
                # Migrate the VMs
                #########################
                try:
                    logger.info('Migrating the VM.')
                    for vm_name in vm_info:
                        source_hypervisor.sdk.migrate(vm_name, destination_storagedriver.storage_ip, hypervisor_info['user'])
                except Exception as ex:
                    logger.error('Failed to stop. Got {0}'.format(str(ex)))
                    raise
                downed_time = time.time()
                time.sleep(cls.IO_REFRESH_RATE * 2)
                # Start IO polling to verify nothing went down
                ThreadingHandler.poll_io(r_semaphore=io_r_semaphore,
                                         required_thread_amount=len(io_thread_pairs),
                                         shared_resource=monitoring_data,
                                         downed_time=downed_time,
                                         timeout=cls.FAILOVER_TIMEOUT,
                                         output_files=output_files,
                                         client=client,
                                         disk_amount=disk_amount)
                # Do some more IO to trigger ownership migration
                ThreadingHandler.keep_threads_running(r_semaphore=io_r_semaphore,
                                                      threads=io_thread_pairs,
                                                      shared_resource=monitoring_data,
                                                      duration=cls.IO_TIME)
                cls._validate_move(values_to_check)
            except Exception as ex:
                logger.error('Running the test for configuration {0} has failed because {1}'.format(configuration, str(ex)))
                failed_configurations.append({'configuration': configuration, 'reason': str(ex)})
            finally:
                for thread_category, thread_collection in threads['evented'].iteritems():
                    ThreadHelper.stop_evented_threads(thread_collection['pairs'], thread_collection['r_semaphore'])
                for vm_name, vm_data in vm_info.iteritems():
                    for screen_name in vm_data.get('screen_names', []):
                        logger.debug('Stopping screen {0} on {1}.'.format(screen_name, vm_data['client'].ip))
                        vm_data['client'].run(['screen', '-S', screen_name, '-X', 'quit'])
                    vm_data['screen_names'] = []

    @staticmethod
    def migrate(hypervisor, d_ip, d_login, vmid):
        """
        Migrates a VM between hypervisors
        :param hypervisor: hypervisor instance
        :param d_ip: destination ip
        :param d_login: destination loign
        :param vmid: vm identifier
        :return:
        """
        # Migrate VM
        hypervisor.sdk.migrate(vmid, d_ip, d_login)

    @staticmethod
    def _validate_move(values_to_check):
        """
        Validates the move test. Checks IO, and checks for dal changes
        :param values_to_check: dict with values to validate if they updated
        :type values_to_check: dict
        :return:
        """
        # Fetch dal object
        source_std = StoragedriverHelper.get_storagedriver_by_guid(values_to_check['source_std']['guid'])
        target_std = StoragedriverHelper.get_storagedriver_by_guid(values_to_check['target_std']['guid'])
        try:
            MigrateTester._validate_dal(values_to_check)
        except ValueError as ex:
            MigrateTester.LOGGER.warning('DAL did not automatically change after a move. Got {0}'.format(ex))
            source_std.invalidate_dynamics([])
            target_std.invalidate_dynamics([])
            # Properties should have been reloaded
            values_to_check['source_std'] = StoragedriverHelper.get_storagedriver_by_guid(values_to_check['source_std']['guid']).serialize()
            values_to_check['target_std'] = StoragedriverHelper.get_storagedriver_by_guid(values_to_check['target_std']['guid']).serialize()
            MigrateTester._validate_dal(values_to_check)

    @staticmethod
    def _validate_dal(values):
        """
        Validates the move test. Checks for dal changes
        :param values: dict with values to validate if they updated
        :type values: dict
        :return:
        """
        # Fetch them from the dal
        source_std = StoragedriverHelper.get_storagedriver_by_guid(values['source_std']['guid'])
        target_std = StoragedriverHelper.get_storagedriver_by_guid(values['target_std']['guid'])
        vdisk = VDiskHelper.get_vdisk_by_guid(values['vdisk']['guid'])
        if values['source_std'] == source_std.serialize():
            # DAL values did not update - expecting a change in vdisks_guids
            raise ValueError('Expecting the target Storagedriver to change but nothing happened...')
        else:
            # Expecting changes in vdisks_guids
            if vdisk.guid in source_std.vdisks_guids:
                raise ValueError('Vdisks guids were not updated after move for source storagedriver.')
            else:
                MigrateTester.LOGGER.info('All properties are updated for source storagedriver.')
        if values['target_std'] == target_std.serialize():
            raise ValueError('Expecting changes in the target Storagedriver but nothing changed.')
        else:
            if vdisk.guid not in target_std.vdisks_guids:
                raise ValueError('Vdisks guids were not updated after move for target storagedriver.')
            else:
                MigrateTester.LOGGER.info('All properties are updated for target storagedriver.')
        if values["vdisk"] == vdisk.serialize():
            raise ValueError('Expecting changes in the vdisk but nothing changed.')
        else:
            if vdisk.storagerouter_guid == target_std.storagerouter.guid:
                MigrateTester.LOGGER.info('All properties are updated for vdisk.')
            else:
                ValueError('Expected {0} but found {1} for vdisk.storagerouter_guid'.format(vdisk.storagerouter_guid, vdisk.storagerouter_guid))
        MigrateTester.LOGGER.info('Move vdisk was successful according to the dal (which fetches volumedriver info).')


def run(blocked=False):
    """
    Run a test

    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """

    return MigrateTester().main(blocked)


if __name__ == "__main__":
    run()
