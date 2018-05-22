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
import uuid
import time
import Queue
import subprocess
from ci.api_lib.helpers.api import TimeOutError
from ci.api_lib.helpers.exceptions import VDiskNotFoundError
from ci.api_lib.helpers.hypervisor.hypervisor import HypervisorCredentials, HypervisorFactory
from ci.api_lib.helpers.vdisk import VDiskHelper
from ci.api_lib.remove.vdisk import VDiskRemover
from ci.api_lib.setup.vdisk import VDiskSetup
from ci.scenario_helpers.ci_constants import CIConstants
from ci.scenario_helpers.threaded_server import ThreadedServer
from ovs.log.log_handler import LogHandler
from ovs.extensions.generic.sshclient import SSHClient
from ovs_extensions.generic.toolbox import ExtensionsToolbox
from ovs.lib.helpers.toolbox import Toolbox


class VMHandler(CIConstants):
    """
    Class that can create virtual machines
    """
    LOGGER = LogHandler.get(source='scenario_helpers', name='vm_handler')
    CLOUD_INIT_DATA = {
        'script_loc': 'http://fileserver.cloudfounders.com/QA/cloud-init/create-config-drive',
        'script_dest': '/tmp/cloud_init_script.sh',
        'user-data_loc': '/tmp/user-data-migrate-test',
        'config_dest': '/tmp/cloud-init-config-migrate-test'
    }

    VM_VCPUS = 4
    VM_VRAM = 1024  # In MB
    VM_OS_TYPE = 'ubuntu16.04'

    LISTEN_TIMEOUT = 60 * 60
    SOCKET_BINDING_TIMEOUT = 5 * 60

    def __init__(self, hypervisor_ip, amount_of_vms=1):
        self.hypervisor_ip = hypervisor_ip
        self.amount_of_vms = amount_of_vms
        self.hv_credentials = HypervisorCredentials(ip=self.hypervisor_ip,
                                                    user=self.HYPERVISOR_INFO['user'],
                                                    password=self.HYPERVISOR_INFO['password'],
                                                    type=self.HYPERVISOR_INFO['type'])
        self.hypervisor_client = HypervisorFactory.get(self.hv_credentials)

        self.vm_info = None
        self.connection_messages = None
        self.volume_amount = None

        self.result_queue = Queue.Queue()
        self.threaded_server = ThreadedServer('', 0, remote_ip=self.hypervisor_ip)
        self.threaded_server.listen_threaded()  # Start our listening to reserve our port
        self.listening_port = self.threaded_server.get_listening_port()
        self.LOGGER.info('VMHandler now listening to port {0}:{1}'.format(self.hypervisor_ip, self.listening_port))

    def prepare_vm_disks(self, source_storagedriver, cloud_image_path, cloud_init_loc,
                         vm_name, data_disk_size, edge_user_info=None, logger=LOGGER):
        """
        Will create all necessary vdisks to create the bulk of vms
        :param source_storagedriver: storagedriver to create the disks on
        :param cloud_image_path: path to the cloud image
        :param cloud_init_loc: path to the cloud init script
        :param vm_name: name prefix for the vms
        :param data_disk_size: size of the data disk
        :param edge_user_info: user information for the edge. Optional
        :param logger: logging instance
        :return:
        """
        logger.info('Starting with preparing vm disk(s)')
        vm_amount = self.amount_of_vms
        if isinstance(edge_user_info, dict):
            required_edge_params = {'username': (str, None, False),
                                    'password': (str, None, False)}
            ExtensionsToolbox.verify_required_params(required_edge_params, edge_user_info)
        if edge_user_info is None:
            edge_user_info = {}

        protocol = source_storagedriver.cluster_node_config['network_server_uri'].split(':')[0]
        vpool = source_storagedriver.vpool
        client = SSHClient(source_storagedriver.storagerouter, username='root')

        edge_configuration = {'ip': source_storagedriver.storage_ip,
                              'port': source_storagedriver.ports['edge'],
                              'protocol': protocol}
        edge_configuration.update(edge_user_info)

        original_boot_disk_name = None  # Cloning purposes
        original_data_disk_name = None  # Cloning purposes

        connection_messages = []
        vm_info = {}
        volume_amount = 0

        for vm_number in xrange(0, vm_amount):
            filled_number = str(vm_number).zfill(3)
            vm_name = '{0}-{1}'.format(vm_name, filled_number)
            create_msg = '{0}_{1}'.format(str(uuid.uuid4()), vm_name)
            boot_vdisk_name = '{0}_vdisk_boot_{1}'.format(vm_name, filled_number)
            data_vdisk_name = '{0}_vdisk_data_{1}'.format(vm_name, filled_number)
            cd_vdisk_name = '{0}_vdisk_cd_{1}'.format(vm_name, filled_number)
            boot_vdisk_path = '/mnt/{0}/{1}.raw'.format(vpool.name, boot_vdisk_name)
            data_vdisk_path = '/mnt/{0}/{1}.raw'.format(vpool.name, data_vdisk_name)
            cd_vdisk_path = '/mnt/{0}/{1}.raw'.format(vpool.name, cd_vdisk_name)
            if vm_number == 0:
                try:
                    # Create VDISKs
                    self.convert_image(client, cloud_image_path, boot_vdisk_name, edge_configuration)
                except RuntimeError as ex:
                    logger.error('Could not covert the image. Got {0}'.format(str(ex)))
                    raise
                boot_vdisk = VDiskHelper.get_vdisk_by_name('{0}.raw'.format(boot_vdisk_name), vpool.name)
                original_boot_disk_name = boot_vdisk_name
                logger.info('Boot VDisk successfully created.')
                try:
                    data_vdisk = VDiskHelper.get_vdisk_by_guid(VDiskSetup.create_vdisk(data_vdisk_name, vpool.name, data_disk_size, source_storagedriver.storage_ip))
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
                                                          storagerouter_ip=source_storagedriver.storage_ip)
                boot_vdisk = VDiskHelper.get_vdisk_by_guid(boot_vdisk_info['vdisk_guid'])
                data_vdisk_info = VDiskSetup.create_clone(vdisk_name=original_data_disk_name,
                                                          vpool_name=vpool.name,
                                                          new_vdisk_name=data_vdisk_name,
                                                          storagerouter_ip=source_storagedriver.storage_ip)
                data_vdisk = VDiskHelper.get_vdisk_by_guid(data_vdisk_info['vdisk_guid'])
            #######################
            # GENERATE CLOUD INIT #
            #######################
            iso_loc = self._generate_cloud_init(client=client, convert_script_loc=cloud_init_loc,
                                                create_msg=create_msg)
            self.convert_image(client, iso_loc, cd_vdisk_name, edge_configuration)
            cd_creation_time = time.time()
            cd_vdisk = None
            while cd_vdisk is None:
                if time.time() - cd_creation_time > 60:
                    raise RuntimeError('Could not fetch the cd vdisk after {}s'.format(time.time() - cd_creation_time))
                try:
                    cd_vdisk = VDiskHelper.get_vdisk_by_name(cd_vdisk_name, vpool.name)
                except VDiskNotFoundError:
                    logger.warning('Could not fetch the cd vdisk after {0}s.'.format(time.time() - cd_creation_time))
                time.sleep(0.5)

            # Take snapshot to revert back to after every migrate scenario
            data_snapshot_guid = VDiskSetup.create_snapshot('{0}_data'.format(vm_name),
                                                            data_vdisk.devicename,
                                                            vpool.name,
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

        self.vm_info = vm_info
        self.connection_messages = connection_messages
        self.volume_amount = volume_amount

    def create_vms(self, edge_configuration, timeout, logger=LOGGER):
        """
        Create multiple VMs and wait for their creation to be completed
        :param edge_configuration: details of the edge
        :param timeout: timeout how long the function can wait for vm creation
        :param logger: logging instance
        :return:
        """
        logger.info('Creating vms')
        for vm_name, vm_data in self.vm_info.iteritems():
            logger.info('Initializing creation of vm {0}'.format(vm_name))
            self.create_vm(vm_name=vm_name,
                           hypervisor_client=self.hypervisor_client,
                           disks=vm_data['disks'],
                           networks=vm_data['networks'],
                           edge_configuration=edge_configuration,
                           cd_path=vm_data['cd_path'])
        logger.info('Joining threads to wait for all VMs to be created')
        # Connection messages are filled by the prepare_vm_disks method
        vm_ip_info = self.threaded_server.wait_for_messages(messages=self.connection_messages, timeout=timeout)
        logger.info('Retrieving VM info, to verify correct creation of VMs ')
        for vm_name, vm_data in self.vm_info.iteritems():
            vm_data.update(vm_ip_info[vm_name])
        assert len(vm_ip_info.keys()) == len(self.vm_info.keys()), 'Not all VMs started.'
        logger.info('Finished creation of vms')
        return self.vm_info

    def _generate_cloud_init(self, client, convert_script_loc, create_msg, path=CLOUD_INIT_DATA['user-data_loc'],
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
            'sudo apt-get update',
            'sudo apt-get install fio -y',
            'sudo sed -ie "s/PermitRootLogin prohibit-password/PermitRootLogin yes/" /etc/ssh/sshd_config',
            'sudo sed -ie "s/PasswordAuthentication no/PasswordAuthentication yes/" /etc/ssh/sshd_config',
            'sudo service ssh restart',
            'sudo parted -s /dev/vdb mklabel gpt mkpart primary ext4 0% 100%',
            'sudo mkfs.ext4 /dev/vdb1',
            'sudo mkdir /mnt/data',
            'sudo mount /dev/vdb1 /mnt/data',
            'echo -n {0} | netcat -w 0 {1} {2}'.format(create_msg, self.hypervisor_ip, self.listening_port)

        ]
        with open(path, 'w') as user_data_file:
            user_data_file.write('\n'.join(lines))
        client.file_upload(path, path)

        # run script that generates meta-data and parser user-data and meta-data to a iso
        convert_cmd = [convert_script_loc, '--user-data', path, config_destination]
        try:
            client.run(convert_cmd)
            self.LOGGER.info('cloud data creation finished, sending message to {0}:{0}'.format(self.hypervisor_ip, self.listening_port))
            return config_destination
        except subprocess.CalledProcessError as ex:
            logger.error(
                'Could not generate the cloud init file on {0}. Got {1} during iso conversion.'.format(client.ip, str(ex.output)))
            raise

    @staticmethod
    def create_vm(hypervisor_client, disks, networks, edge_configuration, cd_path, vm_name, vcpus=VM_VCPUS, ram=VM_VRAM,
                  os_type=VM_OS_TYPE, logger=LOGGER):
        """
        Creates and wait for the VM to be fully connected
        :param hypervisor_client: hypervisor client instance
        :param disks: disk info
        :param networks: network info
        :param edge_configuration: edge info
        :param cd_path: cd info
        :param vcpus: number of virtual cpus
        :param ram: amount of ram
        :param vm_name: name of the vm
        :param os_type: type of the os
        :param logger: logging instance
        :return: None
        """
        logger.info('Creating VM `{0}`'.format(vm_name))
        hypervisor_client.sdk.create_vm(vm_name,
                                        vcpus=vcpus,
                                        ram=ram,
                                        cdrom_iso=cd_path,
                                        disks=disks,
                                        networks=networks,
                                        edge_configuration=edge_configuration,
                                        start=True,
                                        os_type=os_type)
        logger.info('Created VM `{0}`!'.format(vm_name))

    @staticmethod
    def cleanup_vm(hypervisor, vmid, blocking=True, logger=LOGGER):
        """
        Cleans up the created virtual machine
        :param hypervisor: hypervisor instance
        :param vmid: vm identifier
        :param blocking: boolean to determine whether errors should raise or not
        :param logger: logging instance
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
    def stop_vm(hypervisor, vmid, blocking=True, logger=LOGGER):
        """
        Stop the created virtual machine
        :param hypervisor: hypervisor instance
        :param vmid: vm identifier
        :param blocking: boolean to determine whether errors should raise or not
        :param logger: logging instance
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
    def start_vm(hypervisor, vmid, blocking=True, logger=LOGGER):
        """
        starts the created virtual machine
        :param hypervisor: hypervisor instance
        :param vmid: vm identifier
        :param blocking: boolean to determine whether errors should raise or not
        :param logger: logging instance
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
    def create_blktap_device(client, diskname, edge_info, logger=LOGGER):
        """
        Creates a blk tap device from a vdisk
        :return: blktap device location
        """
        required_edge_params = {'port': (int, {'min': 1, 'max': 65535}),
                                'protocol': (str, ['tcp', 'udp', 'rdma']),
                                'ip': (str, Toolbox.regex_ip),
                                'username': (str, None, False),
                                'password': (str, None, False)}
        ExtensionsToolbox.verify_required_params(required_edge_params, edge_info)
        if edge_info.get('username') and edge_info.get('password'):
            ovs_edge_connection = "openvstorage+{0}:{1}:{2}/{3}:username={4}:password={5}".format(edge_info['protocol'], edge_info['ip'],
                                                                                                  edge_info['port'], diskname,
                                                                                                  edge_info['username'], edge_info['password'])
        else:
            ovs_edge_connection = "openvstorage+{0}:{1}:{2}/{3}".format(edge_info['protocol'], edge_info['ip'], edge_info['port'], diskname)

        cmd = ["tap-ctl", "create", "-a", ovs_edge_connection]
        logger.debug('Creating blktap device: {}'.format(' '.join(cmd)))
        return client.run(cmd)

    @staticmethod
    def create_image(client, diskname, disk_size, edge_info, logger=LOGGER):
        """
        Creates an image file with qemu over edge connection with a particular seize
        :return: None
        """
        required_edge_params = {'port': (int, {'min': 1, 'max': 65535}),
                                'protocol': (str, ['tcp', 'udp', 'rdma']),
                                'ip': (str, Toolbox.regex_ip),
                                'username': (str, None, False),
                                'password': (str, None, False)}
        ExtensionsToolbox.verify_required_params(required_edge_params, edge_info)
        if edge_info.get('username') and edge_info.get('password'):
            ovs_edge_connection = "openvstorage+{0}:{1}:{2}/{3}:username={4}:password={5}".format(edge_info['protocol'], edge_info['ip'],
                                                                                                  edge_info['port'], diskname,
                                                                                                  edge_info['username'], edge_info['password'])
        else:
            ovs_edge_connection = "openvstorage+{0}:{1}:{2}/{3}".format(edge_info['protocol'], edge_info['ip'], edge_info['port'], diskname)

        cmd = ["qemu-img", "create", ovs_edge_connection, "{0}B".format(disk_size)]
        logger.debug('Converting an image with qemu using: {}'.format(' '.join(cmd)))
        client.run(cmd)

    @staticmethod
    def convert_image(client, image_location, diskname, edge_info, logger=LOGGER):
        """
        Converts an image file with qemu over edge connection
        :return: None
        """
        required_edge_params = {'port': (int, {'min': 1, 'max': 65535}),
                                'protocol': (str, ['tcp', 'udp', 'rdma']),
                                'ip': (str, Toolbox.regex_ip),
                                'username': (str, None, False),
                                'password': (str, None, False)}
        ExtensionsToolbox.verify_required_params(required_edge_params, edge_info)
        if edge_info.get('username') and edge_info.get('password'):
            ovs_edge_connection = "openvstorage+{0}:{1}:{2}/{3}:username={4}:password={5}".format(edge_info['protocol'],
                                                                                                  edge_info['ip'],
                                                                                                  edge_info['port'],
                                                                                                  diskname,
                                                                                                  edge_info['username'],
                                                                                                  edge_info['password'])
        else:
            ovs_edge_connection = "openvstorage+{0}:{1}:{2}/{3}".format(edge_info['protocol'], edge_info['ip'],
                                                                        edge_info['port'], diskname)
        cmd = ["qemu-img", "convert", image_location, ovs_edge_connection]
        logger.debug('Converting an image with qemu using: {}'.format(' '.join(cmd)))
        client.run(cmd)

    def destroy_vms(self, vm_info):
        for vm_name, vm_object in vm_info.iteritems():
            self.hypervisor_client.sdk.destroy(vm_name)
            VDiskRemover.remove_vdisks_with_structure(vm_object['vdisks'])
            self.hypervisor_client.sdk.undefine(vm_name)
