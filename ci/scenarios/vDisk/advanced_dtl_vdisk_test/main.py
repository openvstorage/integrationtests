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
import time
import socket
import subprocess
from libvirt import libvirtError
from ci.api_lib.helpers.api import OVSClient
from ci.api_lib.helpers.domain import DomainHelper
from ci.api_lib.helpers.hypervisor.hypervisor import HypervisorFactory
from ci.api_lib.helpers.init_manager import InitManager
from ci.api_lib.helpers.storagedriver import StoragedriverHelper
from ci.api_lib.helpers.storagerouter import StoragerouterHelper
from ci.api_lib.helpers.system import SystemHelper
from ci.api_lib.helpers.vpool import VPoolHelper
from ci.api_lib.helpers.vdisk import VDiskHelper
from ci.api_lib.remove.vdisk import VDiskRemover
from ci.autotests import gather_results
from ci.main import CONFIG_LOC
from ci.main import SETTINGS_LOC
from ovs.extensions.generic.remote import remote
from ovs.extensions.generic.sshclient import SSHClient
from ovs.log.log_handler import LogHandler


class AdvancedDTLTester(object):
    """
    Exercice HA with a VM via edge & KVM

    Required packages: qemu-kvm libvirt0 python-libvirt virtinst genisoimage
    Required commands after ovs installation and required packages: usermod -a -G ovs libvirt-qemu

    For this test the regular domain can only be 1 choice
    """

    CASE_TYPE = 'FUNCTIONAL'
    TEST_NAME = 'ci_scenario_advanced_dtl_test'
    LOGGER = LogHandler.get(source='scenario', name=TEST_NAME)
    SLEEP_TIME = 60
    SLEEP_TIME_BEFORE_SHUTDOWN = 30
    VM_CONNECTING_TIMEOUT = 5
    VM_CREATION_MESSAGE = 'I am created!'
    REQUIRED_PACKAGES = ['qemu-kvm', 'libvirt0', 'python-libvirt', 'virtinst', 'genisoimage']
    VM_NAME = 'DTL-test'
    VM_WAIT_TIME = 300  # wait time before timing out on the vm install in seconds
    START_PARENT_TIMEOUT = 30
    CLOUD_INIT_DATA = {
        'script_loc': 'https://raw.githubusercontent.com/kinvaris/cloud-init/master/create-config-drive',
        'script_dest': '/tmp/cloud_init_script.sh',
        'user-data_loc': '/tmp/user-data-migrate-test',
        'config_dest': '/tmp/cloud-init-config-migrate-test'
    }
    AMOUNT_TO_WRITE = 10 * 1024 ** 3  # 10 GB
    IO_PATTERN = (100, 0)  # read, write
    BLOCK_SIZE = 4  # in kb
    IO_DEPTH = 4
    with open(CONFIG_LOC, 'r') as JSON_CONFIG:
        SETUP_CFG = json.load(JSON_CONFIG)

    # collect details about parent hypervisor
    PARENT_HYPERVISOR_INFO = SETUP_CFG['ci']['hypervisor']

    # timeout between checks
    MIGRATE_TIMEOUT = 30
    MIGRATE_CHECKS = 10

    # validate dtl
    VM_FILENAME = '/root/dtl_file'
    VM_RANDOM = '/root/random_file'

    # vm credentials & details
    VM_USERNAME = 'root'
    VM_PASSWORD = 'rooter'
    VM_VCPUS = 1
    VM_VRAM = 512  # In MB

    # hypervisor details
    HYPERVISOR_TYPE = SETUP_CFG['ci']['local_hypervisor']['type']
    HYPERVISOR_USER = SETUP_CFG['ci']['local_hypervisor']['user']
    HYPERVISOR_PASSWORD = SETUP_CFG['ci']['local_hypervisor']['password']

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
        return AdvancedDTLTester._execute_test()

    @staticmethod
    def _execute_test():
        """
        Execute the live migration test
        """

        AdvancedDTLTester.LOGGER.info('Starting advanced DTL autotests test!')

        #################
        # PREREQUISITES #
        #################

        with open(CONFIG_LOC, 'r') as config_file:
            config = json.load(config_file)

        api = OVSClient(
            config['ci']['grid_ip'],
            config['ci']['user']['api']['username'],
            config['ci']['user']['api']['password']
        )

        with open(SETTINGS_LOC, 'r') as JSON_SETTINGS:
            settings = json.load(JSON_SETTINGS)

        storagerouter = None  # Will act as volumedriver node
        compute = None  # Will act as compute node

        for node_ip, node_details in AdvancedDTLTester.PARENT_HYPERVISOR_INFO['vms'].iteritems():
            if node_details['role'] == "VOLDRV" and storagerouter is None:
                storagerouter = StoragerouterHelper.get_storagerouter_by_ip(node_ip)
                AdvancedDTLTester.LOGGER.info('Node with IP `{0}` has been selected as VOLDRV node'
                                              .format(node_ip))
            elif node_details['role'] == "COMPUTE" and compute is None:
                compute = StoragerouterHelper.get_storagerouter_by_ip(node_ip)
                AdvancedDTLTester.LOGGER.info('Node with IP `{0}` has been selected as COMPUTE node'
                                              .format(node_ip))
            else:
                AdvancedDTLTester.LOGGER.info('Node with IP `{0}` is not required or has a invalid role: {1}'
                                              .format(node_ip, node_details['role']))

        # fetch the storagedrivers in the domain where the VOLDRV node is and sort them per vpool
        vpools = {}
        for std in DomainHelper.get_storagedrivers_in_same_domain(domain_guid=storagerouter.regular_domains[0]):
            if std.vpool.name not in vpools:
                vpools[std.vpool.name] = [std]
            else:
                vpools[std.vpool.name].append(std)

        # fetch the vpool with at least 2 storagedrivers & DTL sync
        filtered_vpools = [VPoolHelper.get_vpool_by_name(vpool_name=vpool_name)
                           for vpool_name, storagedrivers in vpools.iteritems() if len(storagedrivers) >= 2 and
                           VPoolHelper.get_vpool_by_name(vpool_name=vpool_name).configuration['dtl_mode'] ==
                           VPoolHelper.DtlStatus.SYNC]
        assert len(filtered_vpools) != 0, "We need at least a vPool with 2 storagedrivers of a vPool in the SAME domain"

        # just pick the first vpool you find :)
        vpool = filtered_vpools[0]
        AdvancedDTLTester.LOGGER.info('vPool `{0}` has been chosen'.format(vpool.name))

        # choose the storagedriver
        storagedriver = [storagedriver for storagedriver in storagerouter.storagedrivers
                         if storagedriver.vpool_guid == vpool.guid][0]
        AdvancedDTLTester.LOGGER.info('Chosen source storagedriver / to be downed node is: {0}'
                                      .format(storagedriver.storage_ip))

        # build ssh client
        to_be_downed_client = SSHClient(storagerouter.ip, username='root')

        # check if enough images available
        images = settings['images']
        assert len(images) >= 1, 'Not enough images in `{0}`'.format(SETTINGS_LOC)

        # check if image exists
        image_path = images[0]
        assert to_be_downed_client.file_exists(image_path), 'Image `{0}` does not exists on `{1}`!'\
                                                            .format(images[0], to_be_downed_client.ip)

        # Get the cloud init file
        cloud_init_loc = AdvancedDTLTester.CLOUD_INIT_DATA['script_dest']
        to_be_downed_client.run(['wget', AdvancedDTLTester.CLOUD_INIT_DATA['script_loc'], '-O', cloud_init_loc])
        to_be_downed_client.file_chmod(cloud_init_loc, 755)
        assert to_be_downed_client.file_exists(cloud_init_loc), 'Could not fetch the cloud init script on {0}'\
            .format(compute.ip)

        # Check if there are missing packages for the hypervisor
        missing_packages = SystemHelper.get_missing_packages(compute.ip, AdvancedDTLTester.REQUIRED_PACKAGES)
        assert len(missing_packages) == 0, 'Missing {0} package(s) on `{1}`: {2}'.format(len(missing_packages),
                                                                                         compute.ip, missing_packages)
        cluster_info = {
            'storagerouters': {'source_str': storagerouter, 'compute': compute},
            'storagedrivers': {'source_std': storagedriver}
        }

        AdvancedDTLTester.test_ha_vm(to_be_downed_client=to_be_downed_client, image_path=image_path, vpool=vpool,
                                     cloud_init_loc=cloud_init_loc, cluster_info=cluster_info)

        AdvancedDTLTester.LOGGER.info('Finished advanced DTL autotests test!')

    @staticmethod
    def test_ha_vm(to_be_downed_client, image_path, vpool, cloud_init_loc, cluster_info):
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
        :return: None
        :rtype: NoneType
        """
        source_str = cluster_info['storagerouters']['source_str']
        compute = cluster_info['storagerouters']['compute']
        source_std = cluster_info['storagedrivers']['source_std']

        # setup hypervisor details
        parent_hypervisor = HypervisorFactory.get(AdvancedDTLTester.PARENT_HYPERVISOR_INFO['ip'],
                                                  AdvancedDTLTester.PARENT_HYPERVISOR_INFO['user'],
                                                  AdvancedDTLTester.PARENT_HYPERVISOR_INFO['password'],
                                                  AdvancedDTLTester.PARENT_HYPERVISOR_INFO['type'])
        computenode_hypervisor = HypervisorFactory.get(compute.ip, AdvancedDTLTester.HYPERVISOR_USER,
                                                       AdvancedDTLTester.HYPERVISOR_PASSWORD,
                                                       AdvancedDTLTester.HYPERVISOR_TYPE)

        ##############
        # SETUP TEST_NAME #
        ##############

        # Cache to validate properties
        values_to_check = {
            'source_std': source_std.serialize()
        }

        # Create a new vdisk to test
        boot_vdisk_name = '{0}_vdisk01'.format(AdvancedDTLTester.TEST_NAME)
        boot_vdisk_path = '/mnt/{0}/{1}.raw'.format(vpool.name, boot_vdisk_name)
        protocol = source_std.cluster_node_config['network_server_uri'].split(':')[0]
        disks = [{'mountpoint': boot_vdisk_path}]
        networks = [{'network': 'default', 'mac': 'RANDOM', 'model': 'e1000'}]

        # Milestones through the code
        cloud_init_created = False
        vm_created = False
        try:
            #################
            # Create VDISKS #
            #################
            try:
                ovs_path = 'openvstorage+{0}:{1}:{2}/{3}'.format(protocol, source_std.storage_ip, source_std.ports['edge'],
                                                                 boot_vdisk_name)
                AdvancedDTLTester.LOGGER.info('Copying the image to the vdisk with command `qemu-img convert {0}`'
                                              .format(ovs_path))
                to_be_downed_client.run(['qemu-img', 'convert', image_path, ovs_path])
            except RuntimeError as ex:
                AdvancedDTLTester.LOGGER.error('Could not covert the image. Got {0}'.format(str(ex)))
                raise

            boot_vdisk = VDiskHelper.get_vdisk_by_name(boot_vdisk_name + '.raw', vpool.name)
            AdvancedDTLTester.LOGGER.info('VDisk `{0}` successfully created!'.format(boot_vdisk.name))

            ####################
            # Prep VM listener #
            ####################
            listening_port = AdvancedDTLTester._get_free_port(compute.ip)

            #######################
            # GENERATE CLOUD INIT #
            #######################
            # iso_loc = "/tmp/cloud-init-config-migrate-test"
            iso_loc = AdvancedDTLTester._generate_cloud_init(client=to_be_downed_client,
                                                             convert_script_loc=cloud_init_loc,
                                                             port=listening_port, hypervisor_ip=compute.ip)
            to_be_downed_client.run(['qemu-img', 'convert', iso_loc, 'openvstorage+{0}:{1}:{2}/{3}'
                                    .format(protocol, source_std.storage_ip, source_std.ports['edge'],
                                            iso_loc.rsplit('/', 1)[1])])
            cd_path = '/mnt/{0}/{1}.raw'.format(vpool.name, iso_loc.rsplit('/', 1)[1])
            cloud_init_created = True

            ##############
            # START TEST_NAME #
            ##############
            try:
                #############
                # CREATE VM #
                #############
                # Get the current state of the vdisk to compare later
                values_to_check['vdisk'] = boot_vdisk.serialize()
                edge_details = {'port': source_std.ports['edge'], 'hostname': source_std.storage_ip, 'protocol': protocol}
                vm_ip = AdvancedDTLTester._create_vm(compute.ip, disks, networks, edge_details, cd_path, listening_port)
                # vm_ip = "192.168.122.179"
                vm_created = True
                if vm_ip is None or vm_ip not in computenode_hypervisor.\
                        sdk.get_guest_ip_addresses(AdvancedDTLTester.VM_NAME):
                    raise RuntimeError('The VM did not connect to the source_hypervisor. '
                                       'Hypervisor has leased {0} and got {1}'
                                       .format(computenode_hypervisor.sdk.
                                               get_guest_ip_addresses(AdvancedDTLTester.VM_NAME), vm_ip))

                #######################
                # CONNECT TO VMACHINE #
                #######################
                with remote(compute.ip, [SSHClient]) as rem:
                    vm_client = rem.SSHClient(vm_ip, AdvancedDTLTester.VM_USERNAME, AdvancedDTLTester.VM_PASSWORD)
                    AdvancedDTLTester.LOGGER.info('Connection was established with the VM.')
                    # install fio on the VM
                    AdvancedDTLTester.LOGGER.info('Installing fio on the VM.')
                    try:
                        vm_client.run(['apt-get', 'install', 'fio', '-y', '--force-yes'])
                        AdvancedDTLTester.LOGGER.info('Installed fio on the VM!')
                    except subprocess.CalledProcessError:
                        AdvancedDTLTester.LOGGER.info('Fio is already installed!')

                    try:
                        ###########################################
                        # load dd, md5sum, screen & fio in memory #
                        ###########################################
                        vm_client = rem.SSHClient(vm_ip, AdvancedDTLTester.VM_USERNAME, AdvancedDTLTester.VM_PASSWORD)
                        try:
                            vm_client.run('dd if=/dev/urandom of={0} bs=1M count=2'
                                          .format(AdvancedDTLTester.VM_RANDOM).split())
                            vm_client.run('md5sum {0}'.format(AdvancedDTLTester.VM_RANDOM).split())
                            vm_client.run('screen -S {0} -dm bash -c "ls"'
                                          .format(AdvancedDTLTester.VM_RANDOM.split("/")[2]).split())
                            vm_client.run('fio --help'.split())
                        except Exception as ex:
                            AdvancedDTLTester.LOGGER.error('Loading MD5SUM & dd in memory has failed with: {1}'
                                                           .format(AdvancedDTLTester.VM_FILENAME, ex))
                            raise

                        ###################################################
                        # Bringing proxies down from source storagedriver #
                        ###################################################
                        AdvancedDTLTester.LOGGER.error("Starting to stop proxy services")
                        proxies = InitManager.list_services(service_name_pattern="ovs-albaproxy_{0}".format(vpool.name),
                                                            ip=to_be_downed_client.ip)
                        for proxy in proxies:
                            AdvancedDTLTester.LOGGER.error("Starting to stop service: {0}".format(proxy))
                            InitManager.service_stop(service_name=proxy.split('.')[0], ip=to_be_downed_client.ip)
                            AdvancedDTLTester.LOGGER.error("Finished to stop service: {0}".format(proxy))

                        ##################
                        # write dtl file #
                        ##################
                        AdvancedDTLTester.LOGGER.info('Starting to WRITE file while proxy is offline!')
                        try:
                            vm_client.run('dd if=/dev/urandom of={0} bs=1M count=2'
                                          .format(AdvancedDTLTester.VM_FILENAME).split())
                            time.sleep(5)
                            original_md5sum = ' '.join(vm_client.run(['md5sum', AdvancedDTLTester.VM_FILENAME]).split())
                            AdvancedDTLTester.LOGGER.info('Original MD5SUM: {0}!'.format(original_md5sum))
                        except Exception as ex:
                            AdvancedDTLTester.LOGGER.error('Fetching MD5SUM for file {0} failed with: {1}'
                                                           .format(AdvancedDTLTester.VM_FILENAME, ex))
                            raise
                        AdvancedDTLTester.LOGGER.info('Finished to WRITE file while proxy is offline!')
                        AdvancedDTLTester.LOGGER.info("Waiting {0} seconds before stopping the parent hypervisor"
                                                      .format(AdvancedDTLTester.SLEEP_TIME))
                        time.sleep(AdvancedDTLTester.SLEEP_TIME)

                        #############
                        # START FIO #
                        #############
                        AdvancedDTLTester.LOGGER.info('Starting fio.')
                        try:
                            AdvancedDTLTester._write_data(vm_client, 'fio', AdvancedDTLTester.IO_PATTERN)
                        except Exception as ex:
                            AdvancedDTLTester.LOGGER.error('Could not start fio Got {0}'.format(str(ex)))
                            raise
                        time.sleep(AdvancedDTLTester.SLEEP_TIME_BEFORE_SHUTDOWN)

                        ##############################################
                        # Bringing original owner of the volume down #
                        ##############################################
                        try:
                            AdvancedDTLTester.LOGGER.info('Stopping {0}.'
                                                          .format(AdvancedDTLTester.PARENT_HYPERVISOR_INFO['vms'][source_str.ip]))
                            AdvancedDTLTester._stop_vm(hypervisor=parent_hypervisor,
                                                       vmid=AdvancedDTLTester.PARENT_HYPERVISOR_INFO
                                                       ['vms'][source_str.ip]['name'])
                        except Exception as ex:
                            AdvancedDTLTester.LOGGER.error('Failed to stop. Got {0}'.format(str(ex)))
                            raise

                        # Stop writing after some time
                        AdvancedDTLTester.LOGGER.info('Writing and monitoring for another {0}s.'
                                                      .format(AdvancedDTLTester.SLEEP_TIME))
                        time.sleep(AdvancedDTLTester.SLEEP_TIME)

                        #########################
                        # VALIDATE OF MIGRATION #
                        #########################
                        AdvancedDTLTester.LOGGER.info('Starting to validate move...')
                        AdvancedDTLTester._validate_move(values_to_check)
                        AdvancedDTLTester.LOGGER.info('Finished to validate move!')

                        ########################################
                        # VALIDATE IF DTL IS CORRECTLY WORKING #
                        ########################################
                        AdvancedDTLTester.LOGGER.info('Validate if DTL is working correctly!')
                        try:
                            finished_md5sum = ' '.join(vm_client.run(['md5sum', AdvancedDTLTester.VM_FILENAME]).split())
                        except Exception as ex:
                            AdvancedDTLTester.LOGGER.error('Fetching MD5SUM for file {0} failed with: {1}'
                                                           .format(AdvancedDTLTester.VM_FILENAME, ex))
                            raise
                        AdvancedDTLTester.LOGGER.info('Finished MD5SUM: {0}!'.format(finished_md5sum))
                        assert original_md5sum == finished_md5sum, "MD5SUMS after DTL SYNC & AUTO HA are " \
                                                                   "not the same, original: {0} current: {1}" \
                                                                   .format(original_md5sum, finished_md5sum)
                        AdvancedDTLTester.LOGGER.info('DTL is working correctly!')

                    except Exception as ex:
                        AdvancedDTLTester.LOGGER.error('Error occurred scenario during read: {0}, write {1}. Got {2}'
                                                       .format(AdvancedDTLTester.IO_PATTERN[0],
                                                               AdvancedDTLTester.IO_PATTERN[1], ex))
                        raise
            except Exception:
                # try stopping the VM on source/destination
                if vm_created is True:
                    AdvancedDTLTester._stop_vm(computenode_hypervisor, AdvancedDTLTester.VM_NAME, False)
                raise
            else:
                # Cleanup the vdisk after all tests were successfully executed!
                if vm_created is True:
                    AdvancedDTLTester._cleanup_vm(computenode_hypervisor, AdvancedDTLTester.VM_NAME, False)
                    AdvancedDTLTester._start_vm(parent_hypervisor,
                                                AdvancedDTLTester.PARENT_HYPERVISOR_INFO['vms'][source_str.ip]['name'])
                    time.sleep(AdvancedDTLTester.START_PARENT_TIMEOUT)
                if iso_loc is not None:
                    AdvancedDTLTester._cleanup_vdisk(boot_vdisk_name, vpool.name, False)
                if cloud_init_created:
                    AdvancedDTLTester._cleanup_vdisk(iso_loc.rsplit('/', 1)[1], vpool.name, False)
        except Exception as ex:
            AdvancedDTLTester.LOGGER.exception('Live migrate test failed. Got {0}'.format(str(ex)))
            # try stopping the VM on source/destination
            if vm_created is True:
                AdvancedDTLTester._stop_vm(computenode_hypervisor, AdvancedDTLTester.VM_NAME, False)
            raise

    @staticmethod
    def _get_free_port(listener_ip):
        """
        Returns a free port
        :param listener_ip: ip to listen on
        :return: port number
        """
        with remote(listener_ip, [socket]) as rem:
            listening_socket = None
            try:
                # Bind to first available port
                listening_socket = rem.socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                listening_socket.bind((listener_ip, 0))
                port = listening_socket.getsockname()[1]
                return port
            except socket.error as ex:
                AdvancedDTLTester.LOGGER.error('Could not bind the socket. Got {0}'.format(str(ex)))
                raise
            finally:
                if listening_socket:
                    try:
                        listening_socket.close()
                    except:
                        pass

    @staticmethod
    def _create_vm(hypervisor_ip, disks, networks, edge_details, cd_path, listening_port):
        """
        Creates and wait for the VM to be fully connected

        :return:
        """
        edge_hostname = edge_details['hostname']
        edge_port = edge_details['port']

        computenode_hypervisor = HypervisorFactory.get(hypervisor_ip, AdvancedDTLTester.HYPERVISOR_USER,
                                                       AdvancedDTLTester.HYPERVISOR_PASSWORD,
                                                       AdvancedDTLTester.HYPERVISOR_TYPE)
        ###########################
        # SETUP VMACHINE LISTENER #
        ###########################
        with remote(hypervisor_ip, [socket]) as rem:
            try:
                # Bind to first available port
                listening_socket = rem.socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                listening_socket.bind((hypervisor_ip, listening_port))
            except socket.error as ex:
                AdvancedDTLTester.LOGGER.error('Could not bind the socket. Got {0}'.format(str(ex)))
                raise
            port = listening_socket.getsockname()[1]
            # listen on socket and wait for data
            listening_socket.listen(1)
            AdvancedDTLTester.LOGGER.info('Socket now listening on port {0}, waiting to accept data.'.format(port))

            ##################
            # SETUP VMACHINE #
            ##################
            try:
                AdvancedDTLTester.LOGGER.info('Creating VM `{0}`'.format(AdvancedDTLTester.VM_NAME))
                computenode_hypervisor.sdk.create_vm(AdvancedDTLTester.VM_NAME,
                                                     vcpus=AdvancedDTLTester.VM_VCPUS,
                                                     ram=AdvancedDTLTester.VM_VRAM,
                                                     cdrom_iso=cd_path,
                                                     disks=disks,
                                                     networks=networks,
                                                     ovs_vm=True,
                                                     hostname=edge_hostname,
                                                     edge_port=edge_port,
                                                     start=True)
                AdvancedDTLTester.LOGGER.info('Created VM `{0}`!'.format(AdvancedDTLTester.VM_NAME))
            except RuntimeError as ex:
                AdvancedDTLTester.LOGGER.error('Creation of VM failed: {0}'.format(str(ex)))
                raise
            except libvirtError:
                # pass because of `libvirtError: internal error: client socket is closed`
                # but VM is succesfully created...
                pass

            ##########################################
            # WAIT FOR START OF VMACHINE AFTER SETUP #
            ##########################################
            # Wait for input from the VM for max x seconds
            client_connected = False
            start_time = time.time()
            vm_ip = None
            try:
                while not client_connected and time.time() - start_time < AdvancedDTLTester.VM_WAIT_TIME:
                    conn, addr = listening_socket.accept()
                    vm_ip = addr[0]
                    AdvancedDTLTester.LOGGER.info('Connected with {0}:{1}'.format(addr[0], addr[1]))
                    data = conn.recv(1024)
                    if data == AdvancedDTLTester.VM_CREATION_MESSAGE:
                        client_connected = True
            except:
                raise
            finally:
                listening_socket.close()
        return vm_ip

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
        AdvancedDTLTester.LOGGER.info('Source is documented as {0} and vdisk is now on {1}'
                                      .format(source_std.storagerouter.guid, vdisk.storagerouter_guid))
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
            AdvancedDTLTester.LOGGER.error(str(ex))
            if blocking is True:
                raise
            else:
                pass

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
            AdvancedDTLTester.LOGGER.error(str(ex))
            if blocking is True:
                raise
            else:
                pass

    @staticmethod
    def _stop_vm(hypervisor, vmid, blocking=True):
        """
        Destroy the created virtual machine
        :param hypervisor: hypervisor instance
        :param vmid: vm identifier
        :param blocking: boolean to determine whether errors should raise or not
        :return: None
        :rtype: NoneType
        """
        try:
            hypervisor.sdk.destroy(vmid=vmid)
        except Exception as ex:
            AdvancedDTLTester.LOGGER.error(str(ex))
            if blocking is True:
                raise
            else:
                pass

    @staticmethod
    def _start_vm(hypervisor, vmid, blocking=True):
        """
        Start the created virtual machine

        :param hypervisor: hypervisor instance
        :param vmid: vm identifier
        :param blocking: boolean to determine whether errors should raise or not
        :return: None
        :rtype: NoneType
        """
        try:
            hypervisor.sdk.power_on(vmid=vmid)
        except Exception as ex:
            AdvancedDTLTester.LOGGER.error(str(ex))
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
        for key, value in AdvancedDTLTester.CLOUD_INIT_DATA.iteritems():
            AdvancedDTLTester.LOGGER.info('Deleting {0}'.format(value))
            client.file_delete(value)
        return True

    @staticmethod
    def _generate_cloud_init(client, convert_script_loc, port, hypervisor_ip, username='test',
                             passwd='test', root_passwd='rooter'):
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
        :return: cloud init destination
        :rtype: str
        """
        path = AdvancedDTLTester.CLOUD_INIT_DATA['user-data_loc']
        # write out user-data
        lines = [
            '#!/bin/bash\n',
            '#user conf',
            'sudo echo "root:{0}" | chpasswd'.format(root_passwd),
            'sudo useradd {0}'.format(username),
            'sudo echo "{0}:{1}" | chpasswd'.format(username, passwd),
            'sudo adduser {0} sudo\n'.format(username),
            'apt-get update',
            'sed -ie "s/PermitRootLogin prohibit-password/PermitRootLogin yes/" /etc/ssh/sshd_config',
            'sed -ie "s/PasswordAuthentication no/PasswordAuthentication yes/" /etc/ssh/sshd_config',
            'sudo service ssh restart',
            'echo -n {0} | netcat -w 0 {1} {2}'.format(AdvancedDTLTester.VM_CREATION_MESSAGE, hypervisor_ip, port)
        ]
        with open(path, 'w') as user_data_file:
            user_data_file.write('\n'.join(lines))
        client.file_upload(path, path)

        # run script that generates meta-data and parser user-data and meta-data to a iso
        convert_cmd = [convert_script_loc, '--user-data', path, AdvancedDTLTester.CLOUD_INIT_DATA.get('config_dest')]
        try:
            client.run(convert_cmd)
            return AdvancedDTLTester.CLOUD_INIT_DATA.get('config_dest')
        except subprocess.CalledProcessError as ex:
            AdvancedDTLTester.LOGGER.error('Could not generate the cloud init file on {0}. '
                                           'Got {1} during iso conversion.'.format(client.ip, str(ex)))
            raise

    @staticmethod
    def _write_data(client, cmd_type, configuration, edge_configuration=None):
        """
        Fire and forget an IO test
        Starts a screen session detaches the sshclient
        :param client: ovs ssh client for the vm
        :type client: ovs.extensions.generic.sshclient.SSHClient
        :param cmd_type: type of command. Was used to differentiate between dd and fio
        :type cmd_type: str
        :param configuration: configuration params for fio. eg (10, 90)
                              first value represents read, second one write percentage
        :type configuration: tuple
        :param edge_configuration: configuration to fio over edge
        :type edge_configuration: dict
        :return: None
        :rtype: NoneType
        """
        bs = AdvancedDTLTester.BLOCK_SIZE * 1024
        write_size = AdvancedDTLTester.AMOUNT_TO_WRITE
        AdvancedDTLTester.LOGGER.info('Starting to write on VM `{0}`'.format(client.ip))
        if cmd_type == 'fio':
            config = ['--name=test', '--ioengine=libaio', '--iodepth={0}'.format(AdvancedDTLTester.IO_DEPTH),
                      '--rw=readwrite', '--bs={0}'.format(bs), '--direct=1', '--size={0}'.format(write_size),
                      '--rwmixread={0}'.format(configuration[0]), '--rwmixwrite={0}'.format(configuration[1])]
            if edge_configuration:
                # Append edge fio stuff
                additional_config = ['--ioengine=openvstorage', '--hostname={0}'.format(edge_configuration['hostname']),
                                     '--port={0}'.format(edge_configuration['port']), '--protocol={0}'
                                     .format(edge_configuration['protocol']),
                                     '--volumename={0}'.format(edge_configuration['volumename']), 'enable_ha=1']
                cmd = [edge_configuration['fio_bin_location']] + config + additional_config
            else:
                additional_config = ['--ioengine=libaio']
                cmd = ['fio'] + config + additional_config
            cmd = 'screen -S fio -dm bash -c "while true;1 do {0}; done"'.format(' '.join(cmd))
        else:
            raise ValueError('{0} is not supported for writing data.'.format(cmd_type))
        AdvancedDTLTester.LOGGER.info('Writing data with: {0}'.format(cmd))
        client.run(cmd, allow_insecure=True)


def run(blocked=False):
    """
    Run a test
    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return AdvancedDTLTester().main(blocked)

if __name__ == '__main__':
    # @todo remove print
    print run()
