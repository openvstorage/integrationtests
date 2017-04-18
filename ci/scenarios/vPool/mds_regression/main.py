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
import os
import re
import json
import math
import uuid
import time
import errno
import Queue
import random
import socket
import threading
import subprocess
from datetime import datetime
from ci.api_lib.helpers.api import OVSClient
from ci.api_lib.helpers.api import TimeOutError
from ci.api_lib.helpers.exceptions import VDiskNotFoundError
from ci.api_lib.helpers.hypervisor.hypervisor import HypervisorFactory
from ci.api_lib.helpers.storagerouter import StoragerouterHelper
from ci.api_lib.helpers.system import SystemHelper
from ci.api_lib.helpers.thread import ThreadHelper, Waiter
from ci.api_lib.helpers.vdisk import VDiskHelper
from ci.api_lib.helpers.vpool import VPoolHelper
from ci.api_lib.remove.vdisk import VDiskRemover
from ci.api_lib.setup.vdisk import VDiskSetup
from ci.main import CONFIG_LOC
from ci.main import SETTINGS_LOC
from ovs.extensions.generic.configuration import Configuration
from ovs.extensions.generic.remote import remote
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.packages.package import PackageManager
from ovs.lib.generic import GenericController
from ovs.log.log_handler import LogHandler


class RegressionTester(object):

    CASE_TYPE = 'FUNCTIONAL'
    TEST_NAME = 'ci_scenario_edge_test'
    LOGGER = LogHandler.get(source='scenario', name=TEST_NAME)

    IO_TIME = 5 * 60  # Time to do IO for
    TEST_TIMEOUT = 300
    VM_CONNECTING_TIMEOUT = 5

    AMOUNT_TO_WRITE = 10 * 1024 ** 3

    VM_NAME = 'HA-test'
    VM_OS_TYPE = 'ubuntu16.04'

    VM_USERNAME = 'root'  # vm credentials & details
    VM_PASSWORD = 'rooter'
    VM_VCPUS = 4
    VM_VRAM = 1024  # In MB

    VM_WAIT_TIME = 300  # wait time before timing out on the vm install in seconds

    DATA_TEST_CASES = [(0, 100), (30, 70), (40, 60), (50, 50), (70, 30), (100, 0)]  # read write patterns to test (read, write)

    CLOUD_INIT_DATA = {
        'script_loc': 'https://raw.githubusercontent.com/kinvaris/cloud-init/master/create-config-drive',
        'script_dest': '/tmp/cloud_init_script.sh',
        'user-data_loc': '/tmp/user-data-migrate-test',
        'config_dest': '/tmp/cloud-init-config-migrate-test'
    }

    REQUIRED_PACKAGES_HYPERVISOR = ['qemu-kvm', 'libvirt0', 'python-libvirt', 'virtinst']
    REQUIRED_PACKAGE_CLOUD_INIT = ['genisoimage']

    FIO_BIN = {'url': 'http://www.include.gr/fio.bin.latest', 'location': '/tmp/fio.bin.latest'}
    FIO_BIN_EE = {'url': 'http://www.include.gr/fio.bin.latest.ee', 'location': '/tmp/fio.bin.latest'}

    VDISK_THREAD_LIMIT = 5  # Each monitor thread queries x amount of vdisks
    FIO_VDISK_LIMIT = 50  # Each fio uses x disks
    IO_REFRESH_RATE = 5  # in seconds

    with open(CONFIG_LOC, 'r') as JSON_CONFIG:
        SETUP_CFG = json.load(JSON_CONFIG)

    # Collect details about parent hypervisor
    PARENT_HYPERVISOR_INFO = SETUP_CFG['ci']['hypervisor']

    # Hypervisor details
    HYPERVISOR_INFO = {'type': PARENT_HYPERVISOR_INFO['type'],
                       'user': SETUP_CFG['ci']['user']['shell']['username'],
                       'password': SETUP_CFG['ci']['user']['shell']['password']}

    @classmethod
    # @gather_results(CASE_TYPE, LOGGER, TEST_NAME)
    def main(cls, blocked):
        """
        Run all required methods for the test
        status depends on attributes in class: ci.api_lib.helpers.testtrailapi.TestrailResult
        case_type depends on attributes in class: ci.api_lib.helpers.testtrailapi.TestrailCaseType
        :param blocked: was the test blocked by other test?
        :return: results of test
        :rtype: dict
        """
        return cls.start_test()

    @classmethod
    def start_test(cls, vm_amount=1, hypervisor_info=HYPERVISOR_INFO):
        api, cluster_info, compute_client, to_be_downed_client, is_ee, cloud_image_path, cloud_init_loc = cls.setup()
        listening_port = cls._get_free_port(compute_client.ip)

        std_2 = cluster_info['storagedrivers']['std2']
        protocol = std_2.cluster_node_config['network_server_uri'].split(':')[0]
        edge_details = {'port': std_2.ports['edge'], 'hostname': std_2.storage_ip, 'protocol': protocol}

        computenode_hypervisor = HypervisorFactory.get(compute_client.ip,
                                                       hypervisor_info['user'],
                                                       hypervisor_info['password'],
                                                       hypervisor_info['type'])
        # vm_info, connection_messages, volume_amount = cls._prepare_vm_disks(cluster_info=cluster_info,
        #                                                                     to_be_downed_client=to_be_downed_client,
        #                                                                     cloud_image_path=cloud_image_path,
        #                                                                     cloud_init_loc=cloud_init_loc,
        #                                                                     api=api,
        #                                                                     vm_amount=vm_amount,
        #                                                                     port=listening_port,
        #                                                                     hypervisor_ip=compute_client.ip)
        # vm_info = cls._create_vms(ip=compute_client.ip,
        #                           port=listening_port,
        #                           connection_messages=connection_messages,
        #                           vm_info=vm_info,
        #                           edge_details=edge_details,
        #                           hypervisor_client=computenode_hypervisor)
        # @TODO: remove this section as it just rebuilds for faster testing
        vp = VPoolHelper.get_vpool_by_name('myvpool01')
        available_storagedrivers = [storagedriver for storagedriver in vp.storagedrivers]
        std_1 = [std for std in available_storagedrivers if std.storage_ip == '10.100.69.121'][0]
        std_2 = [std for std in available_storagedrivers if std.storage_ip == '10.100.69.120'][0]
        str_1 = std_1.storagerouter  # Will act as volumedriver node
        str_2 = std_2.storagerouter  # Will act as volumedriver node
        str_3 = [storagerouter for storagerouter in StoragerouterHelper.get_storagerouters() if
                 storagerouter.guid not in [str_1.guid, str_2.guid]][0]  # Will act as compute node

        cluster_info = {'storagerouters': {'str3': str_3, 'str2': str_2, 'str1': str_1}, 'storagedrivers': {'std1': std_1, 'std2': std_2}, 'vpool': vp}
        volume_amount = 3
        vdisks = [VDiskHelper.get_vdisk_by_guid('b1f224c2-e263-4847-8835-5009db74ce50'), VDiskHelper.get_vdisk_by_guid('ef97599a-f35d-443e-a647-94ae5cd517d8')]
        vm_info = {'HA-test_000': {'vdisks': vdisks, 'created': False, 'data_snapshot_guid': u'156fe4b0-2a85-4cfe-b74b-c82662a79c89', 'create_msg': '73e56a0c-3fd8-4c78-b8c9-cefdf30311ce_000', 'ip': '192.168.122.238', 'disks': [{'mountpoint': '/mnt/myvpool01/ci_scenario_edge_test_vdisk_boot_000.raw'}, {'mountpoint': '/mnt/myvpool01/ci_scenario_edge_test_vdisk_data_000.raw'}], 'cd_path': '/mnt/myvpool01/ci_scenario_edge_test_vdisk_cd_000.raw', 'networks': [{'model': 'e1000', 'mac': 'RANDOM', 'network': 'default'}]}}
        cls.run_test(cluster_info=cluster_info,
                     compute_client=compute_client,
                     is_ee=is_ee,
                     disk_amount=volume_amount,
                     vm_info=vm_info,
                     api=api)

    @classmethod
    def setup(cls, required_packages_cloud_init=REQUIRED_PACKAGE_CLOUD_INIT,
              required_packages_hypervisor=REQUIRED_PACKAGES_HYPERVISOR,
              cloud_init_info=CLOUD_INIT_DATA, logger=LOGGER):
        """
        Performs all required actions to start the testrun
        :param required_packages_cloud_init: packages required the run cloud init
        :type required_packages_cloud_init: list
        :param required_packages_hypervisor: packages required to be a hypervisor
        :type required_packages_hypervisor: list
        :param cloud_init_info: cloud init settings
        :type cloud_init_info: dict
        :param logger: logging instance
        :type logger: ovs.log.log_handler.LogHandler
        :return: 
        """
        vpool = None
        for vp in VPoolHelper.get_vpools():
            if len(vp.storagedrivers) >= 2 and vp.configuration['dtl_mode'] == 'sync':
                vpool = vp
                break
        assert vpool is not None, 'Not enough vPools to test. We need at least a vPool with 2 storagedrivers'
        available_storagedrivers = [storagedriver for storagedriver in vpool.storagedrivers]
        std_1 = available_storagedrivers.pop(random.randrange(len(available_storagedrivers)))
        std_2 = available_storagedrivers.pop(random.randrange(len(available_storagedrivers)))
        str_1 = std_1.storagerouter  # Will act as volumedriver node
        str_2 = std_2.storagerouter  # Will act as volumedriver node
        str_3 = [storagerouter for storagerouter in StoragerouterHelper.get_storagerouters() if
                 storagerouter.guid not in [str_1.guid, str_2.guid]][0]  # Will act as compute node

        with open(CONFIG_LOC, 'r') as config_file:
            config = json.load(config_file)
        api = OVSClient(config['ci']['grid_ip'],
                        config['ci']['user']['api']['username'],
                        config['ci']['user']['api']['password'])
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
        logger.info('Chosen source storagedriver is: {0}'.format(std_1.storage_ip))
        logger.info('Chosen destination storagedriver is: {0}'.format(std_2.storage_ip))

        to_be_downed_client = SSHClient(str_2, username='root')  # build ssh clients
        compute_client = SSHClient(str_3, username='root')

        images = settings['images']  # check if enough images available
        assert len(images) >= 1, 'Not enough images in `{0}`'.format(SETTINGS_LOC)

        image_path = images[0]  # check if image exists
        assert to_be_downed_client.file_exists(image_path), 'Image `{0}` does not exists on `{1}`!'.format(images[0], to_be_downed_client.ip)

        cloud_init_loc = cloud_init_info['script_dest']  # Get the cloud init file
        to_be_downed_client.run(['wget', cloud_init_info['script_loc'], '-O', cloud_init_loc])
        to_be_downed_client.file_chmod(cloud_init_loc, 755)
        assert to_be_downed_client.file_exists(cloud_init_loc), 'Could not fetch the cloud init script'

        missing_packages = SystemHelper.get_missing_packages(to_be_downed_client.ip, required_packages_cloud_init)
        assert len(missing_packages) == 0, 'Missing {0} package(s) on `{1}`: {2}'.format(len(missing_packages),
                                                                                         to_be_downed_client.ip,
                                                                                         missing_packages)
        missing_packages = SystemHelper.get_missing_packages(compute_client.ip, required_packages_hypervisor)
        assert len(missing_packages) == 0, 'Missing {0} package(s) on `{1}`: {2}'.format(len(missing_packages),
                                                                                         compute_client.ip,
                                                                                         missing_packages)
        cluster_info = {'storagerouters': {'str1': str_1, 'str2': str_2, 'str3': str_3},
                        'storagedrivers': {'std1': std_1, 'std2': std_2},
                        'vpool': vpool}
        installed_versions = PackageManager.get_installed_versions(client=compute_client)
        is_ee = 'volumedriver-ee-base' in installed_versions
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
        return api, cluster_info, compute_client, to_be_downed_client, is_ee, image_path, cloud_init_loc

    @classmethod
    def run_test(cls, cluster_info, compute_client, is_ee, vm_info, disk_amount, api, vm_username=VM_USERNAME, vm_password=VM_PASSWORD,
                 timeout=TEST_TIMEOUT, data_test_cases=DATA_TEST_CASES, logger=LOGGER):
        """
        Runs the test as described in https://github.com/openvstorage/dev_ops/issues/64
        :param cluster_info: information about the cluster
        :param compute_client: SSHclient of the computenode
        :param is_ee: is entreprise edition or not
        :param vm_info: vm information
        :param api: api instance
        :param disk_amount: amount of disks
        :param vm_username: username to login on all vms
        :param vm_password: password to login on all vms
        :param timeout: timeout in seconds
        :param data_test_cases: data rw ratios to test
        :param logger: logging instance
        :return: 
        """
        str_3 = cluster_info['storagerouters']['str3']
        std_1 = cluster_info['storagedrivers']['std1']
        std_2 = cluster_info['storagedrivers']['std2']

        # Cache to validate properties
        values_to_check = {
            'source_std': std_1.serialize(),
            'target_std': std_2.serialize()
        }
        # Prep VM listener #
        failed_configurations = []
        ee_info = None
        if is_ee is True:
            # @ Todo create user instead
            ee_info = {'username': 'root', 'password': 'rooter'}

        # Extract vdisk info from vm_info
        vdisk_info = {}
        for vm_name, vm_object in vm_info.iteritems():
            for vdisk in vm_object['vdisks']:
                vdisk_info.update({vdisk.name: vdisk})
        try:
            cls._adjust_automatic_scrubbing(disable=True)
            with remote(str_3.ip, [SSHClient]) as rem:
                for test_run_nr, configuration in enumerate(data_test_cases):
                    r_semaphore = None
                    threads = {'evented': {'io': [],
                                           'snapshots': []}}
                    output_files = []
                    try:
                        logger.info('Starting the following configuration: {0}'.format(configuration))
                        if test_run_nr == 0:  # Build reusable ssh clients
                            for vm_name, vm_data in vm_info.iteritems():
                                vm_client = rem.SSHClient(vm_data['ip'], vm_username, vm_password)
                                vm_client.file_create('/mnt/data/{0}.raw'.format(vm_data['create_msg']))
                                vm_data['client'] = vm_client
                        io_thread_pairs, monitoring_data, r_semaphore = cls._start_io_polling_threads(volume_bundle=vdisk_info)
                        threads['evented']['io'] = io_thread_pairs
                        for vm_name, vm_data in vm_info.iteritems():  # Write data
                            screen_names, output_files = cls._write_data(client=vm_data['client'],
                                                                         cmd_type='fio',
                                                                         configuration=configuration,
                                                                         file_locations=['/mnt/data/{0}.raw'.format(vm_data['create_msg'])],
                                                                         ee_info=ee_info)
                            vm_data['screen_names'] = screen_names
                        logger.info('Doing IO for {0}s before bringing down the node.'.format(cls.IO_TIME))
                        threads['evented']['snapshots'] = cls._start_snapshotting_threads(volume_bundle=vdisk_info, api=api)
                        # @todo start another thread that will wait 10 min before deleting some snapshots
                        cls._keep_threads_running(r_semaphore=r_semaphore,
                                                  threads=threads['evented']['io'],
                                                  shared_resource=monitoring_data,
                                                  duration=cls.IO_TIME)
                        # Threads ready for monitoring at this point
                        cls._delete_snapshots(volume_bundle=vdisk_info, api=api)
                        scrubbing_result = cls._start_scrubbing(volume_bundle=vdisk_info)  # Starting to scrub, offloaded to celery
                        cls._trigger_mds_failover()  # Trigger mds failover while scrubber is busy
                        # Do some monitoring further for 60s
                        cls._keep_threads_running(r_semaphore=r_semaphore,
                                                  threads=threads['evented']['io'],
                                                  shared_resource=monitoring_data,
                                                  duration=60)
                        time.sleep(cls.IO_REFRESH_RATE * 2)
                        downed_time = time.time()
                        # Start IO polling to verify nothing went down
                        cls._poll_io(r_semaphore=r_semaphore,
                                     required_thread_amount=len(threads),
                                     shared_resource=monitoring_data,
                                     downed_time=downed_time,
                                     timeout=timeout,
                                     output_files=output_files,
                                     client=compute_client,
                                     disk_amount=disk_amount)
                        api.wait_for_task(task_id=scrubbing_result.id)  # Wait for scrubbing to finish
                        cls._validate(values_to_check, monitoring_data)
                    except Exception as ex:
                        logger.error('Running the test for configuration {0} has failed because {1}'.format(configuration, str(ex)))
                        failed_configurations.append({'configuration': configuration, 'reason': str(ex)})
                        raise
                    finally:
                        for thread_category, threads in threads['evented'].iteritems():
                            logger.info('Stopping {} threads.'.format(thread_category))
                            for thread_pair in threads:
                                if thread_pair[0].isAlive():
                                    thread_pair[1].set()
                                # Wait again to sync
                                logger.info('Syncing threads')
                                while r_semaphore.get_counter() < len(threads):  # Wait for the number of threads we currently have.
                                    time.sleep(0.05)
                                r_semaphore.wait()  # Unlock them to let them stop (the object is set -> wont loop)
                            # Wait for threads to die
                            for thread_pair in threads:
                                thread_pair[0].join()
                        for vm_name, vm_data in vm_info.iteritems():
                            for screen_name in vm_data.get('screen_names', []):
                                logger.debug('Stopping screen {0} on {1}.'.format(screen_name, vm_data['client'].ip))
                                vm_data['client'].run(['screen', '-S', screen_name, '-X', 'quit'])
                            vm_data['screen_names'] = []
        finally:
            cls._adjust_automatic_scrubbing(disable=False)
        assert len(failed_configurations) == 0, 'Certain configuration failed: {0}'.format(' '.join(failed_configurations))

    @classmethod
    def _create_vms(cls, ip, port, connection_messages, vm_info, edge_details, hypervisor_client, timeout=TEST_TIMEOUT):
        listening_queue = Queue.Queue()
        # offload to a thread
        listening_thread, listening_stop_object = ThreadHelper.start_thread_with_event(
            cls._listen_to_address, 'vm_listener',
            args=(ip, port, listening_queue, connection_messages, timeout))
        try:
            for vm_name, vm_data in vm_info.iteritems():
                cls._create_vm(vm_name=vm_name,
                               hypervisor_client=hypervisor_client,
                               disks=vm_data['disks'],
                               networks=vm_data['networks'],
                               edge_details=edge_details,
                               cd_path=vm_data['cd_path'])
            listening_thread.join()  # Wait for all to finish
            vm_ip_info = listening_queue.get()
            for vm_name, vm_data in vm_info.iteritems():
                vm_data.update(vm_ip_info[vm_name])
            assert len(vm_ip_info.keys()) == len(vm_info.keys()), 'Not all VMs started.'
        except:
            if listening_thread.isAlive():
                listening_stop_object[1].set()
            listening_thread.join(timeout=60)
        return vm_info

    @classmethod
    def _prepare_vm_disks(cls, cluster_info, to_be_downed_client, cloud_image_path, cloud_init_loc, api, port, vm_amount,
                          hypervisor_ip, vm_name=VM_NAME, write_amount=AMOUNT_TO_WRITE, logger=LOGGER):
        """
        Will create all necessary vdisks to create the bulk of vms
        :param cluster_info: information about the cluster
        :param to_be_downed_client: SSHClient of the node to be downed
        :param cloud_image_path: path to the cloud image
        :param cloud_init_loc: path to the cloud init script
        :param api: ovsclient instance
        :param vm_amount: amount of vms to test with
        :param vm_name: name prefix for the vms
        :param write_amount: amount of data to read/write
        :param logger: logging instance
        :return: 
        """
        std_2 = cluster_info['storagedrivers']['std2']
        vpool = cluster_info['vpool']
        protocol = std_2.cluster_node_config['network_server_uri'].split(':')[0]

        original_boot_disk_name = None  # Cloning purposes
        original_data_disk_name = None  # Cloning purposes

        connection_messages = []
        vm_info = {}
        volume_amount = 0

        for vm_number in xrange(0, vm_amount):
            filled_number = str(vm_number).zfill(3)
            create_msg = '{0}_{1}'.format(str(uuid.uuid4()), filled_number)
            vm_name = '{0}_{1}'.format(vm_name, filled_number)
            boot_vdisk_name = '{0}_vdisk_boot_{1}'.format(cls.TEST_NAME, filled_number)
            data_vdisk_name = '{0}_vdisk_data_{1}'.format(cls.TEST_NAME, filled_number)
            cd_vdisk_name = '{0}_vdisk_cd_{1}'.format(cls.TEST_NAME, filled_number)
            boot_vdisk_path = '/mnt/{0}/{1}.raw'.format(vpool.name, boot_vdisk_name)
            data_vdisk_path = '/mnt/{0}/{1}.raw'.format(vpool.name, data_vdisk_name)
            cd_vdisk_path = '/mnt/{0}/{1}.raw'.format(vpool.name, cd_vdisk_name)
            if vm_number == 0:
                try:
                    # Create VDISKs
                    ovs_path = 'openvstorage+{0}:{1}:{2}/{3}'.format(protocol, std_2.storage_ip, std_2.ports['edge'], boot_vdisk_name)
                    logger.info('Copying the image to the vdisk with command `qemu-img convert {0}`'.format(ovs_path))
                    to_be_downed_client.run(['qemu-img', 'convert', cloud_image_path, ovs_path])
                except RuntimeError as ex:
                    logger.error('Could not covert the image. Got {0}'.format(str(ex)))
                    raise
                boot_vdisk = VDiskHelper.get_vdisk_by_name('{0}.raw'.format(boot_vdisk_name), vpool.name)
                original_boot_disk_name = boot_vdisk_name
                logger.info('Boot VDisk successfully created.')
                try:
                    data_vdisk = VDiskHelper.get_vdisk_by_guid(VDiskSetup.create_vdisk(data_vdisk_name, vpool.name, write_amount, std_2.storage_ip, api))
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
                boot_vdisk_info = VDiskSetup.create_clone(vdisk_name=original_boot_disk_name,
                                                          vpool_name=vpool.name,
                                                          new_vdisk_name=boot_vdisk_name,
                                                          storagerouter_ip=std_2.storage_ip,
                                                          api=api)
                boot_vdisk = VDiskHelper.get_vdisk_by_guid(boot_vdisk_info['vdisk_guid'])
                data_vdisk_info = VDiskSetup.create_clone(vdisk_name=original_data_disk_name,
                                                          vpool_name=vpool.name,
                                                          new_vdisk_name=data_vdisk_name,
                                                          storagerouter_ip=std_2.storage_ip,
                                                          api=api)
                data_vdisk = VDiskHelper.get_vdisk_by_guid(data_vdisk_info['vdisk_guid'])
            #######################
            # GENERATE CLOUD INIT #
            #######################
            iso_loc = cls._generate_cloud_init(client=to_be_downed_client, convert_script_loc=cloud_init_loc,
                                               port=port, hypervisor_ip=hypervisor_ip, create_msg=create_msg)
            to_be_downed_client.run(['qemu-img', 'convert', iso_loc, 'openvstorage+{0}:{1}:{2}/{3}'.format(protocol,
                                                                                                           std_2.storage_ip,
                                                                                                           std_2.ports['edge'],
                                                                                                           cd_vdisk_name)])
            cd_creation_time = time.time()
            cd_vdisk = None
            while cd_vdisk is None:
                try:
                    cd_vdisk = VDiskHelper.get_vdisk_by_name(cd_vdisk_name, vpool.name)
                except VDiskNotFoundError:
                    logger.warning('Could not fetch the cd vdisk after {0}s.'.format(time.time() - cd_creation_time))
                time.sleep(0.5)

            # Take snapshot to revert back to after every migrate scenario
            data_snapshot_guid = VDiskSetup.create_snapshot('{0}_data'.format(cls.TEST_NAME),
                                                            data_vdisk.devicename,
                                                            vpool.name,
                                                            api,
                                                            consistent=False)
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

        return vm_info, connection_messages, volume_amount

    @classmethod
    def _start_io_polling_threads(cls, volume_bundle, logger=LOGGER):
        """
        Will start the io polling threads
        :param volume_bundle: bundle of volumes {vdiskname: vdisk object}
        :type volume_bundle: dict
        :param logger: logger instance
        :type logger: ovs.log.log_handler.LogHandler
        :return: threads, monitoring_data, r_semaphore
        :rtype: tuple(list, dict, ci.api_lib.helpers.thread.Waiter)
        """
        required_thread_amount = math.ceil(float(len(volume_bundle.keys())) / cls.VDISK_THREAD_LIMIT)  # Amount of threads we will need
        r_semaphore = Waiter(required_thread_amount + 1, auto_reset=True)  # Add another target to let this thread control the semaphore
        threads = []
        monitoring_data = {}
        current_thread_bundle = {'index': 1, 'vdisks': []}
        logger.info('Starting threads.')  # Separate because creating vdisks takes a while, while creating the threads does not
        try:
            for index, (vdisk_name, vdisk_object) in enumerate(volume_bundle.iteritems(), 1):
                vdisks = current_thread_bundle['vdisks']
                volume_number_range = '{0}-{1}'.format(current_thread_bundle['index'], index)
                vdisks.append(vdisk_object)
                if index % cls.VDISK_THREAD_LIMIT == 0 or index == len(volume_bundle.keys()):
                    # New thread bundle
                    monitor_resource = {'general': {'io': [], 'edge_clients': {}}}
                    # noinspection PyTypeChecker
                    for vdisk in vdisks:
                        monitor_resource[vdisk.name] = {
                            'io': {'down': [], 'descending': [], 'rising': [], 'highest': None, 'lowest': None},
                            'edge_clients': {'down': [], 'up': []}}
                    monitoring_data[volume_number_range] = monitor_resource
                    threads.append(ThreadHelper.start_thread_with_event(target=cls._monitor_changes,
                                                                        name='iops_{0}'.format(current_thread_bundle['index']),
                                                                        args=(monitor_resource, vdisks, r_semaphore)))
                    current_thread_bundle['index'] = index + 1
                    current_thread_bundle['vdisks'] = []
        except Exception:
            for thread_pair in threads:  # Attempt to cleanup current inflight threads
                if thread_pair[0].isAlive():
                    thread_pair[1].set()
            while r_semaphore.get_counter() < len(threads):  # Wait for the number of threads we currently have.
                time.sleep(0.05)
            r_semaphore.wait()  # Unlock them to let them stop (the object is set -> wont loop)
            # Wait for threads to die
            for thread_pair in threads:
                thread_pair[0].join()
            raise
        return threads, monitoring_data, r_semaphore

    @classmethod
    def _poll_io(cls, r_semaphore, required_thread_amount, shared_resource, downed_time, disk_amount, timeout=TEST_TIMEOUT,
                 output_files=None, client=None, logger=LOGGER):
        """
        Will start IO polling
        Prerequisite: all threads must have synced up before calling this function
        :param r_semaphore: Reverse semaphore, controlling object to sync the threads with
        :type r_semaphore: ci.api_lib.helpers.thread.Waiter
        :param required_thread_amount: Amount of threads that should be accounted for
        :type required_thread_amount: double / int
        :param shared_resource: Resources shared between all threads
        :type shared_resource: dict
        :param downed_time: Time to start timeout from
        :type downed_time: imt
        :param timeout: Seconds that can elapse before timing out
        :type timeout: int
        :param output_files: OPTIONAL: files that can be checked for errors (fio write data will do this)
        :type output_files: list[str]
        :param client: client that points towards the output files
        :type client: ovs.extensions.generic.sshclient.SSHClient
        :param disk_amount: amount of disks that were checked with
        :type disk_amount: int
        :param logger: logging instance
        :type logger: ovs.log.log_handler.LogHandler
        :return: None
        """
        if output_files is None and client is None:
            raise ValueError('When output files is specified, a compute client is needed.')
        if output_files is None:
            output_files = []
        r_semaphore.wait()  # Start IO polling
        while True:
            if time.time() - downed_time > timeout:
                raise RuntimeError('HA test timed out after {0}s.'.format(timeout))
            if r_semaphore.get_counter() < required_thread_amount:
                time.sleep(1)
                continue
            # Check if any errors occurred - possible due to the nature of the write data with screens
            # If the fio has had an error, it will break and output to the output file
            errors = {}
            for output_file in output_files:
                errors.update(set(client.run('grep -a error {} || true'.format(re.escape(output_file)), allow_insecure=True).split()))
            if len(errors) > 0:
                raise RuntimeError('Fio has reported errors: {} at {}'.format(', '.join(errors), datetime.today().strftime('%Y-%m-%d %H:%M:%S')))
            # Calculate to see if IO is back
            io_volumes = cls._get_all_vdisks_with_io(shared_resource)
            logger.info('Currently got io for {0}: {1}'.format(len(io_volumes), io_volumes))
            if len(io_volumes) == disk_amount:
                logger.info('All threads came through with IO at {0}. Waited {1}s for IO.'.format(
                    datetime.today().strftime('%Y-%m-%d %H:%M:%S'), time.time() - downed_time))
                break
            logger.info('IO has not come through for {0}s.'.format(time.time() - downed_time))
            r_semaphore.wait()  # Unblock waiting threads

    @classmethod
    def _keep_threads_running(cls, r_semaphore, threads, shared_resource, duration=IO_TIME, logger=LOGGER):
        """
        Keeps the threads running for the duration
        :param r_semaphore: Reverse semaphore, controlling object to sync the threads with
        :type r_semaphore: ci.api_lib.helpers.thread.Waiter
        :param threads: list of threads with their closing object
        :type threads: list
        :param shared_resource: Resources shared between all threads
        :type shared_resource: dict
        :param duration: time to keep running
        :type duration: int
        :param logger: logging instance
        :type logger: ovs.log.log_handler.LogHandler
        :return: None
        """
        now = time.time()
        while time.time() - now < duration:
            if r_semaphore.get_counter() < len(threads):
                time.sleep(0.05)
                continue
            if time.time() - now % 1 == 0:
                io_volumes = cls._get_all_vdisks_with_io(shared_resource)
                logger.info('Currently got io for {0} volumes: {1}'.format(len(io_volumes), io_volumes))
            r_semaphore.wait()

    @staticmethod
    def _get_all_edge_clients(monitoring_data):
        output = {}
        for volume_number_range, monitor_resource in monitoring_data.iteritems():
            output.update(monitor_resource['general']['edge_clients'])
        return output

    @staticmethod
    def _get_all_vdisks_with_io(monitoring_data):
        output = []
        for volume_number_range, monitor_resource in monitoring_data.iteritems():
            output.extend(monitor_resource['general']['io'])
        return output

    @staticmethod
    def _adjust_automatic_scrubbing(disable=True):
        """
        Enable or disable the automatic scrubbing
        :param disable: enable of disable the automatic scrubbing
        :type disable: bool
        :return:
        """
        celery_key = 'ovs/framework/scheduling/celery'
        job_key = 'ovs.generic.execute_scrub'

        def change_scheduled_task(task_name, state, disabled=False, cron=None, celery_key=celery_key):
            if not Configuration.exists(celery_key):
                Configuration.set(celery_key, {})
            jobs = Configuration.get(celery_key)
            if state == 'present':
                if disabled:
                    jobs[task_name] = None
                    output = 'task {0}: disabled'.format(task_name)
                else:
                    jobs[task_name] = cron
                    settings = ''
                    for key, value in cron.iteritems():
                        settings += "{0}: {1} ".format(key, value)
                    output = 'task {0}: cron settings {1}'.format(task_name, settings)
            else:
                jobs.pop(task_name, None)
                output = 'task {0}: removed, default settings will be applied.'.format(task_name)
            Configuration.set(celery_key, jobs)
            return output
        if disable is True:
            return change_scheduled_task(job_key, 'present', disabled=True)
        return change_scheduled_task(job_key, 'absent')

    @classmethod
    def _start_snapshotting_threads(cls, volume_bundle, api, args=(), kwargs=None, logger=LOGGER):
        """
        Start the snapshotting threads
        :param volume_bundle: bundle of volumes
        :type volume_bundle: dict
        :param api: api instance
        :param logger: logging instance
        :return: 
        """
        if kwargs is None:
            kwargs = {}
        threads = []
        current_thread_bundle = {'index': 1, 'vdisks': []}
        logger.info('Starting threads.')
        try:
            for index, (vdisk_name, vdisk_object) in enumerate(volume_bundle.iteritems(), 1):
                vdisks = current_thread_bundle['vdisks']
                vdisks.append(vdisk_object)
                if index % cls.VDISK_THREAD_LIMIT == 0 or index == len(volume_bundle.keys()):
                    threads.append(ThreadHelper.start_thread_with_event(target=cls._start_snapshots,
                                                                        name='iops_{0}'.format(current_thread_bundle['index']),
                                                                        args=(vdisks, api,) + args,
                                                                        kwargs=kwargs))
                    current_thread_bundle['index'] = index + 1
                    current_thread_bundle['vdisks'] = []
        except Exception:
            for thread_pair in threads:  # Attempt to cleanup current inflight threads
                if thread_pair[0].isAlive():
                    thread_pair[1].set()
            # Wait for threads to die
            for thread_pair in threads:
                thread_pair[0].join()
            raise
        return threads

    @staticmethod
    def _start_snapshots(vdisks, api, stop_event, interval=60):
        """
        Threading code that creates snapshots every x seconds
        :param stop_event: Threading event that will stop the while loop
        :type stop_event: threading._Event
        :param interval: time between taking the snapshots
        :type interval: int
        :param vdisks: vdisk object
        :type vdisks: list(ovs.dal.hybrids.vdisk.VDISK)
        :return: None
        :rtype: NoneType
        """
        while not stop_event.is_set():
            start = time.time()
            for vdisk in vdisks:
                VDiskSetup.create_snapshot(snapshot_name='{0}_{1}'.format(vdisk.name, datetime.today().strftime('%Y-%m-%d %H:%M:%S')),
                                           vdisk_name=vdisk.devicename,
                                           vpool_name=vdisk.vpool.name,
                                           api=api,
                                           consistent=False,
                                           sticky=False)
            duration = time.time() - start
            time.sleep(0 if duration > interval else interval - duration)

    @staticmethod
    def _trigger_mds_failover(logger=LOGGER):
        logger.debug('Starting the mds triggering.')

    @staticmethod
    def _delete_snapshots(volume_bundle, api, amount_to_delete=3, logger=LOGGER):
        """
        Delete a random number of snapshots
        :return: None
        :rtype: NoneType
        """
        for index, (vdisk_name, vdisk_object) in enumerate(volume_bundle.iteritems(), 1):
            snapshot_list = vdisk_object.snapshots
            if len(snapshot_list) < 3:
                raise RuntimeError('Need at least 3 snapshots to be able to leave the first and last snapshots.')
            snapshots_allowed_to_remove = snapshot_list[1:-1]  # Do not remove first or last
            while amount_to_delete > 0:
                if len(snapshots_allowed_to_remove) == 0:
                    logger.warning('No snapshots left to remove. Needed to remove at least {} more.'.format(amount_to_delete))
                    break
                snapshot = snapshots_allowed_to_remove.pop(random.randrange(0, len(snapshots_allowed_to_remove)))
                logger.debug('Removing snapshot with guid {0}'.format(snapshot['guid']))
                VDiskRemover.remove_snapshot(snapshot['guid'], vdisk_object.name, vdisk_object.vpool.name, api)
                amount_to_delete -= 1

    @staticmethod
    def _run_pg_bench():
        pass

    @staticmethod
    def _start_scrubbing(volume_bundle):
        """
        Starts scrubbing and offloads it to celery
        :param volume_bundle: volume information
        :return: Asynchronous result of a CeleryTask
        :rtype: celery.result.AsyncResult
        """
        vdisk_guids = []
        for vdisk_name, vdisk_object in volume_bundle.iteritems():
            vdisk_guids.append(vdisk_object.guid)
        return GenericController.execute_scrub.delay(vdisk_guids=vdisk_guids)

    @staticmethod
    def _generate_cloud_init(client, convert_script_loc, port, hypervisor_ip, create_msg, path=CLOUD_INIT_DATA['user-data_loc'],
                             config_destination=CLOUD_INIT_DATA['config_dest'], username='test', password='test', root_password='rooter', logger=LOGGER):
        """
        Generates a cloud init file with some userdata in (for a virtual machine)
        The script attached will notify the vm of its creation
        :param client: ovs ssh client for current node
        :type client: ovs.extensions.generic.sshclient.SSHClient
        :param username: username of the user that will be added to the vm
        :type username: str
        :param password: password of the user that will be added to the vm
        :type password: str
        :param root_password: password of root that will be added to the vm
        :type root_password: str
        :param path: path to write out the user data
        :type path: str
        :param config_destination: destination for the full configuration
        :type config_destination: str
        :param convert_script_loc: location to the conversion script
        :type convert_script_loc: str
        :param create_msg: message to send when the vm is done
        :type create_msg: str
        :param logger: logging instance
        :type logger: ovs.log.log_handler.LogHandler
        :return: cloud init destination
        :rtype: str
        """
        # write out user-data
        lines = [
            '#!/bin/bash\n',
            '#user conf',
            'sudo echo "root:{0}" | chpasswd'.format(root_password),
            'sudo useradd {0}'.format(username),
            'sudo echo "{0}:{1}" | chpasswd'.format(username, password),
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
        convert_cmd = [convert_script_loc, '--user-data', path, config_destination]
        try:
            client.run(convert_cmd)
            return config_destination
        except subprocess.CalledProcessError as ex:
            logger.error('Could not generate the cloud init file on {0}. Got {1} during iso conversion.'.format(client.ip, str(ex.output)))
            raise

    @staticmethod
    def _listen_to_address(listening_host, listening_port, queue, connection_messages, timeout, stop_event, logger=LOGGER, vm_name_prefix=VM_NAME):
        """
        Listen for VMs that are ready
        :param listening_host: host to listen on
        :type listening_host: str
        :param listening_port: port to listen on
        :type listening_port: int
        :param queue: queue object to report the answer to
        :type queue: Queue.Queue
        :param connection_messages: messages to listen to
        :type connection_messages: list[str]
        :param timeout: timeout in seconds
        :type timeout: int
        :param stop_event: stop event to abort this thread
        :type stop_event: Threading.Event
        :return: 
        """
        vm_ips_info = {}
        with remote(listening_host, [socket]) as rem:
            listening_socket = rem.socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                # Bind to first available port
                listening_socket.bind((listening_host, listening_port))
                listening_socket.listen(5)
                logger.info('Socket now listening on {0}:{1}, waiting to accept data.'.format(listening_host, listening_port))
                start_time = time.time()
                while len(connection_messages) > 0 and not stop_event.is_set():
                    if time.time() - start_time > timeout:
                        raise RuntimeError('Listening timed out after {0}s'.format(timeout))
                    conn, addr = listening_socket.accept()
                    logger.debug('Connected with {0}:{1}'.format(addr[0], addr[1]))
                    data = conn.recv(1024)
                    logger.debug('Connector said {0}'.format(data))
                    if data in connection_messages:
                        connection_messages.remove(data)
                        vm_number = data.rsplit('_', 1)[-1]
                        vm_name = '{0}_{1}'.format(vm_name_prefix, vm_number)
                        logger.debug('Recognized sender as {0}'.format(vm_name))
                        vm_ips_info[vm_name] = {'ip': addr[0]}
            except Exception as ex:
                logger.error('Error while listening for VM messages.. Got {0}'.format(str(ex)))
                raise
            finally:
                listening_socket.close()
        queue.put(vm_ips_info)

    @staticmethod
    def _get_free_port(listener_ip, logger=LOGGER):
        """
        Returns a free port
        :param listener_ip: ip to listen on
        :type listener_ip: str
        :param logger: logging instance
        :type logger: ovs.log.log_handler.LogHandler
        :return: port number
        :rtype: int
        """
        with remote(listener_ip, [socket]) as rem:
            listening_socket = rem.socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                # Bind to first available port
                listening_socket.bind(('', 0))
                port = listening_socket.getsockname()[1]
                return port
            except socket.error as ex:
                logger.error('Could not bind the socket. Got {0}'.format(str(ex)))
                raise
            finally:
                try:
                    listening_socket.close()
                except:
                    pass

    @staticmethod
    def _create_vm(hypervisor_client, disks, networks, edge_details, cd_path, vcpus=VM_VCPUS, ram=VM_VRAM, vm_name=VM_NAME, os_type=VM_OS_TYPE, logger=LOGGER):
        """
        Creates and wait for the VM to be fully connected
        :param hypervisor_client: hypervisor client instance
        :param disks: disk info
        :param networks: network info
        :param edge_details: edge info
        :param cd_path: cd info
        :param vcpus: number of virtual cpus
        :param ram: amount of ram
        :param vm_name: name of the vm
        :param os_type: type of the os
        :param logger: logging instance
        :return: None
        """
        edge_hostname = edge_details['hostname']
        edge_port = edge_details['port']
        logger.info('Creating VM `{0}`'.format(vm_name))
        hypervisor_client.sdk.create_vm(vm_name,
                                        vcpus=vcpus,
                                        ram=ram,
                                        cdrom_iso=cd_path,
                                        disks=disks,
                                        networks=networks,
                                        ovs_vm=True,
                                        hostname=edge_hostname,
                                        edge_port=edge_port,
                                        start=True,
                                        os_type=os_type)
        logger.info('Created VM `{0}`!'.format(vm_name))

    @staticmethod
    def _cleanup_vm(hypervisor, vmid, blocking=True, logger=LOGGER):
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
            logger.error(str(ex))
            if blocking is True:
                raise
            else:
                pass

    @staticmethod
    def _stop_vm(hypervisor, vmid, blocking=True, logger=LOGGER):
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
            logger.error(str(ex))
            if blocking is True:
                raise
            else:
                pass

    @staticmethod
    def _start_vm(hypervisor, vmid, blocking=True, logger=LOGGER):
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
            logger.error(str(ex))
            if blocking is True:
                raise
            else:
                pass

    @staticmethod
    def _monitor_changes(results, vdisks, r_semaphore, stop_event, refresh_rate=IO_REFRESH_RATE, logger=LOGGER):
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
            logger.debug('IO for {0} at {1}. Call took {2}'.format(has_io, now, duration))
            logger.debug('Edge clients for {0} at {1}. Call took {2}'.format(edge_info, now, duration))
            general_info['in_progress'] = False
            time.sleep(0 if duration > refresh_rate else refresh_rate - duration)
            r_semaphore.wait(30 * 60)  # Let each thread wait for another

    @classmethod
    def _write_data(cls, client, cmd_type, configuration, edge_configuration=None, screen=True,
                    data_to_write=AMOUNT_TO_WRITE, file_locations=None, ee_info=None, logger=LOGGER):
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
        :return: list of screen names (empty if screen is False), list of output files
        :rtype: tuple(list, list)
        """
        bs = '4k'
        iodepth = 32
        fio_output_format = 'json'
        write_size = data_to_write
        cmds = []
        screen_names = []
        output_files = []
        output_directory = '/tmp/{0}'.format(cls.TEST_NAME)
        client.dir_create(output_directory)
        try:
            os.makedirs(output_directory)
        except OSError as exception:
            if exception.errno != errno.EEXIST:
                raise
        if cmd_type != 'fio':
            raise ValueError('{0} is not supported for writing data.'.format(cmd_type))
        config = ['--iodepth={0}'.format(iodepth), '--rw=randrw', '--bs={0}'.format(bs), '--direct=1',
                  '--rwmixread={0}'.format(configuration[0]), '--rwmixwrite={0}'.format(configuration[1]),
                  '--randrepeat=0']
        if edge_configuration:
            fio_vdisk_limit = cls.FIO_VDISK_LIMIT
            volumes = edge_configuration['volumename']
            fio_amount = int(math.ceil(float(len(volumes)) / fio_vdisk_limit))  # Amount of fio commands to prep
            for fio_nr in xrange(0, fio_amount):
                vols = volumes[fio_nr * fio_vdisk_limit: (fio_nr + 1) * fio_vdisk_limit]  # Subset the volume list
                additional_settings = ['ulimit -n 4096;']  # Volumedriver envir params
                # Append edge fio stuff
                additional_config = ['--ioengine=openvstorage', '--hostname={0}'.format(edge_configuration['hostname']),
                                     '--port={0}'.format(edge_configuration['port']),
                                     '--protocol={0}'.format(edge_configuration['protocol']),
                                     '--enable_ha=1', '--group_reporting=1']
                if ee_info is not None:
                    additional_config.extend(
                        ['--username={0}'.format(ee_info['username']), '--password={0}'.format(ee_info['password'])])
                verify_config = ['--verify=crc32c-intel', '--verifysort=1', '--verify_fatal=1',
                                 '--verify_backlog=1000000']
                output_file = '{0}/fio_{1}-{2}'.format(output_directory, fio_nr, len(vols))
                output_files.append(output_file)
                output_config = ['--output={0}'.format(output_file), '--output-format={0}'.format(fio_output_format)]
                # Generate test names for each volume
                fio_jobs = []
                for index, volume in enumerate(vols):
                    fio_jobs.append('--name=test{0}'.format(index))
                    fio_jobs.append('--volumename={0}'.format(volume))
                cmds.append(additional_settings + [edge_configuration[
                                                       'fio_bin_location']] + config + additional_config + verify_config + output_config + fio_jobs)
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
                cmds[index] = ['screen', '-S', screen_name, '-dm', 'bash', '-c',
                               'while {0}; do :; done; exec bash'.format(' '.join(cmd))]
                screen_names.append(screen_name)
        for cmd in cmds:
            logger.debug('Writing data with: {0}'.format(' '.join(cmd)))
            client.run(cmd)
        return screen_names, output_files

    @staticmethod
    def _validate(dal_values, monitoring_data):
        pass


def run(blocked=False):
    """
    Run a test
    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return RegressionTester().main(blocked)

if __name__ == '__main__':
    run()
