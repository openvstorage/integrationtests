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
import random
import time

from ci.api_lib.helpers.api import OVSClient
from ci.api_lib.helpers.hypervisor.hypervisor import HypervisorFactory
from ci.api_lib.helpers.network import NetworkHelper
from ci.api_lib.helpers.storagerouter import StoragerouterHelper
from ci.api_lib.helpers.system import SystemHelper
from ci.api_lib.helpers.thread import ThreadHelper
from ci.api_lib.helpers.vpool import VPoolHelper
from ci.api_lib.remove.vdisk import VDiskRemover
from ci.api_lib.setup.vdisk import VDiskSetup
from ci.main import CONFIG_LOC
from ci.main import SETTINGS_LOC
from ci.scenario_helpers.data_writing import DataWriter
from ci.scenario_helpers.threading_handlers import ThreadingHandler
from ci.scenario_helpers.vm_handler import VMHandler
from ovs.dal.lists.storagerouterlist import StorageRouterList
from ovs.extensions.generic.configuration import Configuration
from ovs.extensions.generic.remote import remote
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.packages.package import PackageManager
from ovs.extensions.services.service import ServiceManager
from ovs.lib.generic import GenericController
from ovs.lib.mdsservice import MDSServiceController
from ovs.log.log_handler import LogHandler


class RegressionTester(object):

    CASE_TYPE = 'FUNCTIONAL'
    TEST_NAME = 'ci_scenario_edge_test'
    LOGGER = LogHandler.get(source='scenario', name=TEST_NAME)

    IO_TIME = 2 * 60  # Time to do IO for
    TEST_TIMEOUT = 300
    VM_CONNECTING_TIMEOUT = 5

    AMOUNT_TO_WRITE = 10 * 1024 ** 3

    VM_NAME = 'mds-regression'
    VM_OS_TYPE = 'ubuntu16.04'

    VM_USERNAME = 'root'  # vm credentials & details
    VM_PASSWORD = 'rooter'
    VM_VCPUS = 4
    VM_VRAM = 1024  # In MB

    VM_WAIT_TIME = 300  # wait time before timing out on the vm install in seconds

    # DATA_TEST_CASES = [(0, 100), (30, 70), (40, 60), (50, 50), (70, 30), (100, 0)]  # read write patterns to test (read, write)
    DATA_TEST_CASES = [(80, 20)]
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
        listening_port = NetworkHelper.get_free_port(compute_client.ip)

        source_storagedriver = cluster_info['storagedrivers']['source']
        protocol = source_storagedriver.cluster_node_config['network_server_uri'].split(':')[0]
        edge_details = {'port': source_storagedriver.ports['edge'], 'hostname': source_storagedriver.storage_ip, 'protocol': protocol}

        computenode_hypervisor = HypervisorFactory.get(compute_client.ip,
                                                       hypervisor_info['user'],
                                                       hypervisor_info['password'],
                                                       hypervisor_info['type'])
        vm_info, connection_messages, volume_amount = VMHandler.prepare_vm_disks(source_storagedriver=source_storagedriver,
                                                                                 cloud_image_path=cloud_image_path,
                                                                                 cloud_init_loc=cloud_init_loc,
                                                                                 api=api,
                                                                                 vm_amount=vm_amount,
                                                                                 port=listening_port,
                                                                                 hypervisor_ip=compute_client.ip,
                                                                                 vm_name=cls.VM_NAME,
                                                                                 write_amount=cls.AMOUNT_TO_WRITE * 20)
        vm_info = VMHandler.create_vms(ip=compute_client.ip,
                                       port=listening_port,
                                       connection_messages=connection_messages,
                                       vm_info=vm_info,
                                       edge_details=edge_details,
                                       hypervisor_client=computenode_hypervisor,
                                       timeout=cls.TEST_TIMEOUT)
        # # @TODO: remove this section as it just rebuilds for faster testing
        # from ci.api_lib.helpers.vdisk import VDiskHelper
        # vp = VPoolHelper.get_vpool_by_name('mysyncvpool')
        # available_storagedrivers = [storagedriver for storagedriver in vp.storagedrivers]
        # destination_storagedriver = [std for std in available_storagedrivers if std.storage_ip == '10.100.188.32'][0]
        # source_storagedriver = [std for std in available_storagedrivers if std.storage_ip == '10.100.188.33'][0]
        # str_1 = destination_storagedriver.storagerouter  # Will act as volumedriver node
        # str_2 = source_storagedriver.storagerouter  # Will act as volumedriver node
        # str_3 = [storagerouter for storagerouter in StoragerouterHelper.get_storagerouters() if
        #          storagerouter.guid not in [str_1.guid, str_2.guid]][0]  # Will act as compute node
        # compute_client = SSHClient(str_3, username='root')
        # cluster_info = {'storagerouters': {'str3': str_3, 'str2': str_2, 'str1': str_1}, 'storagedrivers': {'destination': destination_storagedriver, 'source': source_storagedriver}, 'vpool': vp}
        # volume_amount = 3
        # vdisks = [VDiskHelper.get_vdisk_by_guid('61c9e92a-df52-4026-938b-e3e3d8da925d'),  # boot
        #           VDiskHelper.get_vdisk_by_guid('a2f5c5a5-d894-4ee1-b687-adf9f0a6b2ea'),  # cd
        #           VDiskHelper.get_vdisk_by_guid('7e091881-3da3-4a59-bece-78f01d2f4fc3')]  # data
        # vm_info = {'HA-test_000': {'vdisks': vdisks,
        #                            'created': False,
        #                            'data_snapshot_guid': u'156fe4b0-2a85-4cfe-b74b-c82662a79c89',
        #                            'create_msg': 'f1143bd1-7eb0-4115-b9d7-ff1c1bfd8c07_HA-test-000',
        #                            'ip': '192.168.122.239',
        #                            'disks': [{'mountpoint': '/mnt/mysyncvpool/HA-test-000_vdisk_boot_000'},
        #                                      {'mountpoint': '/mnt/mysyncvpool/HA-test-000_vdisk_data_000.raw'}],
        #                            'cd_path': '/mnt/mysyncvpool/HA-test-000_vdisk_cd_000.raw',
        #                            'networks': [{'model': 'e1000', 'mac': 'RANDOM', 'network': 'default'}]}}
        cls.run_test(cluster_info=cluster_info,
                     compute_client=compute_client,
                     is_ee=is_ee,
                     disk_amount=volume_amount,
                     vm_info=vm_info,
                     api=api)

    @classmethod
    def setup(cls, required_packages_cloud_init=REQUIRED_PACKAGE_CLOUD_INIT, required_packages_hypervisor=REQUIRED_PACKAGES_HYPERVISOR,
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
        destination_storagedriver = available_storagedrivers.pop(random.randrange(len(available_storagedrivers)))
        source_storagedriver = available_storagedrivers.pop(random.randrange(len(available_storagedrivers)))
        str_1 = destination_storagedriver.storagerouter  # Will act as volumedriver node
        str_2 = source_storagedriver.storagerouter  # Will act as volumedriver node
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
        destination_storagedriver = [storagedriver for storagedriver in str_1.storagedrivers if storagedriver.vpool_guid == vpool.guid][0]
        source_storagedriver = [storagedriver for storagedriver in str_2.storagedrivers if storagedriver.vpool_guid == vpool.guid][0]
        logger.info('Chosen destination storagedriver is: {0}'.format(destination_storagedriver.storage_ip))
        logger.info('Chosen source storagedriver is: {0}'.format(source_storagedriver.storage_ip))

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
                        'storagedrivers': {'destination': destination_storagedriver, 'source': source_storagedriver},
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
        destination_storagedriver = cluster_info['storagedrivers']['destination']
        source_storagedriver = cluster_info['storagedrivers']['source']

        # Cache to validate properties
        values_to_check = {
            'source_std': source_storagedriver.serialize(),
            'target_std': destination_storagedriver.serialize()
        }
        # Prep VM listener #
        failed_configurations = []
        ee_info = None
        if is_ee is True:
            # @ Todo create user instead
            ee_info = {'username': 'root', 'password': 'rooter'}

        # Extract vdisk info from vm_info - only get the data ones
        vdisk_info = {}
        for vm_name, vm_object in vm_info.iteritems():
            for vdisk in vm_object['vdisks']:
                if 'vdisk_data' in vdisk.name:
                    vdisk_info.update({vdisk.name: vdisk})
        try:
            cls._adjust_automatic_scrubbing(disable=True)
            with remote(str_3.ip, [SSHClient]) as rem:
                for test_run_nr, configuration in enumerate(data_test_cases):
                    threads = {'evented': {'io': {'pairs': [], 'r_semaphore': None},
                                           'snapshots': {'pairs': [], 'r_semaphore': None}}}
                    output_files = []
                    safety_set = False
                    mds_triggered = False
                    try:
                        logger.info('Starting the following configuration: {0}'.format(configuration))
                        if test_run_nr == 0:  # Build reusable ssh clients
                            for vm_name, vm_data in vm_info.iteritems():
                                vm_client = rem.SSHClient(vm_data['ip'], vm_username, vm_password)
                                vm_client.file_create('/mnt/data/{0}.raw'.format(vm_data['create_msg']))
                                vm_data['client'] = vm_client
                        else:
                            for vm_name, vm_data in vm_info.iteritems():
                                vm_data['client'].run(['rm', '/mnt/data/{0}.raw'.format(vm_data['create_msg'])])
                        cls._set_mds_safety(1, checkup=True)  # Set the safety to trigger the mds
                        safety_set = True
                        io_thread_pairs, monitoring_data, io_r_semaphore = ThreadingHandler.start_io_polling_threads(volume_bundle=vdisk_info)
                        threads['evented']['io']['pairs'] = io_thread_pairs
                        threads['evented']['io']['r_semaphore'] = io_r_semaphore
                        # @todo snapshot every minute
                        threads['evented']['snapshots']['pairs'] = ThreadingHandler.start_snapshotting_threads(volume_bundle=vdisk_info, api=api, kwargs={'interval': 15})
                        for vm_name, vm_data in vm_info.iteritems():  # Write data
                            screen_names, output_files = DataWriter.write_data(client=vm_data['client'],
                                                                               cmd_type='fio',
                                                                               configuration=configuration,
                                                                               file_locations=['/mnt/data/{0}.raw'.format(vm_data['create_msg'])],
                                                                               ee_info=ee_info,
                                                                               data_to_write=cls.AMOUNT_TO_WRITE)
                            vm_data['screen_names'] = screen_names
                        logger.info('Doing IO for {0}s before bringing down the node.'.format(cls.IO_TIME))
                        ThreadingHandler.keep_threads_running(r_semaphore=threads['evented']['io']['r_semaphore'],
                                                              threads=threads['evented']['io']['pairs'],
                                                              shared_resource=monitoring_data,
                                                              duration=cls.IO_TIME / 2)
                        ThreadHelper.stop_evented_threads(threads['evented']['snapshots']['pairs'],
                                                          threads['evented']['snapshots']['r_semaphore'])  # Stop snapshotting
                        cls._delete_snapshots(volume_bundle=vdisk_info, api=api)
                        scrubbing_result = cls._start_scrubbing(volume_bundle=vdisk_info)  # Starting to scrub, offloaded to celery
                        cls._trigger_mds_issue(vdisk_info, destination_storagedriver.storagerouter.guid, api)  # Trigger mds failover while scrubber is busy
                        mds_triggered = True
                        # Do some monitoring further for 60s
                        ThreadingHandler.keep_threads_running(r_semaphore=threads['evented']['io']['r_semaphore'],
                                                              threads=threads['evented']['io']['pairs'],
                                                              shared_resource=monitoring_data,
                                                              duration=cls.IO_TIME / 2)
                        time.sleep(cls.IO_REFRESH_RATE * 2)
                        downed_time = time.time()
                        # Start IO polling to verify nothing went down
                        ThreadingHandler.poll_io(r_semaphore=threads['evented']['io']['r_semaphore'],
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
                        for thread_category, thread_collection in threads['evented'].iteritems():
                            ThreadHelper.stop_evented_threads(thread_collection['pairs'], thread_collection['r_semaphore'])
                        for vm_name, vm_data in vm_info.iteritems():
                            for screen_name in vm_data.get('screen_names', []):
                                logger.debug('Stopping screen {0} on {1}.'.format(screen_name, vm_data['client'].ip))
                                vm_data['client'].run(['screen', '-S', screen_name, '-X', 'quit'])
                            vm_data['screen_names'] = []
                        if safety_set is True:
                            cls._set_mds_safety(len(StorageRouterList.get_masters()), checkup=True)
                        if mds_triggered is True:  # Vdisks got moved at this point
                            for vdisk_name, vdisk_object in vdisk_info.iteritems():
                                VDiskSetup.move_vdisk(vdisk_guid=vdisk_object.guid,
                                                      target_storagerouter_guid=source_storagedriver.storagerouter.guid,
                                                      api=api)
        finally:
            cls._adjust_automatic_scrubbing(disable=False)
        assert len(failed_configurations) == 0, 'Certain configuration failed: {0}'.format(' '.join(failed_configurations))

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
            service_name = 'scheduled-tasks'
            for storagerouter in StorageRouterList.get_masters():
                client = SSHClient(storagerouter, username='root')
                ServiceManager.restart_service(service_name, client=client)
            return output
        if disable is True:
            return change_scheduled_task(job_key, 'present', disabled=True)
        return change_scheduled_task(job_key, 'absent')

    @staticmethod
    def _set_mds_safety(safety=None, checkup=False, logger=LOGGER):
        if safety is None:
            safety = len(StoragerouterHelper.get_storagerouters())
        if safety <= 0:
            raise ValueError('Safety should be at least 1.')
        logger.debug('Setting the safety to {} and {} checkup'.format(safety, 'will' if checkup is True else 'false'))
        storagedriver_config = Configuration.get('/ovs/framework/storagedriver')
        current_safety = storagedriver_config
        current_safety['mds_safety'] = safety
        Configuration.set('/ovs/framework/storagedriver', current_safety)
        if checkup is True:
            MDSServiceController.mds_checkup()

    @classmethod
    def _trigger_mds_issue(cls, volume_bundle, target_storagerouter_guid, api, logger=LOGGER):
        """
        voldrv A, voldrv B, volume X op A
        ensure_safety lopen op X, die gaat master op A en slave op B hebben -> done on create
        dan ga je manueel tegen de voldrv zeggen dat X enkel nog A heeft als MDS
        B blijft dan slave, en blijft catchuppe
        dan scrub je X, en die raken niet applied op B
        want 'm kent die eigenlijk niet
        en dan - da's hier enigzinds nen educated guess - configureer je B manueel terug als slave
        doe je nen move of nen failover beter gezegd (zie hierboven hoe te doen)
        dan gaat 'm opeens B als master gebruiken maar die heeft geen scrub results applied
        """
        logger.debug('Starting the mds triggering.')
        cls._set_mds_safety(2, checkup=True)  # Will trigger mds checkup which should create a slave again
        # Move the volume to set the slave as the master
        for vdisk_name, vdisk_object in volume_bundle.iteritems():
            VDiskSetup.move_vdisk(vdisk_guid=vdisk_object.guid, target_storagerouter_guid=target_storagerouter_guid, api=api)

        # Manually fool the voldriver into thinking it only has the master left
        # the other volumedriver remains slave en keeps catching up
        # Scrubbing wont be applied to B
        # Reconfigure B as slave
        # move to vdisk to B so B is master but B does not have scrub results

        # The case above is the potentially the same as settingthe safety to 1 after creation, mds checkup and then setting it to 2, mds checkup
        # Set the mds safety back to 2

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
