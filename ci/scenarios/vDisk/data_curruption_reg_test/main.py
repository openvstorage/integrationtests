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
import random
import socket
import subprocess
from libvirt import libvirtError
from ci.api_lib.helpers.hypervisor.hypervisor import HypervisorFactory
from ci.api_lib.helpers.vpool import VPoolHelper
from ci.api_lib.helpers.vdisk import VDiskHelper
from ci.api_lib.helpers.system import SystemHelper
from ci.main import CONFIG_LOC
from ci.main import SETTINGS_LOC
from ci.api_lib.remove.vdisk import VDiskRemover
from ovs.extensions.generic.remote import remote
from ovs.extensions.generic.sshclient import SSHClient
from ovs.log.log_handler import LogHandler


class DataCorruptionTester(object):
    """
    This is a regression test for https://github.com/openvstorage/integrationtests/issues/468

    Required packages: qemu-kvm libvirt0 python-libvirt virtinst genisoimage
    Required commands after ovs installation and required packages: usermod -a -G ovs libvirt-qemu
    """

    CASE_TYPE = 'STABILITY'
    TEST_NAME = 'ci_scenario_data_corruption'
    LOGGER = LogHandler.get(source='scenario', name=TEST_NAME)
    SLEEP_TIME = 60
    SLEEP_TIME_BEFORE_SHUTDOWN = 30
    VM_CONNECTING_TIMEOUT = 5
    VM_CREATION_MESSAGE = 'I am created!'
    REQUIRED_PACKAGES = ['qemu-kvm', 'libvirt0', 'python-libvirt', 'virtinst', 'genisoimage']
    VM_NAME = 'DTL-test'
    VM_WAIT_TIME = 300  # wait time before timing out on the vm install in seconds
    START_PARENT_TIMEOUT = 30
    VDBENCH_ZIP = "http://fileserver.cloudfounders.com/Operations/IT/Software/vdbench/vdbench.zip"
    VM_VDBENCH_ZIP = "/root/vdbench.zip"
    AMOUNT_THREADS = 4  # threads
    AMOUNT_TO_WRITE = 3  # in GB, size
    AMOUNT_DATA_ERRORS = 1  # data_errors
    VDBENCH_TIME = 7200  # in seconds
    VDBENCH_INTERVAL = 1  # in seconds
    WORKLOAD = ['wd1']  # wd
    IO_RATE = 'max'  # iorate
    RUNNAME = 'data_cor_run'  # rd
    # xfersize
    XFERSIZE = '(4k,25.68,8k,26.31,16k,6.4,32k,7.52,60k,10.52,128k,9.82,252k,7.31,504k,6.19,984k,0.23,1032k,0.02)'
    READ_PERCENTAGE = 50  # rdpct
    RANDOM_SEEK_PERCENTAGE = 100  # seekpct
    VM_FILENAME = "/root/vdbench_file"  # lun
    VM_VDBENCH_CFG_PATH = "/root/vdbench_run.cfg"

    # cloud init details
    CLOUD_INIT_DATA = {
        'script_loc': 'https://raw.githubusercontent.com/kinvaris/cloud-init/master/create-config-drive',
        'script_dest': '/tmp/cloud_init_script.sh',
        'user-data_loc': '/tmp/user-data-migrate-test',
        'config_dest': '/tmp/cloud-init-config-migrate-test'
    }

    with open(CONFIG_LOC, 'r') as JSON_CONFIG:
        SETUP_CFG = json.load(JSON_CONFIG)

    with open(SETTINGS_LOC, 'r') as JSON_SETTINGS:
        SETTINGS = json.load(JSON_SETTINGS)

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
    def main(blocked):
        """
        Run all required methods for the test

        status depends on attributes in class: ci.api_lib.helpers.testtrailapi.TestrailResult
        case_type depends on attributes in class: ci.api_lib.helpers.testtrailapi.TestrailCaseType
        :param blocked: was the test blocked by other test?
        :return: results of test
        :rtype: dict
        """
        if not blocked:
            try:
                DataCorruptionTester._execute_test()
                return {'status': 'PASSED', 'case_type': DataCorruptionTester.CASE_TYPE, 'errors': None}
            except Exception as ex:
                return {'status': 'FAILED', 'case_type': DataCorruptionTester.CASE_TYPE, 'errors': str(ex)}
        else:
            return {'status': 'BLOCKED', 'case_type': DataCorruptionTester.CASE_TYPE, 'errors': None}

    @staticmethod
    def _execute_test():
        """
        Execute the live migration test
        """

        DataCorruptionTester.LOGGER.info('Starting data corruption regression test')

        #################
        # PREREQUISITES #
        #################

        # Get a suitable vpool
        vpool = None
        for vp in VPoolHelper.get_vpools():
            if len(vp.storagedrivers) >= 2:
                vpool = vp
                break
        assert vpool is not None, "Not enough vPools to test. Requires 1 with at least 2 storagedrivers and found 0."

        # choose the storagedriver
        storagedriver = random.choice([st for st in vpool.storagedrivers])
        DataCorruptionTester.LOGGER.info('Chosen source storagedriver: {0}'
                                         .format(storagedriver.storage_ip))

        # build ssh client
        client = SSHClient(storagedriver.storagerouter.ip, username='root')

        # check if enough images available
        images = DataCorruptionTester.SETTINGS['images']
        assert len(images) >= 1, 'Not enough images in `{0}`'.format(SETTINGS_LOC)

        # check if image exists
        image_path = images[0]
        assert client.file_exists(image_path), 'Image `{0}` does not exists on `{1}`!'\
                                               .format(images[0], client.ip)

        # Get the cloud init file
        cloud_init_loc = DataCorruptionTester.CLOUD_INIT_DATA['script_dest']
        client.run(['wget', DataCorruptionTester.CLOUD_INIT_DATA['script_loc'], '-O', cloud_init_loc])
        client.file_chmod(cloud_init_loc, 755)
        assert client.file_exists(cloud_init_loc), 'Could not fetch the cloud init script on {0}'.format(client.ip)

        # Check if there are missing packages for the hypervisor
        missing_packages = SystemHelper.get_missing_packages(client.ip, DataCorruptionTester.REQUIRED_PACKAGES)
        assert len(missing_packages) == 0, 'Missing {0} package(s) on `{1}`: {2}'.format(len(missing_packages),
                                                                                         client.ip, missing_packages)

        #####################
        # START ACTUAL TEST #
        #####################

        DataCorruptionTester._test_vdbench(client=client, image_path=image_path, cloud_init_loc=cloud_init_loc,
                                           storagedriver=storagedriver)

        DataCorruptionTester.LOGGER.info('Finished data corruption regression test!')

    @staticmethod
    def _test_vdbench(client, image_path, cloud_init_loc, storagedriver):
        """
        Deploy a vdbench and see if the following bug is triggered (or other datacorruption bugs)
        https://github.com/openvstorage/integrationtests/issues/468

        :param client: sshclient of the storagerouter where the VM will be deployed
        :type client: ovs.extensions.generic.sshclient.SSHClient
        :param image_path: path of the cloud init image
        :type image_path: str
        :param cloud_init_loc: location of the cloud init boot file
        :type cloud_init_loc: str
        :param storagedriver: storagedriver to use for the VM its vdisks
        :type storagedriver: ovs.dal.hybrids.storagedriver.StorageDriver
        :return: None
        :rtype: NoneType
        """

        # setup hypervisor details
        hypervisor = HypervisorFactory.get(storagedriver.storagerouter.ip,
                                           DataCorruptionTester.HYPERVISOR_USER,
                                           DataCorruptionTester.HYPERVISOR_PASSWORD,
                                           DataCorruptionTester.HYPERVISOR_TYPE)

        ##############
        # SETUP TEST #
        ##############

        # Create a new vdisk to test
        boot_vdisk_name = '{0}_vdisk01'.format(DataCorruptionTester.TEST_NAME)
        boot_vdisk_path = '/mnt/{0}/{1}.raw'.format(storagedriver.vpool.name, boot_vdisk_name)
        protocol = storagedriver.cluster_node_config['network_server_uri'].split(':')[0]
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
                ovs_path = 'openvstorage+{0}:{1}:{2}/{3}'.format(protocol, storagedriver.storage_ip,
                                                                 storagedriver.ports['edge'], boot_vdisk_name)
                DataCorruptionTester.LOGGER.info('Copying the image to the vdisk with command `qemu-img convert {0} {1}`'
                                                 .format(image_path, ovs_path))
                client.run(['qemu-img', 'convert', image_path, ovs_path])
            except RuntimeError as ex:
                DataCorruptionTester.LOGGER.error('Could not covert the image. Got {0}'.format(str(ex)))
                raise

            boot_vdisk = VDiskHelper.get_vdisk_by_name(boot_vdisk_name + '.raw', storagedriver.vpool.name)
            DataCorruptionTester.LOGGER.info('VDisk `{0}` successfully created!'.format(boot_vdisk.name))

            ####################
            # Prep VM listener #
            ####################
            listening_port = DataCorruptionTester._get_free_port(client.ip)

            #######################
            # GENERATE CLOUD INIT #
            #######################
            # iso_loc = "/tmp/cloud-init-config-migrate-test"
            iso_loc = DataCorruptionTester._generate_cloud_init(client=client,
                                                                convert_script_loc=cloud_init_loc,
                                                                port=listening_port, hypervisor_ip=client.ip)
            client.run(['qemu-img', 'convert', iso_loc, 'openvstorage+{0}:{1}:{2}/{3}'
                                    .format(protocol, storagedriver.storage_ip, storagedriver.ports['edge'],
                                            iso_loc.rsplit('/', 1)[1])])
            cd_path = '/mnt/{0}/{1}.raw'.format(storagedriver.vpool.name, iso_loc.rsplit('/', 1)[1])
            cloud_init_created = True

            ##############
            # START TEST #
            ##############
            try:
                #############
                # CREATE VM #
                #############
                edge_details = {'port': storagedriver.ports['edge'], 'hostname': storagedriver.storage_ip,
                                'protocol': protocol}
                vm_ip = DataCorruptionTester._create_vm(client.ip, disks, networks, edge_details, cd_path,
                                                        listening_port)
                vm_created = True
                if vm_ip is None or vm_ip not in hypervisor.sdk.get_guest_ip_addresses(DataCorruptionTester.VM_NAME):
                    raise RuntimeError('The VM did not connect to the source_hypervisor. '
                                       'Hypervisor has leased {0} and got {1}'
                                       .format(hypervisor.sdk.get_guest_ip_addresses(DataCorruptionTester.VM_NAME),
                                               vm_ip))

                #######################
                # CONNECT TO VMACHINE #
                #######################
                with remote(client.ip, [SSHClient]) as rem:
                    vm_client = rem.SSHClient(vm_ip, DataCorruptionTester.VM_USERNAME, DataCorruptionTester.VM_PASSWORD)
                    DataCorruptionTester.LOGGER.info('Connection was established with the VM.')
                    # install fio on the VM
                    DataCorruptionTester.LOGGER.info('Installing vdbench ...')
                    try:
                        vm_client.run(['apt-get', 'install', 'unzip', 'openjdk-9-jre-headless', '-y'])
                        vm_client.run(['wget', DataCorruptionTester.VDBENCH_ZIP, '-O',
                                       DataCorruptionTester.VM_VDBENCH_ZIP])
                        DataCorruptionTester.LOGGER.info('Successfully fetched vdbench ZIP')
                        vm_client.run(['unzip', DataCorruptionTester.VM_VDBENCH_ZIP])
                        DataCorruptionTester.LOGGER.info('Successfully unzipped vdbench ZIP')
                        vm_client.run(['echo', '"data_errors={0}"'.format(DataCorruptionTester.AMOUNT_DATA_ERRORS),
                                       '>>', DataCorruptionTester.VM_VDBENCH_CFG_PATH])
                        vm_client.run(['echo', '"sd=sd1,lun={0},threads={1},size={2}g"'
                                               .format(DataCorruptionTester.VM_FILENAME,
                                                       DataCorruptionTester.AMOUNT_THREADS,
                                                       DataCorruptionTester.AMOUNT_TO_WRITE),
                                       '>>', DataCorruptionTester.VM_VDBENCH_CFG_PATH])
                        vm_client.run(['echo', '"wd={0},sd=(sd1),xfersize={1},rdpct={2},seekpct={3},openflags=directio"'
                                               .format(DataCorruptionTester.WORKLOAD,
                                                       DataCorruptionTester.XFERSIZE,
                                                       DataCorruptionTester.READ_PERCENTAGE,
                                                       DataCorruptionTester.RANDOM_SEEK_PERCENTAGE),
                                       '>>', DataCorruptionTester.VM_VDBENCH_CFG_PATH])
                        vm_client.run(['echo', '"rd={0},iorate={1},elapsed={2},interval={3}"'
                                      .format(DataCorruptionTester.RUNNAME,
                                              DataCorruptionTester.IO_RATE,
                                              DataCorruptionTester.VDBENCH_TIME,
                                              DataCorruptionTester.VDBENCH_INTERVAL),
                                       '>>', DataCorruptionTester.VM_VDBENCH_CFG_PATH])
                        DataCorruptionTester.LOGGER.info('Successfully deployed config')
                    except subprocess.CalledProcessError as ex:
                        DataCorruptionTester.LOGGER.info('Failed to deploy vdbench: {0}'.format(ex))
                        raise

                    ######################
                    # START VDBENCH TEST #
                    ######################
                    DataCorruptionTester.LOGGER.info('Starting VDBENCH!')
                    try:
                        vm_client.run('screen -S fio -dm bash -c "./vdbench -vr -f {0}"'
                                      .format(DataCorruptionTester.VM_VDBENCH_CFG_PATH).split())
                    except Exception as ex:
                        DataCorruptionTester.LOGGER.error('Error during VDBENCH test: {0}'.format(ex))
                        raise
                    DataCorruptionTester.LOGGER.info('Finished VDBENCH without errors!')

                    DataCorruptionTester.LOGGER.info('No data corruption detected!')
            except Exception:
                raise
            else:
                # Cleanup the vdisk after all tests were successfully executed!
                if vm_created is True:
                    DataCorruptionTester._cleanup_vm(hypervisor, DataCorruptionTester.VM_NAME, False)
                    time.sleep(DataCorruptionTester.START_PARENT_TIMEOUT)
                if iso_loc is not None:
                    DataCorruptionTester._cleanup_vdisk(boot_vdisk_name, storagedriver.vpool.name, False)
                if cloud_init_created:
                    DataCorruptionTester._cleanup_vdisk(iso_loc.rsplit('/', 1)[1], storagedriver.vpool.name, False)
        except Exception as ex:
            DataCorruptionTester.LOGGER.error('Error occured during test: {0}'.format(ex))
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
                DataCorruptionTester.LOGGER.error('Could not bind the socket. Got {0}'.format(str(ex)))
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

        computenode_hypervisor = HypervisorFactory.get(hypervisor_ip, DataCorruptionTester.HYPERVISOR_USER,
                                                       DataCorruptionTester.HYPERVISOR_PASSWORD,
                                                       DataCorruptionTester.HYPERVISOR_TYPE)
        ###########################
        # SETUP VMACHINE LISTENER #
        ###########################
        with remote(hypervisor_ip, [socket]) as rem:
            try:
                # Bind to first available port
                listening_socket = rem.socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                listening_socket.bind((hypervisor_ip, listening_port))
            except socket.error as ex:
                DataCorruptionTester.LOGGER.error('Could not bind the socket. Got {0}'.format(str(ex)))
                raise
            port = listening_socket.getsockname()[1]
            # listen on socket and wait for data
            listening_socket.listen(1)
            DataCorruptionTester.LOGGER.info('Socket now listening on port {0}, waiting to accept data.'.format(port))

            ##################
            # SETUP VMACHINE #
            ##################
            try:
                DataCorruptionTester.LOGGER.info('Creating VM `{0}`'.format(DataCorruptionTester.VM_NAME))
                computenode_hypervisor.sdk.create_vm(DataCorruptionTester.VM_NAME,
                                                     vcpus=DataCorruptionTester.VM_VCPUS,
                                                     ram=DataCorruptionTester.VM_VRAM,
                                                     cdrom_iso=cd_path,
                                                     disks=disks,
                                                     networks=networks,
                                                     ovs_vm=True,
                                                     hostname=edge_hostname,
                                                     edge_port=edge_port,
                                                     start=True)
                DataCorruptionTester.LOGGER.info('Created VM `{0}`!'.format(DataCorruptionTester.VM_NAME))
            except RuntimeError as ex:
                DataCorruptionTester.LOGGER.error('Creation of VM failed: {0}'.format(str(ex)))
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
                while not client_connected and time.time() - start_time < DataCorruptionTester.VM_WAIT_TIME:
                    conn, addr = listening_socket.accept()
                    vm_ip = addr[0]
                    DataCorruptionTester.LOGGER.info('Connected with {0}:{1}'.format(addr[0], addr[1]))
                    data = conn.recv(1024)
                    if data == DataCorruptionTester.VM_CREATION_MESSAGE:
                        client_connected = True
            except:
                raise
            finally:
                listening_socket.close()
        return vm_ip

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
            DataCorruptionTester.LOGGER.error(str(ex))
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
            DataCorruptionTester.LOGGER.error(str(ex))
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
            DataCorruptionTester.LOGGER.error(str(ex))
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
            DataCorruptionTester.LOGGER.error(str(ex))
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
        for key, value in DataCorruptionTester.CLOUD_INIT_DATA.iteritems():
            DataCorruptionTester.LOGGER.info('Deleting {0}'.format(value))
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
        path = DataCorruptionTester.CLOUD_INIT_DATA['user-data_loc']
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
            'echo -n {0} | netcat -w 0 {1} {2}'.format(DataCorruptionTester.VM_CREATION_MESSAGE, hypervisor_ip, port)
        ]
        with open(path, 'w') as user_data_file:
            user_data_file.write('\n'.join(lines))
        client.file_upload(path, path)

        # run script that generates meta-data and parser user-data and meta-data to a iso
        convert_cmd = [convert_script_loc, '--user-data', path, DataCorruptionTester.CLOUD_INIT_DATA.get('config_dest')]
        try:
            client.run(convert_cmd)
            return DataCorruptionTester.CLOUD_INIT_DATA.get('config_dest')
        except subprocess.CalledProcessError as ex:
            DataCorruptionTester.LOGGER.error('Could not generate the cloud init file on {0}. '
                                           'Got {1} during iso conversion.'.format(client.ip, str(ex)))
            raise


def run(blocked=False):
    """
    Run a test
    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return DataCorruptionTester().main(blocked)

if __name__ == '__main__':
    # @todo remove print
    print run()
