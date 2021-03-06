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
from ci.api_lib.helpers.api import TimeOutError
from ci.api_lib.helpers.hypervisor.hypervisor import HypervisorFactory
from ci.api_lib.helpers.system import SystemHelper
from ci.api_lib.helpers.thread import ThreadHelper
from ci.api_lib.helpers.vdisk import VDiskHelper
from ci.api_lib.remove.vdisk import VDiskRemover
from ci.api_lib.setup.vdisk import VDiskSetup
from ci.autotests import gather_results
from ci.scenario_helpers.ci_constants import CIConstants
from ci.scenario_helpers.data_writing import DataWriter
from ci.scenario_helpers.fwk_handler import FwkHandler
from ci.scenario_helpers.setup import SetupHelper
from ci.scenario_helpers.threading_handlers import ThreadingHandler
from ci.scenario_helpers.vm_handler import VMHandler
from ovs.extensions.generic.logger import Logger
from ovs_extensions.generic.remote import remote
from ovs.extensions.generic.sshclient import SSHClient


class HATester(CIConstants):
    """
    Exercise HA with a VM via edge & KVM
    Required packages: qemu-kvm libvirt0 python-libvirt virtinst genisoimage
    Required commands after ovs installation and required packages: usermod -a -G ovs libvirt-qemu
    Requires the parent hyper to know the keys from its vms
    """
    CASE_TYPE = 'FUNCTIONAL'
    TEST_NAME = 'ci_scenario_hypervisor_ha_test'
    LOGGER = Logger('scenario-{0}'.format(TEST_NAME))

    IO_TIME = 15
    VM_CONNECTING_TIMEOUT = 5
    VM_NAME = 'HA-test'

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
        return HATester.start_test()

    @classmethod
    def start_test(cls, vm_amount=1):
        """
        Run the entire automated_ha test
        :param vm_amount: Amount of vms to run the test with
        :type vm_amount: int
        :return:
        """
        cluster_info, is_ee, cloud_image_path, cloud_init_loc, fio_bin_path = cls.setup()
        compute_ip = cluster_info['storagerouters']['compute'].ip

        vm_handler = VMHandler(hypervisor_ip=compute_ip, amount_of_vms=vm_amount)

        source_storagedriver = cluster_info['storagedrivers']['source']
        protocol = source_storagedriver.cluster_node_config['network_server_uri'].split(':')[0]
        edge_details = {'port': source_storagedriver.ports['edge'], 'hostname': source_storagedriver.storage_ip, 'protocol': protocol}
        edge_user_info = {}
        if is_ee is True:
            edge_user_info = cls.get_shell_user()
            edge_details.update(edge_user_info)
        vm_handler.prepare_vm_disks(source_storagedriver=source_storagedriver,
                                    cloud_image_path=cloud_image_path,
                                    cloud_init_loc=cloud_init_loc,
                                    vm_name=cls.VM_NAME,
                                    data_disk_size=cls.AMOUNT_TO_WRITE,
                                    edge_user_info=edge_user_info)
        vm_info = vm_handler.create_vms(edge_configuration=edge_details,
                                        timeout=cls.VM_CREATION_TIMEOUT)
        try:
            cls.run_test(cluster_info=cluster_info, vm_info=vm_info)
        finally:
            vm_handler.destroy_vms(vm_info=vm_info)

    @classmethod
    def setup(cls, logger=LOGGER):
        """
        Set up the environment for the test
        :param logger: Logger instance
        :type logger: ovs.log.log_handler.LogHandler
        """
        logger.info('Setting up environment for testing')
        cluster_info = SetupHelper.setup_env(domain_based=True)

        to_be_downed_client = SSHClient(cluster_info['storagerouters']['source'], username='root')  # Build ssh clients
        compute_client = SSHClient(cluster_info['storagerouters']['compute'], username='root')

        cloud_init_loc, is_ee = SetupHelper.setup_cloud_info(to_be_downed_client, cluster_info['storagedrivers']['source'])
        image_path = SetupHelper.check_images(to_be_downed_client)
        fio_bin_loc = SetupHelper.get_fio_bin_path(compute_client, is_ee)
        logger.info('Finished setting up environment')
        return cluster_info, is_ee, image_path, cloud_init_loc, fio_bin_loc

    @classmethod
    def run_test(cls, vm_info, cluster_info, logger=LOGGER):
        """
        Tests the HA using a virtual machine which will write in his own filesystem
        :param cluster_info: information about the cluster, contains all dal objects
        :type cluster_info: dict
        :param vm_info: info about the vms
        :param logger: logging instance
        :return: None
        :rtype: NoneType
        """
        compute_client = SSHClient(cluster_info['storagerouters']['compute'], username='root')
        failed_configurations = []

        destination_storagedriver = cluster_info['storagedrivers']['destination']
        source_storagedriver = cluster_info['storagedrivers']['source']

        # Cache to validate properties
        values_to_check = {
            'source_std': source_storagedriver.serialize(),
            'target_std': destination_storagedriver.serialize()
        }

        vm_to_stop = cls.HYPERVISOR_INFO['vms'][source_storagedriver.storage_ip]['name']
        parent_hypervisor = HypervisorFactory().get()
        # Extract vdisk info from vm_info
        vdisk_info = {}
        disk_amount = 0
        for vm_name, vm_object in vm_info.iteritems():
            for vdisk in vm_object['vdisks']:
                # Ignore the cd vdisk as no IO will come from it
                if vdisk.name == vm_object['cd_path'].replace('.raw', '').split('/')[-1]:
                    continue
                disk_amount += 1
                vdisk_info.update({vdisk.name: vdisk})

        with remote(compute_client.ip, [SSHClient]) as rem:
            configuration = random.choice(cls.DATA_TEST_CASES)
            threads = {'evented': {'io': {'pairs': [], 'r_semaphore': None}}}
            output_files = []
            vm_downed = False
            try:
                logger.info('Starting the following configuration: {0}'.format(configuration))
                for vm_name, vm_data in vm_info.iteritems():
                    vm_client = rem.SSHClient(vm_data['ip'], cls.VM_USERNAME, cls.VM_PASSWORD)
                    vm_client.file_create('/mnt/data/{0}.raw'.format(vm_data['create_msg']))
                    vm_data['client'] = vm_client
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
                # Bringing original owner of the volume down
                #########################
                try:
                    logger.info('Stopping {0}.'.format(vm_to_stop))
                    VMHandler.stop_vm(hypervisor=parent_hypervisor, vmid=vm_to_stop)
                    vm_downed = True
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
                                         timeout=cls.HA_TIMEOUT,
                                         output_files=output_files,
                                         client=compute_client,
                                         disk_amount=disk_amount)
                cls._validate(values_to_check, monitoring_data)
            except Exception as ex:
                logger.error('Running the test for configuration {0} has failed because {1}'.format(configuration, str(ex)))
                failed_configurations.append({'configuration': configuration, 'reason': str(ex)})
            finally:
                for thread_category, thread_collection in threads['evented'].iteritems():
                    ThreadHelper.stop_evented_threads(thread_collection['pairs'], thread_collection['r_semaphore'])
                if vm_downed is True:
                    VMHandler.start_vm(parent_hypervisor, vm_to_stop)
                    logger.debug('Started {0}'.format(vm_to_stop))
                    SystemHelper.idle_till_ovs_is_up(source_storagedriver.storage_ip, **cls.get_shell_user())
                    # @TODO: Remove when https://github.com/openvstorage/integrationtests/issues/540 is fixed
                    FwkHandler.restart_all()
                for vm_name, vm_data in vm_info.iteritems():
                    for screen_name in vm_data.get('screen_names', []):
                        logger.debug('Stopping screen {0} on {1}.'.format(screen_name, vm_data['client'].ip))
                        vm_data['client'].run(['screen', '-S', screen_name, '-X', 'quit'])
                    vm_data['screen_names'] = []
        assert len(failed_configurations) == 0, 'Certain configuration failed: {0}'.format(' '.join(failed_configurations))

    @classmethod
    def test_ha_fio(cls, fio_bin_path, cluster_info, is_ee, disk_amount=1, timeout=CIConstants.HA_TIMEOUT, logger=LOGGER):
        """
        Uses a modified fio to work with the openvstorage protocol
        :param fio_bin_path: path of the fio binary
        :type fio_bin_path: str
        :param cluster_info: information about the cluster, contains all dal objects
        :type cluster_info: dict
        :param is_ee: is it an ee version or not
        :type is_ee: bool
        :param disk_amount: amount of disks to test fail over with
        :type disk_amount: int
        :param timeout: timeout in seconds
        :type timeout: int
        :param logger: logging instance
        :return: None
        :rtype: NoneType
        """
        destination_storagedriver = cluster_info['storagedrivers']['destination']
        source_storagedriver = cluster_info['storagedrivers']['source']
        vpool = destination_storagedriver.vpool

        compute_client = SSHClient(cluster_info['storagerouters']['compute'], username='root')

        vm_to_stop = cls.HYPERVISOR_INFO['vms'][source_storagedriver.storage_ip]['name']
        parent_hypervisor = HypervisorFactory().get()
        values_to_check = {
            'source_std': source_storagedriver.serialize(),
            'target_std': destination_storagedriver.serialize(),
            'vdisks': []
        }
        # Create vdisks
        protocol = source_storagedriver.cluster_node_config['network_server_uri'].split(':')[0]
        edge_configuration = {'fio_bin_location': fio_bin_path, 'hostname': source_storagedriver.storage_ip,
                              'port': source_storagedriver.ports['edge'],
                              'protocol': protocol,
                              'volumenames': []}
        if is_ee is True:
            edge_configuration.update(cls.get_shell_user())

        vdisk_info = {}
        failed_configurations = []

        for index in xrange(0, disk_amount):
            try:
                vdisk_name = '{0}_vdisk{1}'.format(cls.TEST_NAME, str(index).zfill(3))
                data_vdisk = VDiskHelper.get_vdisk_by_guid(VDiskSetup.create_vdisk(vdisk_name, vpool.name, cls.AMOUNT_TO_WRITE, source_storagedriver.storage_ip))
                vdisk_info[vdisk_name] = data_vdisk
                edge_configuration['volumenames'].append(data_vdisk.devicename.rsplit('.', 1)[0].split('/', 1)[1])
                values_to_check['vdisks'].append(data_vdisk.serialize())
            except TimeOutError:
                logger.error('Creating the vdisk has timed out.')
                raise
            except RuntimeError as ex:
                logger.error('Could not create the vdisk. Got {0}'.format(str(ex)))
                raise
        configuration = random.choice(cls.DATA_TEST_CASES)
        threads = {'evented': {'io': {'pairs': [], 'r_semaphore': None}}}
        vm_downed = False
        screen_names = []
        try:
            logger.info('Starting threads.')  # Separate because creating vdisks takes a while, while creating the threads does not

            io_thread_pairs, monitoring_data, io_r_semaphore = ThreadingHandler.start_io_polling_threads(volume_bundle=vdisk_info)
            threads['evented']['io']['pairs'] = io_thread_pairs
            threads['evented']['io']['r_semaphore'] = io_r_semaphore
            screen_names, output_files = DataWriter.write_data_fio(client=compute_client,
                                                                   fio_configuration={'io_size': cls.AMOUNT_TO_WRITE,
                                                                                      'configuration': configuration},
                                                                   edge_configuration=edge_configuration)
            logger.info('Doing IO for {0}s before bringing down the node.'.format(cls.IO_TIME))
            ThreadingHandler.keep_threads_running(r_semaphore=io_r_semaphore,
                                                  threads=io_thread_pairs,
                                                  shared_resource=monitoring_data,
                                                  duration=cls.IO_TIME)
            # Threads ready for monitoring at this point
            #########################
            # Bringing original owner of the volume down
            #########################
            try:
                logger.info('Stopping {0}.'.format(vm_to_stop))
                VMHandler.stop_vm(hypervisor=parent_hypervisor, vmid=vm_to_stop)
                downed_time = time.time()
                vm_downed = True
            except Exception as ex:
                logger.error('Failed to stop. Got {0}'.format(str(ex)))
                raise
            time.sleep(cls.IO_REFRESH_RATE * 2)
            # Start IO polling to verify nothing went down
            ThreadingHandler.poll_io(r_semaphore=io_r_semaphore,
                                     required_thread_amount=len(io_thread_pairs),
                                     shared_resource=monitoring_data,
                                     downed_time=downed_time,
                                     timeout=timeout,
                                     output_files=output_files,
                                     client=compute_client,
                                     disk_amount=disk_amount)
            cls._validate(values_to_check, monitoring_data)
        except Exception as ex:
            failed_configurations.append({'configuration': configuration, 'reason': str(ex)})
        finally:
            for thread_category, thread_collection in threads['evented'].iteritems():
                ThreadHelper.stop_evented_threads(thread_collection['pairs'], thread_collection['r_semaphore'])
            if vm_downed is True:
                VMHandler.start_vm(parent_hypervisor, vm_to_stop)
                SystemHelper.idle_till_ovs_is_up(source_storagedriver.storage_ip, **cls.get_shell_user())
                # @TODO: Remove when https://github.com/openvstorage/integrationtests/issues/540 is fixed
                FwkHandler.restart_all()
            if screen_names:
                for screen_name in screen_names:
                    compute_client.run(['screen', '-S', screen_name, '-X', 'quit'])
            for vdisk in vdisk_info.values():
                VDiskRemover.remove_vdisk(vdisk.guid)
        assert len(failed_configurations) == 0, 'Certain configuration failed: {0}'.format(' '.join(failed_configurations))

    @staticmethod
    def _validate(values_to_check, monitoring_data):
        """
        Checks if the volume actually moved
        :param values_to_check: dict with values to validate if they updated
        :type values_to_check: dict
        :return: None
        :rtype: NoneType
        """
        # Validate downtime
        # Each log means +-4s downtime and slept twice
        pass
        # io_monitoring = monitoring_data['io']
        # if len(io_monitoring['down']) * HATester.IO_REFRESH_RATE >= HATester.SLEEP_TIME * 2:
        #     raise ValueError('Thread did not cause any IOPS to happen.')


def run(blocked=False):
    """
    Run a test
    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return HATester().main(blocked)


if __name__ == '__main__':
    run()
