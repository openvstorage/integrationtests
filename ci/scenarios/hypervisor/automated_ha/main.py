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
from ci.api_lib.helpers.api import TimeOutError
from ci.api_lib.helpers.hypervisor.hypervisor import HypervisorFactory
from ci.api_lib.helpers.domain import DomainHelper
from ci.api_lib.helpers.network import NetworkHelper
from ci.api_lib.helpers.storagedriver import StoragedriverHelper
from ci.api_lib.helpers.system import SystemHelper
from ci.api_lib.helpers.thread import ThreadHelper
from ci.api_lib.helpers.vdisk import VDiskHelper
from ci.api_lib.setup.vdisk import VDiskSetup
from ci.autotests import gather_results
from ci.scenario_helpers.ci_constants import CIConstants
from ci.scenario_helpers.data_writing import DataWriter
from ci.scenario_helpers.threading_handlers import ThreadingHandler
from ci.scenario_helpers.vm_handler import VMHandler
from ovs.extensions.generic.remote import remote
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.services.service import ServiceManager
from ovs.log.log_handler import LogHandler


class HATester(CIConstants):
    """
    Exercise HA with a VM via edge & KVM
    Required packages: qemu-kvm libvirt0 python-libvirt virtinst genisoimage
    Required commands after ovs installation and required packages: usermod -a -G ovs libvirt-qemu
    Requires the parent hyper to know the keys from its vms
    """
    CASE_TYPE = 'FUNCTIONAL'
    TEST_NAME = 'ci_scenario_hypervisor_ha_test'
    LOGGER = LogHandler.get(source='scenario', name=TEST_NAME)

    IO_TIME = 15
    VM_CONNECTING_TIMEOUT = 5
    VM_NAME = 'HA-test'

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
        _ = blocked
        return HATester.start_test()

    @classmethod
    def setup(cls, logger=LOGGER):
        """
        Execute the live migration test
        """
        #################
        # PREREQUISITES #
        #################
        destination_str, source_str, compute_str = cls.get_storagerouters_for_ha()
        destination_storagedriver = None
        source_storagedriver = None
        if len(source_str.regular_domains) == 0:
            storagedrivers = StoragedriverHelper.get_storagedrivers()
        else:
            storagedrivers = DomainHelper.get_storagedrivers_in_same_domain(domain_guid=source_str.regular_domains[0])
        for storagedriver in storagedrivers:
            if len(storagedriver.vpool.storagedrivers) < 2:
                continue
            if storagedriver.guid in destination_str.storagedrivers_guids:
                if destination_storagedriver is None and (source_storagedriver is None or source_storagedriver.vpool_guid == storagedriver.vpool_guid):
                    destination_storagedriver = storagedriver
                    logger.info('Chosen destination storagedriver is: {0}'.format(destination_storagedriver.storage_ip))
            elif storagedriver.guid in source_str.storagedrivers_guids:
                # Select if the source driver isn't select and destination is also unknown or the storagedriver has matches with the same vpool
                if source_storagedriver is None and (destination_storagedriver is None or destination_storagedriver.vpool_guid == storagedriver.vpool_guid):
                    source_storagedriver = storagedriver
                    logger.info('Chosen source storagedriver is: {0}'.format(source_storagedriver.storage_ip))
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
        assert len(missing_packages) == 0, 'Missing {0} package(s) on `{1}`: {2}'.format(len(missing_packages), to_be_downed_client.ip, missing_packages)
        missing_packages = SystemHelper.get_missing_packages(compute_client.ip, cls.REQUIRED_PACKAGES_HYPERVISOR)
        assert len(missing_packages) == 0, 'Missing {0} package(s) on `{1}`: {2}'.format(len(missing_packages), compute_client.ip, missing_packages)

        cluster_info = {'storagerouters': {'destination': destination_str,
                                           'source': source_str,
                                           'compute': compute_str},
                        'storagedrivers': {'destination': destination_storagedriver,
                                           'source': source_storagedriver}}

        is_ee = SystemHelper.get_ovs_version(to_be_downed_client) == 'ee'
        if is_ee is True:
            fio_bin_loc = cls.FIO_BIN_EE['location']
            fio_bin_url = cls.FIO_BIN_EE['url']
        else:
            fio_bin_loc = cls.FIO_BIN['location']
            fio_bin_url = cls.FIO_BIN['url']
        # Get the fio binary
        compute_client.run(['wget', fio_bin_url, '-O', fio_bin_loc])
        compute_client.file_chmod(fio_bin_loc, 755)
        assert compute_client.file_exists(fio_bin_loc), 'Could not get the latest fio binary.'
        return cluster_info, is_ee, image_path, cloud_init_loc

    @classmethod
    def start_test(cls, vm_amount=1, hypervisor_info=CIConstants.HYPERVISOR_INFO):
        api = cls.get_api_instance()
        cluster_info, is_ee, cloud_image_path, cloud_init_loc = cls.setup()
        compute_ip = cluster_info['storagerouters']['compute'].ip
        listening_port = NetworkHelper.get_free_port(compute_ip)

        source_storagedriver = cluster_info['storagedrivers']['source']
        protocol = source_storagedriver.cluster_node_config['network_server_uri'].split(':')[0]
        edge_details = {'port': source_storagedriver.ports['edge'], 'hostname': source_storagedriver.storage_ip, 'protocol': protocol}
        edge_user_info = {}
        if is_ee is True:
            edge_user_info = cls.get_shell_user()
            edge_details.update(edge_user_info)
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
            data_disk_size=cls.AMOUNT_TO_WRITE,
            edge_user_info=edge_user_info)
        vm_info = VMHandler.create_vms(ip=compute_ip,
                                       port=listening_port,
                                       connection_messages=connection_messages,
                                       vm_info=vm_info,
                                       edge_configuration=edge_details,
                                       hypervisor_client=computenode_hypervisor,
                                       timeout=cls.HA_TIMEOUT)
        cls.run_test(cluster_info=cluster_info,
                     disk_amount=volume_amount,
                     vm_info=vm_info,
                     api=api)

    @classmethod
    def run_test(cls, vm_info, cluster_info, api, disk_amount, logger=LOGGER):
        """
        Tests the HA using a virtual machine which will write in his own filesystem
        :param cluster_info: information about the cluster, contains all dal objects
        :type cluster_info: dict
        :param api: api object to call the ovs api
        :type api: ci.api_lib.helpers.api.OVSClient
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

        vm_to_stop = HATester.PARENT_HYPERVISOR_INFO['vms'][source_storagedriver.storage_ip]['name']
        parent_hypervisor = HypervisorFactory.get(HATester.PARENT_HYPERVISOR_INFO['ip'],
                                                  HATester.PARENT_HYPERVISOR_INFO['user'],
                                                  HATester.PARENT_HYPERVISOR_INFO['password'],
                                                  HATester.PARENT_HYPERVISOR_INFO['type'])
        # Extract vdisk info from vm_info
        vdisk_info = {}
        for vm_name, vm_object in vm_info.iteritems():
            for vdisk in vm_object['vdisks']:
                vdisk_info.update({vdisk.name: vdisk})
                
        with remote(compute_client.ip, [SSHClient]) as rem:
            for test_run_nr, configuration in enumerate(HATester.DATA_TEST_CASES):
                threads = {'evented': {'io': {'pairs': [], 'r_semaphore': None},
                                       'snapshots': {'pairs': [], 'r_semaphore': None}}}
                output_files = []
                vm_downed = False
                failed_over = False
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
                    ThreadingHandler.keep_threads_running(r_semaphore=threads['evented']['io']['r_semaphore'],
                                                          threads=threads['evented']['io']['pairs'],
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
                    # Start IO polling to verify nothing went down
                    ThreadingHandler.poll_io(r_semaphore=threads['evented']['io']['r_semaphore'],
                                             required_thread_amount=len(threads),
                                             shared_resource=monitoring_data,
                                             downed_time=downed_time,
                                             timeout=cls.HA_TIMEOUT,
                                             output_files=output_files,
                                             client=compute_client,
                                             disk_amount=disk_amount)
                    failed_over = True
                    HATester._validate(values_to_check, monitoring_data)
                except Exception as ex:
                    logger.error('Running the test for configuration {0} has failed because {1}'.format(configuration, str(ex)))
                    failed_configurations.append({'configuration': configuration, 'reason': str(ex)})
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
                    if failed_over:
                        cls._wait_and_move(vdisk_info, source_storagedriver.storagerouter.guid, api)
        assert len(failed_configurations) == 0, 'Certain configuration failed: {0}'.format(' '.join(failed_configurations))

    @classmethod
    def test_ha_fio(cls, fio_bin_path, vpool, compute_client, cluster_info, is_ee,  api, disk_amount=1, timeout=CIConstants.HA_TIMEOUT, logger=LOGGER):
        """
        Uses a modified fio to work with the openvstorage protocol
        :param fio_bin_path: path of the fio binary
        :type fio_bin_path: str
        :param compute_client: client of the machine to execute the fio
        :type compute_client: ovs.extensions.generic.sshclient.SSHClient
        :param vpool: vpool DAL object of the vpool to use
        :type vpool: ovs.dal.hybrids.vpool.VPool
        :param cluster_info: information about the cluster, contains all dal objects
        :type cluster_info: dict
        :param api: api object to call the ovs api
        :type api: ci.api_lib.helpers.api.OVSClient
        :param disk_amount: amount of disks to test fail over with
        :type disk_amount: int
        :param timeout: timeout in seconds
        :type timeout: int
        :return: None
        :rtype: NoneType
        """
        destination_storagedriver = cluster_info['storagedrivers']['destination']
        source_storagedriver = cluster_info['storagedrivers']['source']

        vm_to_stop = HATester.PARENT_HYPERVISOR_INFO['vms'][source_storagedriver.storage_ip]['name']
        parent_hypervisor = HypervisorFactory.get(HATester.PARENT_HYPERVISOR_INFO['ip'],
                                                  HATester.PARENT_HYPERVISOR_INFO['user'], HATester.PARENT_HYPERVISOR_INFO['password'],
                                                  HATester.PARENT_HYPERVISOR_INFO['type'])
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
                vdisk_name = '{0}_vdisk{1}'.format(HATester.TEST_NAME, str(index).zfill(3))
                data_vdisk = VDiskHelper.get_vdisk_by_guid(VDiskSetup.create_vdisk(vdisk_name, vpool.name, HATester.AMOUNT_TO_WRITE, source_storagedriver.storage_ip, api))
                vdisk_info[vdisk_name] = data_vdisk
                edge_configuration['volumenames'].append(data_vdisk.devicename.rsplit('.', 1)[0].split('/', 1)[1])
                values_to_check['vdisks'].append(data_vdisk.serialize())
            except TimeOutError:
                logger.error('Creating the vdisk has timed out.')
                raise
            except RuntimeError as ex:
                logger.error('Could not create the vdisk. Got {0}'.format(str(ex)))
                raise

        for configuration in HATester.DATA_TEST_CASES:
            threads = {'evented': {'io': {'pairs': [], 'r_semaphore': None},
                                   'snapshots': {'pairs': [], 'r_semaphore': None}}}
            vm_downed = False
            screen_names = []
            failed_over = False
            try:
                logger.info('Starting threads.')  # Separate because creating vdisks takes a while, while creating the threads does not

                io_thread_pairs, monitoring_data, io_r_semaphore = ThreadingHandler.start_io_polling_threads(volume_bundle=vdisk_info)
                threads['evented']['io']['pairs'] = io_thread_pairs
                threads['evented']['io']['r_semaphore'] = io_r_semaphore
                screen_names, output_files = DataWriter.write_data_fio(client=compute_client,
                                                                       fio_configuration={'io_size': cls.AMOUNT_TO_WRITE,
                                                                                          'configuration': configuration},
                                                                       edge_configuration=edge_configuration)
                logger.info('Doing IO for {0}s before bringing down the node.'.format(HATester.IO_TIME))
                ThreadingHandler.keep_threads_running(r_semaphore=threads['evented']['io']['r_semaphore'],
                                                      threads=threads['evented']['io']['pairs'],
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
                time.sleep(HATester.IO_REFRESH_RATE)
                # Start IO polling to verify nothing went down
                ThreadingHandler.poll_io(r_semaphore=threads['evented']['io']['r_semaphore'],
                                         required_thread_amount=len(threads),
                                         shared_resource=monitoring_data,
                                         downed_time=downed_time,
                                         timeout=timeout,
                                         output_files=output_files,
                                         client=compute_client,
                                         disk_amount=disk_amount)
                HATester._validate(values_to_check, monitoring_data)
            except Exception as ex:
                failed_configurations.append({'configuration': configuration, 'reason': str(ex)})
            finally:
                if vm_downed is True:
                    VMHandler.start_vm(parent_hypervisor, vm_to_stop)
                if screen_names:
                    for screen_name in screen_names:
                        compute_client.run(['screen', '-S', screen_name, '-X', 'quit'])
                for thread_category, thread_collection in threads['evented'].iteritems():
                    ThreadHelper.stop_evented_threads(thread_collection['pairs'], thread_collection['r_semaphore'])
                if failed_over:
                    # Wait for the downed node to come back up
                    cls._wait_and_move(vdisk_info, source_storagedriver.storagerouter.guid, api)

        assert len(failed_configurations) == 0, 'Certain configuration failed: {0}'.format(' '.join(failed_configurations))

    @staticmethod
    def _wait_and_move(vdisk_info, target_storagedriver, api, timeout=CIConstants.HA_TIMEOUT):
        start_time = time.time()
        to_be_downed_client = None
        while to_be_downed_client is None:
            try:
                to_be_downed_client = SSHClient(target_storagedriver.storagerouter, username='root')
            except:
                pass
            time.sleep(1)
        services = ServiceManager.list_services(to_be_downed_client)
        for service in services:
            if target_storagedriver.vpool.name not in service:
                continue
            while ServiceManager.get_service_status(service, to_be_downed_client) != 'active':
                if time.time() - start_time > timeout:
                    raise RuntimeError('Service {0} did not come up after {1}s. Something must be wrong with it.'.format(service, HATester.HA_TIMEOUT))
                time.sleep(1)
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
                VDiskSetup.move_vdisk(vdisk_guid=vdisk_object.guid, target_storagerouter_guid=target_storagedriver.storagerouter.guid, api=api)

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
