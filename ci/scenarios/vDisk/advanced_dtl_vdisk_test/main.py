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

import sys
import json
import time
import socket
import threading
import subprocess
from datetime import datetime
from libvirt import libvirtError
from ci.helpers.api import OVSClient
from ci.helpers.hypervisor.hypervisor import HypervisorFactory
from ci.helpers.vpool import VPoolHelper
from ci.helpers.vdisk import VDiskHelper
from ci.helpers.storagerouter import StoragerouterHelper
from ci.helpers.storagedriver import StoragedriverHelper
from ci.helpers.system import SystemHelper
from ci.main import CONFIG_LOC
from ci.main import SETTINGS_LOC
from ci.setup.vdisk import VDiskSetup
from ci.remove.vdisk import VDiskRemover
from ovs.extensions.generic.remote import remote
from ovs.extensions.generic.sshclient import SSHClient
from ovs.log.log_handler import LogHandler


class AdvancedDTLTester(object):
    """
    Exercice HA with a VM via edge & KVM

    Required packages: qemu-kvm libvirt0 python-libvirt virtinst genisoimage
    Required commands after ovs installation and required packages: usermod -a -G ovs libvirt-qemu
    """

    CASE_TYPE = 'FUNCTIONAL'
    TEST_NAME = 'ci_scenario_advanced_dtl_test'
    LOGGER = LogHandler.get(source='scenario', name=TEST_NAME)
    SLEEP_TIME = 60
    VM_CONNECTING_TIMEOUT = 5
    REQUIRED_PACKAGES = ['qemu-kvm', 'libvirt0', 'python-libvirt', 'virtinst', 'genisoimage']
    VM_NAME = 'DTL-test'
    VM_WAIT_TIME = 300  # wait time before timing out on the vm install in seconds
    VM_CREATION_MESSAGE = 'I am created!'
    CLOUD_INIT_DATA = {
        'script_loc': 'https://raw.githubusercontent.com/kinvaris/cloud-init/master/create-config-drive',
        'script_dest': '/tmp/cloud_init_script.sh',
        'user-data_loc': '/tmp/user-data-migrate-test',
        'config_dest': '/tmp/cloud-init-config-migrate-test'
    }
    AMOUNT_TO_WRITE = 10 * 1024 ** 3  # 10 GB
    with open(CONFIG_LOC, 'r') as JSON_CONFIG:
        SETUP_CFG = json.load(JSON_CONFIG)

    # collect details about parent hypervisor
    PARENT_HYPERVISOR_INFO = SETUP_CFG['ci']['hypervisor']

    # vm credentials & details
    VM_USERNAME = 'root'
    VM_PASSWORD = 'rooter'
    VM_VCPUS = 1
    VM_VRAM = 512  # In MB

    # hypervisor details
    HYPERVISOR_TYPE = PARENT_HYPERVISOR_INFO['type']
    HYPERVISOR_USER = SETUP_CFG['ci']['user']['shell']['username']
    HYPERVISOR_PASSWORD = SETUP_CFG['ci']['user']['shell']['password']

    def __init__(self):
        pass

    @staticmethod
    def main(blocked):
        """
        Run all required methods for the test
        status depends on attributes in class: ci.helpers.testtrailapi.TestrailResult
        case_type depends on attributes in class: ci.helpers.testtrailapi.TestrailCaseType
        :param blocked: was the test blocked by other test?
        :return: results of test
        :rtype: dict
        """
        if not blocked:
            try:
                AdvancedDTLTester._execute_test()
                return {'status': 'PASSED', 'case_type': AdvancedDTLTester.CASE_TYPE, 'errors': None}
            except Exception as ex:
                return {'status': 'FAILED', 'case_type': AdvancedDTLTester.CASE_TYPE, 'errors': str(ex)}
        else:
            return {'status': 'BLOCKED', 'case_type': AdvancedDTLTester.CASE_TYPE, 'errors': None}

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

        str_1 = None  # Will act as volumedriver node
        str_2 = None  # Will act as volumedriver node
        str_3 = None  # Will act as compute node

        for node_ip, node_details in AdvancedDTLTester.PARENT_HYPERVISOR_INFO['vms'].iteritems():
            if node_details['role'] == "VOLDRV":
                if str_1 is None:
                    str_1 = StoragerouterHelper.get_storagerouter_by_ip(node_ip)
                    AdvancedDTLTester.LOGGER.info('Node with IP `{0}` has been selected as VOLDRV node (str_1)'.format(node_ip))
                elif str_2 is None:
                    str_2 = StoragerouterHelper.get_storagerouter_by_ip(node_ip)
                    AdvancedDTLTester.LOGGER.info('Node with IP `{0}` has been selected as VOLDRV node (str_2)'.format(node_ip))
            elif node_details['role'] == "COMPUTE" and str_3 is None:
                str_3 = StoragerouterHelper.get_storagerouter_by_ip(node_ip)
                AdvancedDTLTester.LOGGER.info('Node with IP `{0}` has been selected as COMPUTE node (str_3)'.format(node_ip))
            else:
                AdvancedDTLTester.LOGGER.info('Node with IP `{0}` is not required or has a invalid role: {1}'
                                              .format(node_ip, node_details['role']))

        # Get a suitable vpool with min. 2 storagedrivers
        vpool = None
        for vp in VPoolHelper.get_vpools():
            if len(vp.storagedrivers) >= 2 and vp.configuration['dtl_mode'] == VPoolHelper.DtlStatus.SYNC:
                vpool = vp
                break

        assert vpool is not None, 'Not enough vPools to test. We need at least a vPool with 2 storagedrivers'

        # Choose source & destination storage driver
        std_1 = [storagedriver for storagedriver in str_1.storagedrivers if storagedriver.vpool_guid == vpool.guid][0]
        std_2 = [storagedriver for storagedriver in str_2.storagedrivers if storagedriver.vpool_guid == vpool.guid][0]
        AdvancedDTLTester.LOGGER.info('Chosen source storagedriver is: {0}'.format(std_1.storage_ip))
        AdvancedDTLTester.LOGGER.info('Chosen destination storagedriver is: {0}'.format(std_2.storage_ip))

        # build ssh clients
        to_be_downed_client = SSHClient(str_2.ip, username='root')
        compute_client = SSHClient(str_3.ip, username='root')

        # check if enough images available
        images = settings['images']
        assert len(images) >= 1, 'Not enough images in `{0}`'.format(SETTINGS_LOC)

        # check if image exists
        image_path = images[0]
        assert to_be_downed_client.file_exists(image_path), 'Image `{0}` does not exists on `{1}`!'\
                                                            .format(images[0], to_be_downed_client.ip)

        # Get the cloud init file
        cloud_init_loc = AdvancedDTLTester.CLOUD_INIT_DATA['script_dest']
        compute_client.run(['wget', AdvancedDTLTester.CLOUD_INIT_DATA.get('script_loc'), '-O', cloud_init_loc])
        compute_client.file_chmod(cloud_init_loc, 755)
        assert compute_client.file_exists(cloud_init_loc), 'Could not fetch the cloud init script on {0}'\
            .format(str_3.ip)

        # Check if there are missing packages for the hypervisor
        missing_packages = SystemHelper.get_missing_packages(str_3.ip, AdvancedDTLTester.REQUIRED_PACKAGES)
        assert len(missing_packages) == 0, 'Missing {0} package(s) on `{1}`: {2}'.format(len(missing_packages), str_3.ip, missing_packages)
        cluster_info = {'storagerouters': {'str1': str_1, 'str2': str_2, 'str3': str_3}, 'storagedrivers': {'std1': std_1, 'std2': std_2}}

        AdvancedDTLTester.test_ha_vm(to_be_downed_client=to_be_downed_client, image_path=image_path, vpool=vpool,
                                     cloud_init_loc=cloud_init_loc, cluster_info=cluster_info, api=api)

    @staticmethod
    def test_ha_vm(to_be_downed_client, image_path, vpool, cloud_init_loc, cluster_info, api):
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
        :type api: ci.helpers.api.OVSClient
        :return: None
        :rtype: NoneType
        """
        str_2 = cluster_info['storagerouters']['str2']
        str_3 = cluster_info['storagerouters']['str3']
        std_1 = cluster_info['storagedrivers']['std1']
        std_2 = cluster_info['storagedrivers']['std2']

        # setup hypervisor details
        parent_hypervisor = HypervisorFactory.get(AdvancedDTLTester.PARENT_HYPERVISOR_INFO['ip'], AdvancedDTLTester.PARENT_HYPERVISOR_INFO['user'],
                                                  AdvancedDTLTester.PARENT_HYPERVISOR_INFO['password'], AdvancedDTLTester.PARENT_HYPERVISOR_INFO['type'])
        computenode_hypervisor = HypervisorFactory.get(str_3.ip, AdvancedDTLTester.HYPERVISOR_USER, AdvancedDTLTester.HYPERVISOR_PASSWORD, AdvancedDTLTester.HYPERVISOR_TYPE)

        ##############
        # SETUP TEST #
        ##############

        # Cache to validate properties
        values_to_check = {
            'source_std': std_1.serialize(),
            'target_std': std_2.serialize()
        }

        # Create a new vdisk to test
        boot_vdisk_name = '{0}_vdisk01'.format(AdvancedDTLTester.TEST_NAME)
        data_vdisk_name = '{0}_vdisk02'.format(AdvancedDTLTester.TEST_NAME)
        boot_vdisk_path = '/mnt/{0}/{1}.raw'.format(vpool.name, boot_vdisk_name)
        data_vdisk_path = '/mnt/{0}/{1}.raw'.format(vpool.name, data_vdisk_name)
        protocol = std_2.cluster_node_config['network_server_uri'].split(':')[0]
        disks = [{'mountpoint': boot_vdisk_path}, {'mountpoint': data_vdisk_path}]
        networks = [{'network': 'default', 'mac': 'RANDOM', 'model': 'e1000'}]

        # Milestones through the code
        files_generated = False
        vm_created = False
        try:
            #################
            # Create VDISKS #
            #################
            try:
                ovs_path = 'openvstorage+{0}:{1}:{2}/{3}'.format(protocol, std_2.storage_ip, std_2.ports['edge'],
                                                                 boot_vdisk_name)
                AdvancedDTLTester.LOGGER.info('Copying the image to the vdisk with command `qemu-img convert {0}`'
                                              .format(ovs_path))
                to_be_downed_client.run(['qemu-img', 'convert', image_path, ovs_path])
            except RuntimeError as ex:
                AdvancedDTLTester.LOGGER.error('Could not covert the image. Got {0}'.format(str(ex)))
                raise

            boot_vdisk = VDiskHelper.get_vdisk_by_name(boot_vdisk_name + '.raw', vpool.name)
            AdvancedDTLTester.LOGGER.info('VDisk `{0}` successfully created!'.format(boot_vdisk.name))
            try:
                data_vdisk = VDiskHelper.get_vdisk_by_guid(VDiskSetup.create_vdisk(data_vdisk_name, vpool.name, AdvancedDTLTester.AMOUNT_TO_WRITE, str_2.ip, api))
                AdvancedDTLTester.LOGGER.info('VDisk successfully created with guid `{0}`!'.format(data_vdisk.guid))
            except RuntimeError as ex:
                AdvancedDTLTester.LOGGER.error('Could not create the data vdisk. Got {0}'.format(str(ex)))
                raise

            ####################
            # Prep VM listener #
            ####################
            listening_port = AdvancedDTLTester._get_free_port(str_3.ip)

            #######################
            # GENERATE CLOUD INIT #
            #######################
            iso_loc = AdvancedDTLTester._generate_cloud_init(client=to_be_downed_client,
                                                             convert_script_loc=cloud_init_loc,
                                                             port=listening_port, hypervisor_ip=str_3.ip)
            to_be_downed_client.run(['qemu-img', 'convert', iso_loc, 'openvstorage+{0}:{1}:{2}/{3}'
                                    .format(protocol, str_2.ip, std_2.ports['edge'], iso_loc.rsplit('/', 1)[1])])
            cd_path = '/mnt/{0}/{1}.raw'.format(vpool.name, iso_loc.rsplit('/', 1)[1])

            ##############
            # START TEST #
            ##############
            try:
                ###################################
                # REVERT VDISK & RESET MILESTONES #
                ###################################
                # Certain milestones should be reset for every run
                vm_created = False
                # Get the current state of the vdisk to compare later
                values_to_check['vdisk'] = boot_vdisk.serialize()
                edge_details = {'port': std_2.ports['edge'], 'hostname': std_2.storage_ip, 'protocol': protocol}
                vm_ip = AdvancedDTLTester._create_vm(str_3.ip, disks, networks, edge_details, cd_path, listening_port)
                vm_created = True
                if vm_ip is None or vm_ip not in computenode_hypervisor.sdk.get_guest_ip_addresses(AdvancedDTLTester.VM_NAME):
                    raise RuntimeError('The VM did not connect to the source_hypervisor. Hypervisor has leased {0} and got {1}'
                                       .format(computenode_hypervisor.sdk.get_guest_ip_addresses(AdvancedDTLTester.VM_NAME), vm_ip))

                #######################
                # CONNECT TO VMACHINE #
                #######################

                vm_client = SSHClient(vm_ip, AdvancedDTLTester.VM_USERNAME, AdvancedDTLTester.VM_PASSWORD)
                AdvancedDTLTester.LOGGER.info('Connection was established with the VM.')
                # install fio on the VM
                AdvancedDTLTester.LOGGER.info('Installing fio on the VM.')
                vm_client.run(['apt-get', 'install', 'fio', '-y', '--force-yes'])
                AdvancedDTLTester.LOGGER.info('Installed fio on the VM!')

                # Start threading - own try except to kill off rogue threads
                try:
                    #############
                    # START FIO #
                    #############
                    threads = []
                    # Monitor IOPS activity
                    iops_activity = {'down': [], 'descending': [], 'rising': [], 'highest': None, 'lowest': None}
                    AdvancedDTLTester.LOGGER.info('Starting threads.')
                    try:
                        threads.append(AdvancedDTLTester._start_thread(AdvancedDTLTester._check_downtimes, name='iops', args=(iops_activity, boot_vdisk)))
                        AdvancedDTLTester._write_data(vm_client, 'fio', configuration)
                    except Exception as ex:
                        AdvancedDTLTester.LOGGER.error('Could not start threading. Got {0}'.format(str(ex)))
                        raise
                    time.sleep(AdvancedDTLTester.SLEEP_TIME)

                    ##############################################
                    # Bringing original owner of the volume down #
                    ##############################################
                    try:
                        AdvancedDTLTester.LOGGER.info('Stopping {0}.'.format(AdvancedDTLTester.PARENT_HYPERVISOR_INFO['vms'][str_3.ip]))
                        AdvancedDTLTester._stop_vm(hypervisor=parent_hypervisor, vmid=AdvancedDTLTester.PARENT_HYPERVISOR_INFO['vms'][str_3.ip])
                    except Exception as ex:
                        AdvancedDTLTester.LOGGER.error('Failed to stop. Got {0}'.format(str(ex)))
                        raise
                    # Stop writing after 30 more s
                    AdvancedDTLTester.LOGGER.info('Writing and monitoring for another {0}s.'.format(AdvancedDTLTester.SLEEP_TIME))
                    time.sleep(AdvancedDTLTester.SLEEP_TIME)
                    # Stop IO
                    for thread_pair in threads:
                        if thread_pair[0].isAlive():
                            thread_pair[1].set()

                    # Wait for threads to die
                    for thread_pair in threads:
                        thread_pair[0].join()
                    AdvancedDTLTester.LOGGER.info('IOPS monitoring: {0}'.format(iops_activity))

                    #########################
                    # VALIDATE OF MIGRATION #
                    #########################
                    # Validate move
                    AdvancedDTLTester._validate_move(values_to_check)
                    # Validate downtime
                    # Each log means +-4s downtime and slept twice
                    if len(iops_activity['down']) * 4 >= AdvancedDTLTester.SLEEP_TIME * 2:
                        raise ValueError('Thread did not cause any IOPS to happen.')
                except Exception:
                    AdvancedDTLTester.LOGGER.error('Error occurred scenario: read: {0}, write {1}.'.format(configuration[0], configuration[1]))
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
                if iso_loc is not None:
                    AdvancedDTLTester._cleanup_vdisk(boot_vdisk_name + '.raw', vpool.name, False)
        except Exception as ex:
            AdvancedDTLTester.LOGGER.exception('Live migrate test failed. Got {0}'.format(str(ex)))
            # try stopping the VM on source/destination
            if vm_created is True:
                AdvancedDTLTester._stop_vm(computenode_hypervisor, AdvancedDTLTester.VM_NAME, False)
            raise
        else:
            # cleanup data
            try:
                if files_generated is True:
                    AdvancedDTLTester._cleanup_generated_files(to_be_downed_client)
            except Exception:
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

        computenode_hypervisor = HypervisorFactory.get(hypervisor_ip, AdvancedDTLTester.HYPERVISOR_USER, AdvancedDTLTester.HYPERVISOR_PASSWORD, AdvancedDTLTester.HYPERVISOR_TYPE)
        ###########################
        # SETUP VMACHINE LISTENER #
        ###########################
        # Initialize listener for VM installation
        with remote(hypervisor_ip, [socket]) as rem:
            try:
                # Bind to first available port
                listening_socket = rem.socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                listening_socket.bind((hypervisor_ip, listening_port))
            except socket.error as ex:
                AdvancedDTLTester.LOGGER.error('Could not bind the socket. Got {0}'.format(str(ex)))
                raise
            port = listening_socket.getsockname()[1]
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
    def _validate_edge_ha():
        pass

    @staticmethod
    def _validate_move(values_to_check):
        """
        Validates the move test. Checks IO, and checks for dal changes
        :param values_to_check: dict with values to validate if they updated
        :type values_to_check: dict
        :return: None
        :rtype: NoneType
        """
        # Fetch dal object
        source_std = StoragedriverHelper.get_storagedriver_by_guid(values_to_check['source_std']['guid'])
        target_std = StoragedriverHelper.get_storagedriver_by_guid(values_to_check['target_std']['guid'])
        try:
            AdvancedDTLTester._validate_dal(values_to_check)
        except ValueError as ex:
            AdvancedDTLTester.LOGGER.warning('DAL did not automatically change after a move. Got {0}'.format(ex))
            source_std.invalidate_dynamics([])
            target_std.invalidate_dynamics([])
            # Properties should have been reloaded
            values_to_check['source_std'] = StoragedriverHelper.get_storagedriver_by_guid(values_to_check['source_std']['guid']).serialize()
            values_to_check['target_std'] = StoragedriverHelper.get_storagedriver_by_guid(values_to_check['target_std']['guid']).serialize()
            AdvancedDTLTester._validate_dal(values_to_check)

    @staticmethod
    def _validate_dal(values):
        """
        Validates the move test. Checks for dal changes
        :param values: dict with values to validate if they updated
        :type values: dict
        :return: None
        :rtype: NoneType
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
                AdvancedDTLTester.LOGGER.info('All properties are updated for source storagedriver.')
        if values['target_std'] == target_std.serialize():
            raise ValueError('Expecting changes in the target Storagedriver but nothing changed.')
        else:
            if vdisk.guid not in target_std.vdisks_guids:
                raise ValueError('Vdisks guids were not updated after move for target storagedriver.')
            else:
                AdvancedDTLTester.LOGGER.info('All properties are updated for target storagedriver.')
        if values['vdisk'] == vdisk.serialize():
            raise ValueError('Expecting changes in the vdisk but nothing changed.')
        else:
            if vdisk.storagerouter_guid == target_std.storagerouter.guid:
                AdvancedDTLTester.LOGGER.info('All properties are updated for vdisk.')
            else:
                ValueError('Expected {0} but found {1} for vdisk.storagerouter_guid'.format(vdisk.storagerouter_guid, vdisk.storagerouter_guid))
        AdvancedDTLTester.LOGGER.info('Move vdisk was successful according to the dal (which fetches volumedriver info).')

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
        Stop the created virtual machine
        :param hypervisor: hypervisor instance
        :param vmid: vm identifier
        :param blocking: boolean to determine whether errors should raise or not
        :return: None
        :rtype: NoneType
        """
        try:
            hypervisor.sdk.shutdown(vmid=vmid)
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
    def _generate_cloud_init(client, convert_script_loc, port, hypervisor_ip, username='test', passwd='test', root_passwd='rooter'):
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
        path = AdvancedDTLTester.CLOUD_INIT_DATA.get('user-data_loc')
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
            'parted /dev/vdb mklabel gpt mkpart 1 ext4 1MiB 5G'
            'mkfs.ext4 /dev/vdb1',
            'mkdir /mnt/data'
            'mount /dev/vdb1 /mnt/data'
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
            AdvancedDTLTester.LOGGER.error('Could not generate the cloud init file on {0}. Got {1} during iso conversion.'.format(client.ip, str(ex.output)))
            raise

    @staticmethod
    def _check_downtimes(results, vdisk, stop_event):
        """
        Threading method that will check for IOPS downtimes
        :param results: variable reserved for this thread
        :type results: dict
        :param vdisk: vdisk object
        :type vdisk: ovs.dal.hybrids.vdisk.VDISK
        :param stop_event: Threading event to watch for
        :type stop_event: threading._Event
        :return: None
        :rtype: NoneType
        """
        last_recorded_iops = None
        while not stop_event.is_set():
            now = datetime.today().strftime('%Y-%m-%d %H:%M:%S')
            current_iops = vdisk.statistics['operations']
            if current_iops == 0:
                results['down'].append((now, current_iops))
            else:
                if last_recorded_iops >= current_iops:
                    results['rising'].append((now, current_iops))
                else:
                    results['descending'].append((now, current_iops))
                if current_iops > results['highest'] or results['highest'] is None:
                    results['highest'] = current_iops
                if current_iops < results['lowest'] or results['lowest'] is None:
                    results['lowest'] = current_iops
            # Sleep to avoid caching
            last_recorded_iops = current_iops
            time.sleep(4)

    @staticmethod
    def _write_data(client, cmd_type, configuration, edge_configuration=None):
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
        :return: None
        :rtype: NoneType
        """
        bs = 1 * 1024 ** 2
        write_size = AdvancedDTLTester.AMOUNT_TO_WRITE
        AdvancedDTLTester.LOGGER.info('Starting to write on VM `{0}`'.format(client.ip))
        if cmd_type == 'fio':
            config = ['--name=test', '--ioengine=libaio', '--iodepth=4', '--rw=readwrite', '--bs={0}'.format(bs),
                      '--direct=1', '--size={0}'.format(write_size), '--rwmixread={0}'.format(configuration[0]),
                      '--rwmixwrite={0}'.format(configuration[1])]
            if edge_configuration:
                # Append edge fio stuff
                additional_config = ['--ioengine=openvstorage', '--hostname={0}'.format(edge_configuration['hostname']),
                                     '--port={0}'.format(edge_configuration['port']), '--protocol={0}'.format(edge_configuration['protocol']),
                                     '--volumename={0}'.format(edge_configuration['volumename']), 'enable_ha=1']
                cmd = [edge_configuration['fio_bin_location']] + config + additional_config
            else:
                additional_config = ['--ioengine=libaio']
                cmd = ['fio'] + config + additional_config
            cmd = 'screen -S fio -dm bash -c "while true; do {0}; done"'.format(' '.join(cmd))
        else:
            raise ValueError('{0} is not supported for writing data.'.format(cmd_type))
        AdvancedDTLTester.LOGGER.info('Writing data with: {0}'.format(cmd))
        client.run(cmd, allow_insecure=True)

    @staticmethod
    def _start_thread(target, name, args=()):
        """
        Starts a thread
        :param target: target - usually a method
        :type target: object
        :param name: name of the thread
        :type name: str
        :param args: tuple of arguments
        :type args: tuple
        :return: a tuple with the thread and event
        :rtype: tuple
        """
        AdvancedDTLTester.LOGGER.info('Starting thread with target {0}'.format(target))
        event = threading.Event()
        args = args + (event,)
        thread = threading.Thread(target=target, args=tuple(args))
        thread.setName(str(name))
        thread.start()
        return thread, event


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
