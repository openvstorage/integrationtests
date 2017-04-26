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
import json
import math
import Queue
import socket
import subprocess
import time
import threading
import uuid
from datetime import datetime
from ci.api_lib.helpers.api import OVSClient
from ci.api_lib.helpers.exceptions import VDiskNotFoundError
from ci.api_lib.helpers.hypervisor.hypervisor import HypervisorFactory
from ci.api_lib.helpers.vpool import VPoolHelper
from ci.api_lib.helpers.vdisk import VDiskHelper
from ci.api_lib.helpers.storagerouter import StoragerouterHelper
from ci.api_lib.helpers.system import SystemHelper
from ci.api_lib.helpers.thread import ThreadHelper, Waiter
from ci.autotests import gather_results
from ci.main import CONFIG_LOC
from ci.main import SETTINGS_LOC
from ci.api_lib.helpers.api import TimeOutError
from ci.api_lib.setup.vdisk import VDiskSetup
from ci.api_lib.remove.vdisk import VDiskRemover
from ovs.extensions.generic.remote import remote
from ovs.extensions.services.service import ServiceManager
from ovs.extensions.generic.sshclient import SSHClient
from ovs.log.log_handler import LogHandler


class HATester(object):
    """
    Exercise HA with a VM via edge & KVM
    Required packages: qemu-kvm libvirt0 python-libvirt virtinst genisoimage
    Required commands after ovs installation and required packages: usermod -a -G ovs libvirt-qemu
    Requires the parent hyper to know the keys from its vms
    """
    CASE_TYPE = 'FUNCTIONAL'
    TEST_NAME = 'ci_scenario_hypervisor_ha_test'
    LOGGER = LogHandler.get(source='scenario', name=TEST_NAME)

    SLEEP_TIME = 15
    HA_TIMEOUT = 300
    VM_CONNECTING_TIMEOUT = 5
    REQUIRED_PACKAGES_HYPERVISOR = ['qemu-kvm', 'libvirt0', 'python-libvirt', 'virtinst']
    REQUIRED_PACKAGE_CLOUD_INIT = ['genisoimage']
    DATA_TEST_CASES = [(0, 100), (30, 70), (40, 60), (50, 50), (70, 30), (100, 0)]  # read write patterns to test (read, write)

    VM_NAME = 'HA-test'
    VM_OS_TYPE = 'ubuntu16.04'
    VM_WAIT_TIME = 300  # wait time before timing out on the vm install in seconds
    CLOUD_INIT_DATA = {
        'script_loc': 'https://raw.githubusercontent.com/kinvaris/cloud-init/master/create-config-drive',
        'script_dest': '/tmp/cloud_init_script.sh',
        'user-data_loc': '/tmp/user-data-migrate-test',
        'config_dest': '/tmp/cloud-init-config-migrate-test'
    }
    FIO_BIN = {'url': 'http://www.include.gr/fio.bin.latest', 'location': '/tmp/fio.bin.latest'}
    AMOUNT_TO_WRITE = 10 * 1024 ** 3
    with open(CONFIG_LOC, 'r') as JSON_CONFIG:
        SETUP_CFG = json.load(JSON_CONFIG)

    # collect details about parent hypervisor
    PARENT_HYPERVISOR_INFO = SETUP_CFG['ci']['hypervisor']

    VDISK_THREAD_LIMIT = 5  # Each monitor thread queries x amount of vdisks
    FIO_VDISK_LIMIT = 50  # Each fio uses x disks

    VM_USERNAME = 'root'  # vm credentials & details
    VM_PASSWORD = 'rooter'
    VM_VCPUS = 4
    VM_VRAM = 1024  # In MB

    IO_REFRESH_RATE = 5  # in seconds

    # hypervisor details
    HYPERVISOR_TYPE = PARENT_HYPERVISOR_INFO['type']
    HYPERVISOR_USER = SETUP_CFG['ci']['user']['shell']['username']
    HYPERVISOR_PASSWORD = SETUP_CFG['ci']['user']['shell']['password']

    def __init__(self):
        pass

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
        return HATester._execute_test()

    @staticmethod
    def _execute_test():
        """
        Execute the live migration test
        """

        HATester.LOGGER.info('Starting Edge HA autotests test!')

        #################
        # PREREQUISITES #
        #################

        str_1 = None  # Will act as volumedriver node
        str_2 = None  # Will act as volumedriver node
        str_3 = None  # Will act as compute node

        for node_ip, node_details in HATester.PARENT_HYPERVISOR_INFO['vms'].iteritems():
            if node_details['role'] == "VOLDRV":
                if str_1 is None:
                    str_1 = StoragerouterHelper.get_storagerouter_by_ip(node_ip)
                    HATester.LOGGER.info('Node with IP `{0}` has been selected as VOLDRV node (str_1)'.format(node_ip))
                elif str_2 is None:
                    str_2 = StoragerouterHelper.get_storagerouter_by_ip(node_ip)
                    HATester.LOGGER.info('Node with IP `{0}` has been selected as VOLDRV node (str_2)'.format(node_ip))
            elif node_details['role'] == "COMPUTE" and str_3 is None:
                str_3 = StoragerouterHelper.get_storagerouter_by_ip(node_ip)
                HATester.LOGGER.info('Node with IP `{0}` has been selected as COMPUTE node (str_3)'.format(node_ip))
            else:
                HATester.LOGGER.info('Node with IP `{0}` is not required or has a invalid role: {1}'.format(node_ip, node_details['role']))

        with open(CONFIG_LOC, 'r') as config_file:
            config = json.load(config_file)
        api = OVSClient(
            config['ci']['grid_ip'],
            config['ci']['user']['api']['username'],
            config['ci']['user']['api']['password']
        )
        with open(SETTINGS_LOC, 'r') as JSON_SETTINGS:
            settings = json.load(JSON_SETTINGS)
        # Get a suitable vpool with min. 2 storagedrivers
        vpool = None
        for vp in VPoolHelper.get_vpools():
            if len(vp.storagedrivers) >= 2 and vp.configuration['dtl_mode'] == 'sync':
                vpool = vp
                break
        assert vpool is not None, 'Not enough vPools to test. We need at least a vPool with 2 storagedrivers'

        # Choose source & destination storage driver
        std_1 = [storagedriver for storagedriver in str_1.storagedrivers if storagedriver.vpool_guid == vpool.guid][0]
        std_2 = [storagedriver for storagedriver in str_2.storagedrivers if storagedriver.vpool_guid == vpool.guid][0]
        HATester.LOGGER.info('Chosen source storagedriver is: {0}'.format(std_1.storage_ip))
        HATester.LOGGER.info('Chosen destination storagedriver is: {0}'.format(std_2.storage_ip))

        # build ssh clients
        to_be_downed_client = SSHClient(str_2, username='root')
        compute_client = SSHClient(str_3, username='root')

        # check if enough images available
        images = settings['images']
        assert len(images) >= 1, 'Not enough images in `{0}`'.format(SETTINGS_LOC)

        # check if image exists
        image_path = images[0]
        assert to_be_downed_client.file_exists(image_path), 'Image `{0}` does not exists on `{1}`!'.format(images[0], to_be_downed_client.ip)

        # Get the cloud init file
        cloud_init_loc = HATester.CLOUD_INIT_DATA.get('script_dest')
        to_be_downed_client.run(['wget', HATester.CLOUD_INIT_DATA.get('script_loc'), '-O', cloud_init_loc])
        to_be_downed_client.file_chmod(cloud_init_loc, 755)
        assert to_be_downed_client.file_exists(cloud_init_loc), 'Could not fetch the cloud init script'
        missing_packages = SystemHelper.get_missing_packages(to_be_downed_client.ip, HATester.REQUIRED_PACKAGE_CLOUD_INIT)
        assert len(missing_packages) == 0, 'Missing {0} package(s) on `{1}`: {2}'.format(len(missing_packages), to_be_downed_client.ip, missing_packages)
        # Get the fio binary
        compute_client.run(['wget', HATester.FIO_BIN['url'], '-O', HATester.FIO_BIN['location']])
        compute_client.file_chmod(HATester.FIO_BIN['location'], 755)
        assert compute_client.file_exists(HATester.FIO_BIN['location']), 'Could not get the latest fio binary.'
        missing_packages = SystemHelper.get_missing_packages(compute_client.ip, HATester.REQUIRED_PACKAGES_HYPERVISOR)
        assert len(missing_packages) == 0, 'Missing {0} package(s) on `{1}`: {2}'.format(len(missing_packages), compute_client.ip, missing_packages)

        cluster_info = {'storagerouters': {'str1': str_1, 'str2': str_2, 'str3': str_3}, 'storagedrivers': {'std1': std_1, 'std2': std_2}}

        HATester.test_ha_vm(to_be_downed_client, image_path, vpool, cloud_init_loc, cluster_info, api)
        # try:
        #     HATester.test_ha_fio(HATester.FIO_BIN['location'], vpool, compute_client, cluster_info, api)
        # except Exception:
        #     compute_client.file_delete(HATester.FIO_BIN['location'])
        #     raise

    @staticmethod
    def test_ha_vm(to_be_downed_client, image_path, vpool, cloud_init_loc, cluster_info, api, vm_amount=1, timeout=HA_TIMEOUT):
        """
        Tests the HA using a virtual machine which will write in his own filesystem
        :param to_be_downed_client: sshclient of the storagerouter that will go down in this test
        :type to_be_downed_client: ovs.extensions.generic.sshclient.SSHClient
        :param image_path: path of the cloud init image
        :type image_path: str
        :param vpool: vpool DAL object of the vpool to use
        :type vpool: ovs.dal.hybrids.vpool.VPool
        :param cloud_init_loc: location of the cloud init boot file
        :type cloud_init_loc: str
        :param cluster_info: information about the cluster, contains all dal objects
        :type cluster_info: dict
        :param api: api object to call the ovs api
        :type api: ci.api_lib.helpers.api.OVSClient
        :param vm_amount: amount of vms to deploy
        :type vm_amount: int
        :param timeout: timeout in seconds
        :type timeout: int
        :return: None
        :rtype: NoneType
        """
        logger = HATester.LOGGER
        
        str_2 = cluster_info['storagerouters']['str2']
        str_3 = cluster_info['storagerouters']['str3']
        std_1 = cluster_info['storagedrivers']['std1']
        std_2 = cluster_info['storagedrivers']['std2']

        vm_to_stop = HATester.PARENT_HYPERVISOR_INFO['vms'][str_2.ip]['name']
        parent_hypervisor = HypervisorFactory.get(HATester.PARENT_HYPERVISOR_INFO['ip'],
                                                  HATester.PARENT_HYPERVISOR_INFO['user'],
                                                  HATester.PARENT_HYPERVISOR_INFO['password'],
                                                  HATester.PARENT_HYPERVISOR_INFO['type'])
        computenode_hypervisor = HypervisorFactory.get(str_3.ip, HATester.HYPERVISOR_USER, HATester.HYPERVISOR_PASSWORD, HATester.HYPERVISOR_TYPE)
        # Cache to validate properties
        values_to_check = {
            'source_std': std_1.serialize(),
            'target_std': std_2.serialize()
        }
        # Create a new vdisk to test
        original_boot_disk_name = None  # Cloning purposes
        original_data_disk_name = None  # Cloning purposes
        protocol = std_2.cluster_node_config['network_server_uri'].split(':')[0]
        edge_details = {'port': std_2.ports['edge'], 'hostname': std_2.storage_ip, 'protocol': protocol}

        # Milestones through the code
        vm_info = {}

        failed_configurations = []
        volume_amount = 0
        # Prep VM listener #
        listening_port = HATester._get_free_port(str_3.ip)
        connection_messages = []
        for vm_number in xrange(0, vm_amount):
            filled_number = str(vm_number).zfill(3)
            create_msg = '{0}_{1}'.format(str(uuid.uuid4()), filled_number)
            vm_name = '{0}_{1}'.format(HATester.VM_NAME, filled_number)
            boot_vdisk_name = '{0}_vdisk_boot_{1}'.format(HATester.TEST_NAME, filled_number)
            data_vdisk_name = '{0}_vdisk_data_{1}'.format(HATester.TEST_NAME, filled_number)
            cd_vdisk_name = '{0}_vdisk_cd_{1}'.format(HATester.TEST_NAME, filled_number)
            boot_vdisk_path = '/mnt/{0}/{1}.raw'.format(vpool.name, boot_vdisk_name)
            data_vdisk_path = '/mnt/{0}/{1}.raw'.format(vpool.name, data_vdisk_name)
            cd_vdisk_path = '/mnt/{0}/{1}.raw'.format(vpool.name, cd_vdisk_name)
            if vm_number == 0:
                try:
                    # Create VDISKs
                    ovs_path = 'openvstorage+{0}:{1}:{2}/{3}'.format(protocol, std_2.storage_ip, std_2.ports['edge'], boot_vdisk_name)
                    logger.info('Copying the image to the vdisk with command `qemu-img convert {0}`'.format(ovs_path))
                    to_be_downed_client.run(['qemu-img', 'convert', image_path, ovs_path])
                except RuntimeError as ex:
                    logger.error('Could not covert the image. Got {0}'.format(str(ex)))
                    raise
                boot_vdisk = VDiskHelper.get_vdisk_by_name('{0}.raw'.format(boot_vdisk_name), vpool.name)
                original_boot_disk_name = boot_vdisk_name
                logger.info('Boot VDisk successfully created.')
                try:
                    data_vdisk = VDiskHelper.get_vdisk_by_guid(VDiskSetup.create_vdisk(data_vdisk_name, vpool.name, HATester.AMOUNT_TO_WRITE, std_2.storage_ip, api))
                    logger.info('VDisk data_vdisk successfully created!')
                except TimeOutError:
                    logger.error('The creation of the data vdisk has timed out.')
                    raise
                except RuntimeError as ex:
                    logger.error('Could not create the data vdisk. Got {0}'.format(str(ex)))
                    raise
                original_data_disk_name = data_vdisk_name
            else:
                # Rely on cloning to speed up the process
                boot_vdisk_info = VDiskSetup.create_clone(vdisk_name=original_boot_disk_name, vpool_name=vpool.name, new_vdisk_name=boot_vdisk_name, storagerouter_ip=std_2.storage_ip, api=api)
                boot_vdisk = VDiskHelper.get_vdisk_by_guid(boot_vdisk_info['vdisk_guid'])
                data_vdisk_info = VDiskSetup.create_clone(vdisk_name=original_data_disk_name, vpool_name=vpool.name, new_vdisk_name=data_vdisk_name, storagerouter_ip=std_2.storage_ip, api=api)
                data_vdisk = VDiskHelper.get_vdisk_by_guid(data_vdisk_info['vdisk_guid'])
            #######################
            # GENERATE CLOUD INIT #
            #######################
            iso_loc = HATester._generate_cloud_init(client=to_be_downed_client, convert_script_loc=cloud_init_loc, port=listening_port, hypervisor_ip=str_3.ip, create_msg=create_msg)
            to_be_downed_client.run(['qemu-img', 'convert', iso_loc, 'openvstorage+{0}:{1}:{2}/{3}'.format(protocol, std_2.storage_ip, std_2.ports['edge'], cd_vdisk_name)])
            cd_creation_time = time.time()
            cd_vdisk = None
            while cd_vdisk is None:
                try:
                    cd_vdisk = VDiskHelper.get_vdisk_by_name(cd_vdisk_name, vpool.name)
                except VDiskNotFoundError:
                    logger.warning('Could not fetch the cd vdisk after {0}s.'.format(time.time() - cd_creation_time))
                time.sleep(0.5)

            # Take snapshot to revert back to after every migrate scenario
            data_snapshot_guid = VDiskSetup.create_snapshot('{0}_data'.format(HATester.TEST_NAME), data_vdisk.devicename, vpool.name, api, consistent=False)
            vm_info[vm_name] = {'data_snapshot_guid': data_snapshot_guid,
                                'vdisks': [boot_vdisk, data_vdisk, cd_vdisk],
                                'cd_path': cd_vdisk_path,
                                'disks': [{'mountpoint': boot_vdisk_path}, {'mountpoint': data_vdisk_path}],
                                'networks': [{'network': 'default', 'mac': 'RANDOM', 'model': 'e1000'}],
                                'created': False,
                                'ip': '',
                                'create_msg': create_msg}
            connection_messages.append(create_msg)
            volume_amount += len(vm_info[vm_name]['vdisks'])
            logger.info('Prepped everything for VM {0}.'.format(vm_name))
        ##############
        # Create VMS #
        ##############
        listening_queue = Queue.Queue()
        listening_thread, listening_stop_object = ThreadHelper.start_thread_with_event(HATester._listen_to_address, 'vm_listener', args=(str_3.ip, listening_port, listening_queue, connection_messages, timeout))
        for vm_name, vm_data in vm_info.iteritems():
            # offload to a thread
            HATester._create_vm(vm_name=vm_name, hypervisor_ip=str_3.ip, disks=vm_data['disks'],
                                networks=vm_data['networks'], edge_details=edge_details, cd_path=vm_data['cd_path'])
        listening_thread.join()  # Wait for all to finish
        vm_ip_info = listening_queue.get()
        for vm_name, vm_data in vm_info.iteritems():
            vm_data.update(vm_ip_info[vm_name])
        assert len(vm_ip_info.keys()) == len(vm_info.keys()), 'Not all VMs started.'
        # Remove cd
        # for vm_name in vm_info.keys():
        #     computenode_hypervisor.sdk.eject_cd(vm_name)
        ##############
        # START TEST #
        ##############
        with remote(str_3.ip, [SSHClient]) as rem:
            for test_run_nr, configuration in enumerate(HATester.DATA_TEST_CASES):
                vm_downed = False
                failed_over = False
                r_semaphore = None
                threads = []
                try:
                    logger.info('Starting the following configuration: {0}'.format(configuration))
                    if test_run_nr == 0:  # Build reusable ssh clients
                        for vm_name, vm_data in vm_info.iteritems():
                            vm_client = rem.SSHClient(vm_data['ip'], HATester.VM_USERNAME, HATester.VM_PASSWORD)
                            vm_client.file_create('/mnt/data/{0}.raw'.format(vm_data['create_msg']))
                            vm_data['client'] = vm_client
                    # else:
                    #     for vm_name, vm_data in vm_info.iteritems():
                    #         computenode_hypervisor.sdk.destroy(vm_name)
                    #         VDiskSetup.rollback_to_snapshot(vdisk_name=vm_data['data_vdisk'].devicename,
                    #                                         vpool_name=vpool.name,
                    #                                         snapshot_id=vm_data['data_snapshot_guid'],
                    #                                         api=api)
                    #         computenode_hypervisor.sdk.power_on(vm_name)
                    logger.info('Starting threads.')
                    monitoring_data = {}
                    current_thread_bundle = {'index': 1, 'vdisks': []}
                    required_thread_amount = math.ceil(float(len(vm_info.keys())) / HATester.VDISK_THREAD_LIMIT)
                    r_semaphore = Waiter(required_thread_amount + 1, auto_reset=True)  # Add another target to let this thread control the semaphore
                    for index, (vm_name, vm_data) in enumerate(vm_info.iteritems(), 1):
                        vdisks = current_thread_bundle['vdisks']
                        volume_number_range = '{0}-{1}'.format(current_thread_bundle['index'], index)
                        vdisks.extend(vm_data['vdisks'])
                        if index % HATester.VDISK_THREAD_LIMIT == 0 or index == len(vm_info.keys()):
                            # New thread bundle
                            monitor_resource = {'general': {'io': [], 'edge_clients': {}}}
                            for vdisk in vdisks:
                                monitor_resource[vdisk.name] = {
                                    'io': {'down': [], 'descending': [], 'rising': [], 'highest': None, 'lowest': None},
                                    'edge_clients': {'down': [], 'up': []}}
                            monitoring_data[volume_number_range] = monitor_resource
                            threads.append(ThreadHelper.start_thread_with_event(HATester._monitor_changes, name='iops_{0}'.format(current_thread_bundle['index']), args=(monitor_resource, vdisks, r_semaphore)))
                            current_thread_bundle['index'] = index + 1
                            current_thread_bundle['vdisks'] = []
                    for vm_name, vm_data in vm_info.iteritems():  # Write data
                        screen_names = HATester._write_data(vm_data['client'], 'fio', configuration, file_locations=['/mnt/data/{0}.raw'.format(vm_data['create_msg'])])
                        vm_data['screen_names'] = screen_names
                    logger.info('Doing IO for {0}s before bringing down the node.'.format(HATester.SLEEP_TIME))
                    now = time.time()
                    while time.time() - now < HATester.SLEEP_TIME:
                        if r_semaphore.get_counter() < required_thread_amount:
                            time.sleep(0.05)
                            continue
                        if time.time() - now % 1 == 0:
                            edge_clients = HATester._get_all_edge_clients(monitoring_data)
                            logger.info('Currently got edge clients for {0}: {1}'.format(len(edge_clients.keys()), edge_clients.keys()))
                        r_semaphore.wait()
                    # Wait again to sync
                    HATester.LOGGER.info('Syncing threads')
                    while r_semaphore.get_counter() < required_thread_amount:
                        time.sleep(0.05)
                    original_edge_clients = HATester._get_all_edge_clients(monitoring_data)
                    original_edge_clients_keys = {}
                    for vdisk_name, edge_client_info in original_edge_clients.iteritems():
                        original_edge_clients_keys[vdisk_name] = [item['key'] for item in edge_client_info]
                    # Threads ready for monitoring at this point
                    #########################
                    # Bringing original owner of the volume down
                    #########################
                    try:
                        logger.info('Stopping {0}.'.format(vm_to_stop))
                        HATester._stop_vm(hypervisor=parent_hypervisor, vmid=vm_to_stop)
                        downed_time = time.time()
                        vm_downed = True
                    except Exception as ex:
                        logger.error('Failed to stop. Got {0}'.format(str(ex)))
                        raise
                    time.sleep(HATester.IO_REFRESH_RATE)
                    # Start IO polling
                    r_semaphore.wait()
                    try:
                        while True:
                            if time.time() - downed_time > HATester.HA_TIMEOUT:
                                raise RuntimeError('HA test timed out after {0}s.'.format(HATester.HA_TIMEOUT))
                            if r_semaphore.get_counter() < required_thread_amount:
                                time.sleep(1)
                                continue
                            changed_edge_clients = []
                            edge_clients = HATester._get_all_edge_clients(monitoring_data)
                            for vdisk_name, vdisk_edge_clients in edge_clients.iteritems():
                                found_edge_client_keys = [item.get('key') for item in vdisk_edge_clients]
                                if len(found_edge_client_keys) > 0 and set(found_edge_client_keys) != {None} and set(found_edge_client_keys) != set(original_edge_clients_keys[vdisk_name]):
                                    changed_edge_clients.append(vdisk_name)
                            logger.info('Edge clients changed for {0}: {1}'.format(len(changed_edge_clients), changed_edge_clients))
                            if len(changed_edge_clients) == volume_amount:
                                logger.info('All volumes have a new edge connection at {0}. Waited {1}s.'.format(
                                    datetime.today().strftime('%Y-%m-%d %H:%M:%S'), time.time() - downed_time))
                                failed_over = True
                                break
                            logger.info('Failover did not occur after {0}s.'.format(time.time() - downed_time))
                            r_semaphore.wait()
                            time.sleep(1)
                    except Exception:
                        raise
                    finally:
                        # Wait again to sync so we can properly abort the threads
                        HATester.LOGGER.info('Syncing threads')
                        while r_semaphore.get_counter() < required_thread_amount:
                            time.sleep(0.05)
                    HATester._validate(values_to_check, monitoring_data)
                except Exception as ex:
                    failed_configurations.append({'configuration': configuration, 'reason': str(ex)})
                finally:
                    if vm_downed is True:
                        HATester._start_vm(parent_hypervisor, vm_to_stop)
                    try:
                        logger.info('Stopping iops monitoring')
                        for thread_pair in threads:
                            if thread_pair[0].isAlive():
                                thread_pair[1].set()
                        if r_semaphore:
                            r_semaphore.wait()
                        # Wait for threads to die
                        for thread_pair in threads:
                            thread_pair[0].join()
                    except Exception as ex:
                        logger.warning('Stopping the threads failed. Got {0}'.format(str(ex)))
                    for vm_name, vm_data in vm_info.iteritems():
                        for screen_name in vm_data.get('screen_names', []):
                            vm_data['client'].run(['screen', '-S', screen_name, '-X', 'quit'])
                        vm_data['screen_names'] = []
                    if failed_over:
                        # Wait for the downed node to come back up
                        start_time = time.time()
                        to_be_downed_client = None
                        while to_be_downed_client is None:
                            try:
                                to_be_downed_client = SSHClient(str_2, username='root')
                            except:
                                pass
                            time.sleep(1)
                        services = ServiceManager.list_services(to_be_downed_client)
                        for service in services:
                            if vpool.name not in service:
                                continue
                            while ServiceManager.get_service_status(service, to_be_downed_client)[0] is False:
                                if time.time() - start_time > HATester.HA_TIMEOUT:
                                    raise RuntimeError('Service {0} did not come up after {1}s. Something must be wrong with it.'.format(service, HATester.HA_TIMEOUT))
                                time.sleep(1)
                        for vm_name, vm_data in vm_info.iteritems():
                            for vdisk in vm_data['vdisks']:
                                VDiskSetup.move_vdisk(vdisk_guid=vdisk.guid, target_storagerouter_guid=str_2.guid, api=api)
        for vm_name, vm_data in vm_info.iteritems():
            HATester._stop_vm(computenode_hypervisor, vm_name, False)
        assert len(failed_configurations) == 0, 'Certain configuration failed: {0}'.format(' '.join(failed_configurations))

    @staticmethod
    def _get_all_edge_clients(monitoring_data):
        """
        Gets all edge clients from the monitoring data
        :param monitoring_data:
        :return: dict with vdisk names and their edge clients
        :rtype: dict
        """
        output = {}
        for volume_number_range, monitor_resource in monitoring_data.iteritems():
            output.update(monitor_resource['general']['edge_clients'])
        return output

    @staticmethod
    def _get_free_port(listener_ip):
        """
        Returns a free port
        :param listener_ip: ip to listen on
        :return: port number
        """
        with remote(listener_ip, [socket]) as rem:
            listening_socket = rem.socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                # Bind to first available port
                listening_socket.bind(('', 0))
                port = listening_socket.getsockname()[1]
                return port
            except socket.error as ex:
                HATester.LOGGER.error('Could not bind the socket. Got {0}'.format(str(ex)))
                raise
            finally:
                try:
                    listening_socket.close()
                except:
                    pass

    @staticmethod
    def _listen_to_address(listening_host, listening_port, queue, connection_messages, timeout, stop_event):
        """
        Listen for VMs that are ready
        :param listening_host: host to listen on
        :param listening_port: port to listen on
        :param queue: queue object to report the aswer to
        :param connection_messages: messages to listen to
        :param timeout: timeout in seconds
        :param stop_event: stop event to abort this thread
        
        :return: 
        """
        vm_ips_info = {}
        with remote(listening_host, [socket]) as rem:
            listening_socket = rem.socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                # Bind to first available port
                listening_socket.bind((listening_host, listening_port))
                listening_socket.listen(5)
                HATester.LOGGER.info('Socket now listening on port {0}, waiting to accept data.'.format(listening_port))
                start_time = time.time()
                while len(connection_messages) > 0 and not stop_event.is_set():
                    if time.time() - start_time > timeout:
                        raise RuntimeError('Listening timed out after {0}s'.format(timeout))
                    conn, addr = listening_socket.accept()
                    HATester.LOGGER.debug('Connected with {0}:{1}'.format(addr[0], addr[1]))
                    data = conn.recv(1024)
                    HATester.LOGGER.debug('Connector said {0}'.format(data))
                    if data in connection_messages:
                        connection_messages.remove(data)
                        vm_number = data.rsplit('_', 1)[-1]
                        vm_name = '{0}_{1}'.format(HATester.VM_NAME, vm_number)
                        HATester.LOGGER.debug('Recognized sender as {0}'.format(vm_name))
                        vm_ips_info[vm_name] = {'ip': addr[0]}
            except Exception as ex:
                HATester.LOGGER.error('Error while listening for VM messages.. Got {0}'.format(str(ex)))
                raise
            finally:
                listening_socket.close()
        queue.put(vm_ips_info)

    @staticmethod
    def _create_vm(hypervisor_ip, disks, networks, edge_details, cd_path, vm_name=VM_NAME, os_type=VM_OS_TYPE):
        """
        Creates and wait for the VM to be fully connected
        :return: None
        """
        edge_hostname = edge_details['hostname']
        edge_port = edge_details['port']

        computenode_hypervisor = HypervisorFactory.get(hypervisor_ip, HATester.HYPERVISOR_USER, HATester.HYPERVISOR_PASSWORD, HATester.HYPERVISOR_TYPE)
        ##################
        # SETUP VMACHINE #
        ##################
        HATester.LOGGER.info('Creating VM `{0}`'.format(vm_name))
        computenode_hypervisor.sdk.create_vm(vm_name,
                                             vcpus=HATester.VM_VCPUS,
                                             ram=HATester.VM_VRAM,
                                             cdrom_iso=cd_path,
                                             disks=disks,
                                             networks=networks,
                                             ovs_vm=True,
                                             hostname=edge_hostname,
                                             edge_port=edge_port,
                                             start=True,
                                             os_type=os_type)
        HATester.LOGGER.info('Created VM `{0}`!'.format(vm_name))

    @staticmethod
    def _cleanup_vm(hypervisor, vmid, blocking=True):
        """
        Cleans up the created virtual machine
        :param hypervisor: hypervisor instance
        :param vmid: vm identifier
        :param blocking: boolean to determine whether errors should raise or not
        :return: None
        :rtype: NoneType
        """
        try:
            hypervisor.sdk.delete_vm(vmid=vmid, delete_disks=False)
        except Exception as ex:
            HATester.LOGGER.error(str(ex))
            if blocking is True:
                raise
            else:
                pass

    @staticmethod
    def _stop_vm(hypervisor, vmid, blocking=True):
        """
        Stop the created virtual machine
        :param hypervisor: hypervisor instance
        :param vmid: vm identifier
        :param blocking: boolean to determine whether errors should raise or not
        :return: None
        :rtype: NoneType
        """
        try:
            hypervisor.sdk.destroy(vmid=vmid)
        except Exception as ex:
            HATester.LOGGER.error(str(ex))
            if blocking is True:
                raise
            else:
                pass

    @staticmethod
    def _start_vm(hypervisor, vmid, blocking=True):
        """
        starts the created virtual machine
        :param hypervisor: hypervisor instance
        :param vmid: vm identifier
        :param blocking: boolean to determine whether errors should raise or not
        :return: None
        :rtype: NoneType
        """
        try:
            hypervisor.sdk.power_on(vmid=vmid)
        except Exception as ex:
            HATester.LOGGER.error(str(ex))
            if blocking is True:
                raise
            else:
                pass

    @staticmethod
    def _cleanup_generated_files(client):
        """
        Cleans up generated files
        :param client: ovs ssh client for current node
        :type client: ovs.extensions.generic.sshclient.SSHClient
        :return: None
        :rtype: NoneType
        """
        for key, value in HATester.CLOUD_INIT_DATA.iteritems():
            HATester.LOGGER.info('Deleting {0}'.format(value))
            client.file_delete(value)
        return True

    @staticmethod
    def _generate_cloud_init(client, convert_script_loc, port, hypervisor_ip, create_msg, username='test', passwd='test', root_passwd='rooter'):
        """
        Generates a cloud init file with some userdata in (for a virtual machine)
        :param client: ovs ssh client for current node
        :type client: ovs.extensions.generic.sshclient.SSHClient
        :param username: username of the user that will be added to the vm
        :type username: str
        :param passwd: password of the user that will be added to the vm
        :type passwd: str
        :param root_passwd: password of root that will be added to the vm
        :type root_passwd: str
        :param convert_script_loc: location to the conversion script
        :type convert_script_loc: str
        :param create_msg: message to send when the vm is done
        :type create_msg: str
        :return: cloud init destination
        :rtype: str
        """
        path = HATester.CLOUD_INIT_DATA.get('user-data_loc')
        # write out user-data
        lines = [
            '#!/bin/bash\n',
            '#user conf',
            'sudo echo "root:{0}" | chpasswd'.format(root_passwd),
            'sudo useradd {0}'.format(username),
            'sudo echo "{0}:{1}" | chpasswd'.format(username, passwd),
            'sudo adduser {0} sudo\n'.format(username),
            'apt-get update',
            'apt-get install fio -y',
            'sed -ie "s/PermitRootLogin prohibit-password/PermitRootLogin yes/" /etc/ssh/sshd_config',
            'sed -ie "s/PasswordAuthentication no/PasswordAuthentication yes/" /etc/ssh/sshd_config',
            'sudo service ssh restart',
            'parted /dev/vdb mklabel gpt mkpart 1 ext4 1MiB 5G',
            'mkfs.ext4 /dev/vdb1',
            'mkdir /mnt/data',
            'mount /dev/vdb1 /mnt/data/',
            'echo -n {0} | netcat -w 0 {1} {2}'.format(create_msg, hypervisor_ip, port)

        ]
        with open(path, 'w') as user_data_file:
            user_data_file.write('\n'.join(lines))
        client.file_upload(path, path)

        # run script that generates meta-data and parser user-data and meta-data to a iso
        convert_cmd = [convert_script_loc, '--user-data', path, HATester.CLOUD_INIT_DATA.get('config_dest')]
        try:
            client.run(convert_cmd)
            return HATester.CLOUD_INIT_DATA.get('config_dest')
        except subprocess.CalledProcessError as ex:
            HATester.LOGGER.error('Could not generate the cloud init file on {0}. Got {1} during iso conversion.'.format(client.ip, str(ex.output)))
            raise

    @staticmethod
    def test_ha_fio(fio_bin_path, vpool, compute_client, cluster_info, api, disk_amount=1, timeout=HA_TIMEOUT):
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
        logger = HATester.LOGGER
        str_2 = cluster_info['storagerouters']['str2']
        std_1 = cluster_info['storagedrivers']['std1']
        std_2 = cluster_info['storagedrivers']['std2']

        vm_to_stop = HATester.PARENT_HYPERVISOR_INFO['vms'][str_2.ip]['name']
        parent_hypervisor = HypervisorFactory.get(HATester.PARENT_HYPERVISOR_INFO['ip'],
                                                  HATester.PARENT_HYPERVISOR_INFO['user'], HATester.PARENT_HYPERVISOR_INFO['password'],
                                                  HATester.PARENT_HYPERVISOR_INFO['type'])
        values_to_check = {
            'source_std': std_2.serialize(),
            'target_std': std_1.serialize(),
            'vdisks': []
        }
        # Create vdisks
        protocol = std_2.cluster_node_config['network_server_uri'].split(':')[0]
        edge_configuration = {'fio_bin_location': fio_bin_path, 'hostname': std_2.storage_ip,
                              'port': std_2.ports['edge'],
                              'protocol': protocol,
                              'volumename': []}
        vdisk_info = {}
        failed_configurations = []

        for index in xrange(0, disk_amount):
            try:
                vdisk_name = '{0}_vdisk{1}'.format(HATester.TEST_NAME, str(index).zfill(3))
                data_vdisk = VDiskHelper.get_vdisk_by_guid(VDiskSetup.create_vdisk(vdisk_name, vpool.name, HATester.AMOUNT_TO_WRITE, std_2.storage_ip, api))
                vdisk_info[vdisk_name] = data_vdisk
                edge_configuration['volumename'].append(data_vdisk.devicename.rsplit('.', 1)[0].split('/', 1)[1])
                values_to_check['vdisks'].append(data_vdisk.serialize())
            except TimeOutError:
                logger.error('Creating the vdisk has timed out.')
                raise
            except RuntimeError as ex:
                logger.error('Could not create the vdisk. Got {0}'.format(str(ex)))
                raise
        for configuration in HATester.DATA_TEST_CASES:
            threads = []
            vm_downed = False
            screen_names = []
            failed_over = False
            r_semaphore = None
            try:
                logger.info('Starting threads.')  # Separate because creating vdisks takes a while, while creating the threads does not
                monitoring_data = {}
                current_thread_bundle = {'index': 1, 'vdisks': []}
                required_thread_amount = math.ceil(len(vdisk_info.keys()) / HATester.VDISK_THREAD_LIMIT)
                r_semaphore = Waiter(required_thread_amount + 1, auto_reset=True)  # Add another target to let this thread control the semaphore
                for index, (vdisk_name, vdisk_object) in enumerate(vdisk_info.iteritems(), 1):
                    vdisks = current_thread_bundle['vdisks']
                    volume_number_range = '{0}-{1}'.format(current_thread_bundle['index'], index)
                    vdisks.append(vdisk_object)
                    if index % HATester.VDISK_THREAD_LIMIT == 0 or index == len(vdisk_info.keys()):
                        # New thread bundle
                        monitor_resource = {'general': {'io': [], 'edge_clients': {}}}
                        for vdisk in vdisks:
                            monitor_resource[vdisk.name] = {'io': {'down': [], 'descending': [], 'rising': [], 'highest': None, 'lowest': None},
                                                            'edge_clients': {'down': [], 'up': []}}
                        monitoring_data[volume_number_range] = monitor_resource
                        threads.append(ThreadHelper.start_thread_with_event(HATester._monitor_changes,
                                                                            name='iops_{0}'.format(current_thread_bundle['index']),
                                                                            args=(monitor_resource, vdisks, r_semaphore)))
                        current_thread_bundle['index'] = index + 1
                        current_thread_bundle['vdisks'] = []
                try:
                    screen_names = HATester._write_data(compute_client, 'fio', configuration, edge_configuration)
                except Exception as ex:
                    logger.error('Could not start threading. Got {0}'.format(str(ex)))
                    raise
                logger.info('Doing IO for {0}s before bringing down the node.'.format(HATester.SLEEP_TIME))
                now = time.time()
                while time.time() - now < HATester.SLEEP_TIME:
                    if r_semaphore.get_counter() < required_thread_amount:
                        time.sleep(0.05)
                        continue
                    if time.time() - now % 1 == 0:
                        io_volumes = HATester._get_all_vdisks_with_io(monitoring_data)
                        logger.info('Currently got io for {0}: {1}'.format(len(io_volumes), io_volumes))
                    r_semaphore.wait()
                # Wait again to sync
                HATester.LOGGER.info('Syncing threads')
                while r_semaphore.get_counter() < required_thread_amount:
                    time.sleep(0.05)
                # Threads ready for monitoring at this point
                #########################
                # Bringing original owner of the volume down
                #########################
                try:
                    logger.info('Stopping {0}.'.format(vm_to_stop))
                    HATester._stop_vm(hypervisor=parent_hypervisor, vmid=vm_to_stop)
                    downed_time = time.time()
                    vm_downed = True
                except Exception as ex:
                    logger.error('Failed to stop. Got {0}'.format(str(ex)))
                    raise
                time.sleep(HATester.IO_REFRESH_RATE)
                # Start IO polling
                r_semaphore.wait()
                try:
                    while True:
                        if time.time() - downed_time > timeout:
                            raise RuntimeError('HA test timed out after {0}s.'.format(timeout))
                        if r_semaphore.get_counter() < required_thread_amount:
                            time.sleep(1)
                            continue
                        # Calculate to see if IO is back
                        io_volumes = HATester._get_all_vdisks_with_io(monitoring_data)
                        logger.info('Currently got io for {0}: {1}'.format(len(io_volumes), io_volumes))
                        if len(io_volumes) == disk_amount:
                            logger.info('All threads came through with IO at {0}. Waited {1}s for IO.'.format(datetime.today().strftime('%Y-%m-%d %H:%M:%S'), time.time() - downed_time))
                            failed_over = True
                            break
                        logger.info('IO has not come through for {0}s.'.format(time.time() - downed_time))
                        r_semaphore.wait()
                        time.sleep(1)
                except Exception:
                    raise
                finally:
                    # Wait again to sync so we can properly abort the threads
                    HATester.LOGGER.info('Syncing threads')
                    while r_semaphore.get_counter() < required_thread_amount:
                        time.sleep(0.05)
                HATester._validate(values_to_check, monitoring_data)
            except Exception as ex:
                failed_configurations.append({'configuration': configuration, 'reason': str(ex)})
            finally:
                if vm_downed is True:
                    HATester._start_vm(parent_hypervisor, vm_to_stop)
                if screen_names:
                    for screen_name in screen_names:
                        compute_client.run(['screen', '-S', screen_name, '-X', 'quit'])
                try:
                    logger.info('Stopping iops monitoring')
                    for thread_pair in threads:
                        if thread_pair[0].isAlive():
                            thread_pair[1].set()
                    if r_semaphore:
                        r_semaphore.wait()
                    # Wait for threads to die
                    for thread_pair in threads:
                        thread_pair[0].join()
                except Exception as ex:
                    logger.warning('Stopping the threads failed. Got {0}'.format(str(ex)))
                if failed_over:
                    # Wait for the downed node to come back up
                    to_be_downed_client = None
                    while to_be_downed_client is None:
                        try:
                            to_be_downed_client = SSHClient(str_2, username='root')
                        except:
                            pass
                        time.sleep(1)
                    services = ServiceManager.list_services(to_be_downed_client)
                    for service in services:
                        if vpool.name not in service:
                            continue
                        while ServiceManager.get_service_status(service, to_be_downed_client)[0] is False:
                            time.sleep(1)
                    for vdisk_name, vdisk_object in vdisk_info.iteritems():
                        VDiskSetup.move_vdisk(vdisk_guid=vdisk_object.guid, target_storagerouter_guid=str_2.guid, api=api)

        assert len(failed_configurations) == 0, 'Certain configuration failed: {0}'.format(' '.join(failed_configurations))

    @staticmethod
    def _get_all_vdisks_with_io(monitoring_data):
        output = []
        for volume_number_range, monitor_resource in monitoring_data.iteritems():
            output.extend(monitor_resource['general']['io'])
        return output

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

    @staticmethod
    def _cleanup_vdisk(vdisk_name, vpool_name, blocking=True):
        """
        Attempt to cleanup vdisk
        :param vdisk_name: name of the vdisk
        :param vpool_name: name of the vpool
        :param blocking: boolean to determine whether errors should raise or not
        :return: None
        :rtype: NoneType
        """
        try:
            VDiskRemover.remove_vdisk_by_name('{0}.raw'.format(vdisk_name), vpool_name)
        except Exception as ex:
            HATester.LOGGER.error(str(ex))
            if blocking is True:
                raise
            else:
                pass

    @staticmethod
    def _monitor_changes(results, vdisks, r_semaphore, stop_event):
        """
        Threading method that will check for IOPS downtimes
        :param results: variable reserved for this thread
        :type results: dict
        :param vdisks: vdisk object
        :type vdisks: list(ovs.dal.hybrids.vdisk.VDISK)
        :param r_semaphore: semaphore object to lock threads
        :type r_semaphore: ovs.extensions.generic.threadhelpers.Waiter
        :param stop_event: Threading event to watch for
        :type stop_event: threading._Event
        :return: None
        :rtype: NoneType
        """
        last_recorded_iops = {}
        while not stop_event.is_set():
            general_info = results['general']
            general_info['in_progress'] = True
            has_io = []
            edge_info = {}
            for vdisk in vdisks:
                edge_info[vdisk.name] = []
            # Reset counters
            general_info['io'] = has_io
            general_info['edge_clients'].update(edge_info)
            now = datetime.today().strftime('%Y-%m-%d %H:%M:%S')
            now_sec = time.time()
            for vdisk in vdisks:
                last_iops = last_recorded_iops.get(vdisk.name, 0)
                result = results[vdisk.name]
                vdisk_stats = vdisk.statistics
                vdisk_edge_clients = vdisk.edge_clients
                current_iops = vdisk_stats['4k_read_operations_ps'] + vdisk_stats['4k_write_operations_ps']
                io_section = result['io']
                if current_iops == 0:
                    io_section['down'].append((now, current_iops))
                else:
                    has_io.append(vdisk.name)
                    if last_iops >= current_iops:
                        io_section['rising'].append((now, current_iops))
                    else:
                        io_section['descending'].append((now, current_iops))
                    if current_iops > io_section['highest'] or io_section['highest'] is None:
                        io_section['highest'] = current_iops
                    if current_iops < io_section['lowest'] or io_section['lowest'] is None:
                        io_section['lowest'] = current_iops
                edge_client_section = result['edge_clients']
                edge_info[vdisk.name] = vdisk_edge_clients
                if len(vdisk_edge_clients) == 0:
                    edge_client_section['down'].append((now, vdisk_edge_clients))
                else:
                    edge_client_section['up'].append((now, vdisk_edge_clients))
                # Sleep to avoid caching
                last_recorded_iops[vdisk.name] = current_iops
            general_info['io'] = has_io
            general_info['edge_clients'].update(edge_info)
            duration = time.time() - now_sec
            HATester.LOGGER.debug('IO for {0} at {1}. Call took {2}'.format(has_io, now, duration))
            HATester.LOGGER.debug('Edge clients for {0} at {1}. Call took {2}'.format(edge_info, now, duration))
            general_info['in_progress'] = False
            time.sleep(0 if duration > HATester.IO_REFRESH_RATE else HATester.IO_REFRESH_RATE - duration)
            r_semaphore.wait(30 * 60)  # Let each thread wait for another

    @staticmethod
    def _write_data(client, cmd_type, configuration, edge_configuration=None, screen=True, data_to_write=AMOUNT_TO_WRITE, file_locations=None):
        """
        Fire and forget an IO test
        Starts a screen session detaches the sshclient
        :param client: ovs ssh client for the vm
        :type client: ovs.extensions.generic.sshclient.SSHClient
        :param cmd_type: type of command. Was used to differentiate between dd and fio
        :type cmd_type: str
        :param configuration: configuration params for fio. eg (10, 90) first value represents read, second one write percentage
        :type configuration: tuple
        :param edge_configuration: configuration to fio over edge
        :type edge_configuration: dict
        :return: list of screen names (empty if screen is False)
        :rtype: list
        """
        bs = '4k'
        iodepth = 32
        write_size = data_to_write
        cmds = []
        screen_names = []
        if cmd_type != 'fio':
            raise ValueError('{0} is not supported for writing data.'.format(cmd_type))
        config = ['--iodepth={0}'.format(iodepth), '--rw=randrw', '--bs={0}'.format(bs), '--direct=1',
                  '--rwmixread={0}'.format(configuration[0]), '--rwmixwrite={0}'.format(configuration[1]), '--randrepeat=0']
        if edge_configuration:
            fio_vdisk_limit = HATester.FIO_VDISK_LIMIT
            volumes = edge_configuration['volumename']
            fio_amount = int(math.ceil(float(len(volumes)) / fio_vdisk_limit))
            for fio_nr in xrange(0, fio_amount):
                vols = volumes[fio_nr * fio_vdisk_limit: (fio_nr + 1) * fio_vdisk_limit]
                # Volumedriver envir params
                additional_settings = ['ulimit -n 4096;']
                # Append edge fio stuff
                additional_config = ['--ioengine=openvstorage', '--hostname={0}'.format(edge_configuration['hostname']),
                                     '--port={0}'.format(edge_configuration['port']), '--protocol={0}'.format(edge_configuration['protocol']),
                                     '--enable_ha=1', '--group_reporting=1']
                verify_config = ['--verify=crc32c-intel', '--verifysort=1', '--verify_fatal=1', '--verify_backlog=1000000']
                # Generate test names for each volume
                volumes = edge_configuration['volumename']
                if isinstance(volumes, str):
                    volumes = [volumes]
                if not isinstance(volumes, list):
                    raise TypeError('Volumes should be string or list')
                fio_jobs = []
                for index, volume in enumerate(vols):
                    fio_jobs.append('--name=test{0}'.format(index))
                    fio_jobs.append('--volumename={0}'.format(volume))
                cmds.append(additional_settings + [edge_configuration['fio_bin_location']] + config + additional_config + verify_config + fio_jobs)
        else:
            fio_jobs = []
            if file_locations:
                for index, file_location in enumerate(file_locations):
                    fio_jobs.append('--name=test{0}'.format(index))
                    fio_jobs.append('--filename={0}'.format(file_location))
            additional_config = ['--ioengine=libaio', '--size={0}'.format(write_size)]
            cmds.append(['fio'] + config + additional_config + fio_jobs)
        if screen is True:
            # exec bash to keep it running
            for index, cmd in enumerate(cmds):
                screen_name = 'fio_{0}'.format(index)
                cmds[index] = 'screen -S {0} -dm bash -c "while {1}; do :; done; exec bash"'.format(screen_name, ' '.join(cmd))
                screen_names.append(screen_name)
        for cmd in cmds:
            HATester.LOGGER.info('Writing data with: {0}'.format(cmd))
            client.run(cmd, allow_insecure=True)
        return screen_names


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
