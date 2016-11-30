# Copyright 2014 iNuron NV
#
# Licensed under the Open vStorage Modified Apache License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.openvstorage.org/license
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
This module contains all code for using the KVM libvirt api
"""

import subprocess
import os
import re
import glob
import uuid
import time
import libvirt
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.generic.system import System
from ovs.log.log_handler import LogHandler
from xml.etree import ElementTree

logger = LogHandler.get('helpers', name='kvm sdk')
ROOT_PATH = '/etc/libvirt/qemu/'  # Get static info from here, or use dom.XMLDesc(0)
RUN_PATH = '/var/run/libvirt/qemu/'  # Get live info from here


# Helpers
def _recurse(treeitem):
    result = {}
    for key, item in treeitem.items():
        result[key] = item
    for child in treeitem.getchildren():
        result[child.tag] = _recurse(child)
        for key, item in child.items():
            result[child.tag][key] = item
        result[child.tag]['<text>'] = child.text
    return result


def authenticated(function):
    """
    Decorator that make sure all required calls are running onto a connected SDK
    """
    def new_function(self, *args, **kwargs):
        self.__doc__ = function.__doc__
        # determine if connection isn't closed.
        is_alive = 0
        try:
            is_alive = self._conn.isAlive()
        except libvirt.libvirtError as e:
            pass
        if self._conn is None or is_alive == 0:
            try:
                self._conn = self.connect(self.login, self.host)
            except:
                try:
                    self.disconnect(self._conn)
                except:
                    pass
                raise
        return function(self, *args, **kwargs)
    return new_function


class Sdk(object):
    """
    This class contains all SDK related methods
    """

    def __init__(self, host='127.0.0.1', login='root', passwd=None):
        logger.debug('Init libvirt')
        self.states = {libvirt.VIR_DOMAIN_NOSTATE: 'NO STATE',
                       libvirt.VIR_DOMAIN_RUNNING: 'RUNNING',
                       libvirt.VIR_DOMAIN_BLOCKED: 'BLOCKED',
                       libvirt.VIR_DOMAIN_PAUSED: 'PAUSED',
                       libvirt.VIR_DOMAIN_SHUTDOWN: 'SHUTDOWN',
                       libvirt.VIR_DOMAIN_SHUTOFF: 'TURNEDOFF',
                       libvirt.VIR_DOMAIN_CRASHED: 'CRASHED'}
        pattern = re.compile(r"^(?<!\S)((\d|[1-9]\d|1\d\d|2[0-4]\d|25[0-5])\b|\.\b){7}(?!\S)$")
        if pattern.match(host):
            self.host = host
        else:
            raise ValueError("{0} is not a valid ip.".format(host))
        self.host = host
        self.login = login
        self.ssh_client = SSHClient(host, login, passwd)
        self._conn = self.connect(login, host)

        logger.debug('Init complete')

    def __del__(self):
        """
        Class destructor
        :return:
        """
        try:
            self.disconnect(self._conn)
        except Exception:
            # Absord destructor exceptions
            pass
        pass

    def test_connection(self):
        pass

    def connect(self, login=None, host=None):
        """
        Connects to a kvm hypervisor
        :param login: username
        :param host: ip
        :return: connection object
        """
        _ = self
        conn = None
        logger.debug('Init connection: {0}, {1}, {2}, {3}'.format(host, login, os.getgid(), os.getuid()))
        try:
            if login == '127.0.0.1':
                conn = libvirt.open('qemu:///system')
            else:
                conn = libvirt.open('qemu+ssh://{0}@{1}/system'.format(login, host))
        except libvirt.libvirtError as le:
            logger.error('Error during connect: %s (%s)', str(le), le.get_error_code())
            raise
        return conn

    def disconnect(self, conn=None):
        _ = self
        logger.debug('Disconnecting libvirt')
        if conn:
            try:
                conn.close()
            except libvirt.libvirtError as le:
                # Ignore error, connection might be already closed
                logger.error('Error during disconnect: {0} ({1})'.format(str(le), le.get_error_code()))
        return None

    @staticmethod
    def _get_disks(vm_object):
        tree = ElementTree.fromstring(vm_object.XMLDesc(0))
        return [_recurse(item) for item in tree.findall('devices/disk')]

    @staticmethod
    def _get_nics(vm_object):
        tree = ElementTree.fromstring(vm_object.XMLDesc(0))
        return [_recurse(item) for item in tree.findall('devices/interface')]

    @staticmethod
    def _get_nova_name(vm_object):
        tree = ElementTree.fromstring(vm_object.XMLDesc(0))
        metadata = tree.findall('metadata')[0]
        nova_instance_namespace_tag = metadata.getchildren()[0].tag
        nova_instance_namespace = nova_instance_namespace_tag[nova_instance_namespace_tag.find('{') + 1:nova_instance_namespace_tag.find('}')]
        instance = metadata.findall('{%s}instance' % nova_instance_namespace)[0]
        name = instance.findall('{%s}name' % nova_instance_namespace)[0]
        return name.text

    @staticmethod
    def _get_ram(vm_object):
        """
        returns RAM size in MiB
        MUST BE INTEGER! not float
        """
        tree = ElementTree.fromstring(vm_object.XMLDesc(0))
        mem = tree.findall('memory')[0]
        unit = mem.items()[0][1]
        value = mem.text
        if unit == 'MiB':
            return int(value)
        elif unit == 'KiB':
            return int(value) / 1024
        elif unit == 'GiB':
            return int(value) * 1024

    def _get_disk_size(self, filename):
        """
        Gets the size of the disk
        :param filename: path to the disk
        :return: size
        """
        cmd = ['qemu-img', 'info', filename]
        try:
            out = self.ssh_client.run(' '.join(cmd), stderr=subprocess.STDOUT, shell=True)
            for line in out.split('\n'):
                if line.startswith('virtual size: '):
                    size = line.split('virtual size: ')[1].split(' ')[0]
                    return size
        except subprocess.CalledProcessError as ex:
            logger.error('Could not fetch disk size for {0}. Got {1}'.format(filename, str(ex)))
            raise

    def _get_vm_pid(self, vm_object):
        """
        return pid of kvm process running this machine (if any)
        """
        if self.get_power_state(vm_object.name()) == 'RUNNING':
            pid_path = '{0}/{1}.pid'.format(RUN_PATH, vm_object.name())
            try:
                with open(pid_path, 'r') as pid_file:
                    pid = pid_file.read()
                return int(pid)
            except IOError:
                # vMachine is running but no run file?
                return '-1'
        return '-2'  # No pid, machine is halted

    def make_agnostic_config(self, vm_object):
        """
        return an agnostic config (no hypervisor specific type or structure)
        """
        regex = '/mnt/([^/]+)/(.+$)'
        config = {'disks': []}
        mountpoints = []

        order = 0
        for disk in Sdk._get_disks(vm_object):
            # Skip cdrom/iso
            if disk['device'] == 'cdrom':
                continue

            # Load backing filename
            if 'file' in disk['source']:
                backingfilename = disk['source']['file']
            elif 'dev' in disk['source']:
                backingfilename = disk['source']['dev']
            else:
                continue
            match = re.search(regex, backingfilename)
            if match is None:
                continue

            # Cleaning up
            mountpoint = '/mnt/{0}'.format(match.group(1))
            filename = backingfilename.replace(mountpoint, '').strip('/')
            diskname = filename.split('/')[-1].split('.')[0]

            # Collecting data
            config['disks'].append({'filename': filename,
                                    'backingfilename': filename,
                                    'datastore': mountpoint,
                                    'name': diskname,
                                    'order': order})
            order += 1
            mountpoints.append(mountpoint)

        vm_filename = self.ssh_client.run("grep -l '<uuid>{0}</uuid>' {1}*.xml".format(vm_object.UUIDString(), ROOT_PATH))
        vm_filename = vm_filename.strip().split('/')[-1]
        vm_location = System.get_my_machine_id(self.ssh_client)
        vm_datastore = None
        possible_datastores = self.ssh_client.run("find /mnt -name '{0}'".format(vm_filename)).split('\n')
        for datastore in possible_datastores:
            # Filter results so only the correct machineid/xml combinations are left over
            if '{0}/{1}'.format(vm_location, vm_filename) in datastore.strip():
                for mountpoint in mountpoints:
                    if mountpoint in datastore.strip():
                        vm_datastore = mountpoint

        try:
            config['name'] = self._get_nova_name(vm_object)
        except Exception as ex:
            logger.debug('Cannot retrieve nova:name {0}'.format(ex))
            # not an error, as we have a fallback, but still keep logging for debug purposes
            config['name'] = vm_object.name()
        config['id'] = str(vm_object.UUIDString())
        config['backing'] = {'filename': '{0}/{1}'.format(vm_location, vm_filename),
                             'datastore': vm_datastore}
        config['datastores'] = dict((mountpoint, '{}:{}'.format(self.host, mountpoint)) for mountpoint in mountpoints)

        return config

    def get_power_state(self, vmid):
        """
        return vmachine state
        vmid is the name
        """
        vm = self.get_vm_object(vmid)
        state = vm.info()[0]
        return self.states.get(state, 'UNKNOWN')

    @authenticated
    def get_vm_object(self, vmid):
        """
        return virDomain object representing virtual machine
        vmid is the name or the uuid
        cannot use ID, since for a stopped vm id is always -1
        """
        try:
            uuid.UUID(vmid)
            is_uuid = True
        except ValueError:
            # not a uuid
            is_uuid = False
        try:
            if is_uuid is True:
                return self._conn.lookupByUUIDString(vmid)
            else:
                return self._conn.lookupByName(vmid)
        except libvirt.libvirtError as ex:
            logger.error(str(ex))
            raise RuntimeError('Virtual Machine with id/name {0} could not be found.'.format(vmid))

    def get_vm_object_by_filename(self, filename):
        """
        get vm based on filename: vmachines/template/template.xml
        """
        vmid = filename.split('/')[-1].replace('.xml', '')
        return self.get_vm_object(vmid)

    def get_vms(self):
        """
        return a list of virDomain objects, representing virtual machines
        """
        return self._conn.listAllDomains()

    def shutdown(self, vmid):
        vm_object = self.get_vm_object(vmid)
        vm_object.shutdown()
        return self.get_power_state(vmid)

    def delete_vm(self, vmid, devicename, disks_info):
        """
        Delete domain from libvirt and try to delete all files from vpool (xml, .raw)
        :param vmid: id of the vm. Could also be the name
        :param devicename: name of the device to delete
        :param disks_info: info about the disks (agnostics)
        :return:
        """
        vm_object = None
        try:
            vm_object = self.get_vm_object(vmid)
        except Exception as ex:
            logger.error('SDK domain retrieve failed: {0}'.format(ex))
        # Flow of kvm delete
        # virsh destroy _domain-id_
        # virsh undefine _domain-id_
        # virsh vol-delete --pool vg0 _domain-id_.img
        found_files = self.find_devicename(devicename)
        if found_files is not None:
            for found_file in found_files:
                self.ssh_client.file_delete(found_file)
                logger.info('File on vpool deleted: {0}'.format(found_file))
        if vm_object:
            found_file = None
            # VM partially created, most likely we have disks
            for disk in self._get_disks(vm_object):
                if disk['device'] == 'cdrom':
                    continue
                if 'file' in disk['source']:
                    found_file = disk['source']['file']
                elif 'dev' in disk['source']:
                    found_file = disk['source']['dev']
                if found_file and os.path.exists(found_file) and os.path.isfile(found_file):
                    self.ssh_client.file_delete(found_file)
                    logger.info('File on vpool deleted: {0}'.format(found_file))
            vm_object.undefine()
        elif disks_info:
            # VM not created, we have disks to rollback
            for path, devicename in disks_info:
                found_file = '{}/{}'.format(path, devicename)
                if os.path.exists(found_file) and os.path.isfile(found_file):
                    self.ssh_client.file_delete(found_file)
                    logger.info('File on vpool deleted: {0}'.format(found_file))
        return True

    def power_on(self, vmid):
        """
        Powers on a libvirt domain
        :param vmid: id or name of the domain
        :return: powerstate of the vm
        """
        vm_object = self.get_vm_object(vmid)
        vm_object.create()
        return self.get_power_state(vmid)

    def find_devicename(self, devicename):
        """
        Searched for a given devicename
        :param devicename: name of the device
        """
        _ = self
        file_matcher = '/mnt/*/{0}'.format(devicename)
        matches = []
        for found_file in glob.glob(file_matcher):
            if os.path.exists(found_file) and os.path.isfile(found_file):
                matches.append(found_file)
        return matches if matches else None

    def is_datastore_available(self, mountpoint):
        if self.ssh_client is None:
            self.ssh_client = SSHClient(self.host, username='root')
        return self.ssh_client.run("[ -d {0} ] && echo 'yes' || echo 'no'".format(mountpoint)) == 'yes'

    def clone_vm(self, vmid, name, disks, mountpoint):
        """
        create a clone vm
        similar to create_vm_from template
        """
        source_vm = self.get_vm_object(vmid)
        return self.create_vm_from_template(name, source_vm, disks, mountpoint)

    def create_vm_from_template(self, name, source_vm, disks, mountpoint):
        """
        Create a vm based on an existing template on specified hypervisor
        :param name: name of the vm to be created
        :param source_vm: vm object of the source
        :param disks: list of dicts (agnostic) eg. {'diskguid': new_disk.guid, 'name': new_disk.name, 'backingdevice': device_location.strip('/')}
        :param mountpoint: location for the vm

         kvm doesn't have datastores, all files should be in /mnt/vpool_x/name/ and shared between nodes
         to "migrate" a kvm machine just symlink the xml on another node and use virsh define name.xml to reimport it
         (assuming that the vpool is in the same location)
        :return:
        """
        vm_disks = []

        # Get agnostic config of source vm
        if hasattr(source_vm, 'config'):
            vcpus = source_vm.config.hardware.numCPU
            ram = source_vm.config.hardware.memoryMB
        elif isinstance(source_vm, libvirt.virDomain):
            vcpus = source_vm.info()[3]
            ram = Sdk._get_ram(source_vm)
        else:
            raise ValueError('Unexpected object type {} {}'.format(source_vm, type(source_vm)))

        # Get nics of source ram - for now only KVM
        networks = []
        for nic in Sdk._get_nics(source_vm):
            if nic.get('type', None) == 'network':
                source = nic.get('source', {}).get('network', 'default')
                model = nic.get('model', {}).get('type', 'e1000')
                networks.append(('network={0}'.format(source), 'mac=RANDOM', 'model={0}'.format(model)))
                # MAC is always RANDOM

        # Assume disks are raw
        for disk in disks:
            vm_disks.append(('/{}/{}'.format(mountpoint.strip('/'), disk['backingdevice'].strip('/')), 'virtio'))

        self._vm_create(name=name, vcpus=vcpus, ram=int(ram), disks=vm_disks, networks=networks)

        try:
            return self.get_vm_object(name).UUIDString()
        except libvirt.libvirtError as le:
            logger.error(str(le))
            try:
                return self.get_vm_object(name).UUIDString()
            except libvirt.libvirtError as le:
                logger.error(str(le))
                raise RuntimeError('Virtual Machine with id/name {} could not be found.'.format(name))

    def _vm_create(self, name, vcpus, ram, disks, cdrom_iso=None, os_type=None, os_variant=None, vnc_listen='0.0.0.0',
                   networks=None, start=False):
        """
        Creates a VM
        @TODO use Edge instead of fuse for disks
        :param name: name of the vm
        :param vcpus: number of cpus
        :param ram: number of ram (MB)
        :param disks: list of tuples : [(disk_name, disk_size_GB, bus ENUM(virtio, ide, sata)]
        when using existing storage, size can be ommited [(/vms/vm1.raw,,virtio)]
        :param cdrom_iso: path to the iso the mount
        :param os_type: type of os
        :param os_variant: variant of the os
        :param vnc_listen:
        :param networks: lists of tuples : ("network=default", "mac=RANDOM" or a valid mac, "model=e1000" (any model for vmachines)
        :param start: start the guest after creation
        :return:
        """
        if networks is None:
            networks = [("network=default", "mac=RANDOM", "model=e1000")]
        command = ["virt-install"]
        options = ["--connect qemu+ssh://{}@{}/system".format(self.login, self.host),
                   "--name {}".format(name),
                   "--vcpus {}".format(vcpus),
                   "--ram {}".format(ram),
                   "--graphics vnc,listen={0}".format(vnc_listen)]  # Have to specify 0.0.0.0 else it will listen on 127.0.0.1 only

        for disk in disks:
            if len(disk) == 2:
                options.append("--disk {0},device=disk,bus={1}".format(*disk))
            else:
                options.append("--disk {0},device=disk,size={1},bus={2}".format(*disk))
        if cdrom_iso is None:
            options.append("--import")
        else:
            options.append("--cdrom {0}".format(cdrom_iso))
        if os_type is not None:
            options.append("--os-type {0}".format(os_type))
        if os_variant is not None:
            options.append("-- os-variant {0}".format(os_variant))
        if networks is None or networks == []:
            options.append("--nonetworks")
        else:
            for network in networks:
                options.append("--network {0}".format(",".join(network)))
        try:
            cmd = Sdk.shell_safe(" ".join(command + options))
            self.ssh_client.run(cmd, allow_insecure=True)
        except subprocess.CalledProcessError as ex:
            logger.exception("Error during creation of VM")
            print " ".join(command+options)
            raise
        if start is False:
            cmd = ["virsh", "destroy", name]
            self.ssh_client.run(cmd)

    @authenticated
    def migrate(self, vmid, d_ip, d_login, flags=libvirt.VIR_MIGRATE_LIVE, bandwidth=0):
        """
        Live migrates a vm by default
        :param vmid: identifier of the vm to migrate (name or id)
        :param d_ip: ip of the destination hypervisor
        :param d_login: login of the destination hypervisor
        :param flags: Flags to supply
        :param bandwith: limit the bandwith to MB/s
        :return:
        """
        vm = self.get_vm_object(vmid)
        dconn = self.connect(login=d_login, host=d_ip)
        if dconn is None:
            raise RuntimeError("Could not connect to {0}".format(d_ip))
        try:
            dom = vm.migrate(dconn=dconn, flags=flags, bandwidth=bandwidth)
            if dom is None:
                raise RuntimeError("Could not migrate the VM to {0}".format(d_ip))
        except libvirt.libvirtError as ex:
            raise RuntimeError("Could not migrate the VM to {0}. Got '{1}'".format(d_ip, str(ex)))

    @staticmethod
    def shell_safe(argument):
        """
        Makes sure that the given path/string is escaped and safe for shell
        :param argument: Argument to make safe for shell
        """
        return "{0}".format(argument.replace(r"'", r"'\''"))

if __name__ == "__main__":
    # Had to change the user to root in /etc/libvirt/qemu.conf
    sdk = Sdk(login='root', host='10.100.199.151', passwd='rooter')
    sdk.migrate('bob2', '10.100.199.152', 'root')
    # disks = [('/mnt/myvpool01/myvdisk01.raw', 'sata')]
    # networks = [("network=default", 'mac=RANDOM', 'model=e1000')]
    # sdk._vm_create('bob2', 2, 1024, disks, networks=networks)
