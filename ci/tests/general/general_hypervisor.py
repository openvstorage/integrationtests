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

"""
A general class dedicated to Hypervisor logic
"""

import os
import re
import time
import urllib
import logging
import urlparse
from ci.tests.general.general import General
from ci.tests.general.general_openstack import GeneralOpenStack
from ci.tests.general.general_pmachine import GeneralPMachine
from ci.tests.general.general_vmachine import GeneralVMachine
from ovs.extensions.hypervisor.hypervisors.kvm import Sdk as Kvm_sdk
from ovs.extensions.hypervisor.hypervisors.vmware import Sdk as Vmware_sdk
from ovs.lib.helpers.toolbox import Toolbox
from ovs.lib.vdisk import VDiskController
from xml.dom import minidom


class GeneralHypervisor(object):
    """
    A general class dedicated to Hypervisor logic
    """
    @staticmethod
    def download_to_vpool(url, path, overwrite_if_exists=False):
        """
        Special method to download to vpool because voldrv does not support extending file at write
        :param url: URL to download from
        :param path: Path to download to
        :param overwrite_if_exists: Overwrite if file already exists
        :return: None
        """
        print url
        print path
        if os.path.exists(path) and not overwrite_if_exists:
            return
        u = urllib.urlopen(url)
        file_size = u.info()['Content-Length']
        bsize = 4096 * 1024
        VDiskController.create_volume(path, 0)
        with open(path, "wb") as f:
            size_written = 0
            os.ftruncate(f.fileno(), int(file_size))
            while 1:
                s = u.read(bsize)
                size_written += len(s)
                f.write(s)
                if len(s) < bsize:
                    break
        u.close()

    @staticmethod
    def get_hypervisor_info():
        """
        Retrieve info about hypervisor (ip, username, password)
        """
        config = General.get_config()
        # @TODO: Split these settings up in separate section or at least in 3 separate values in main
        hi = config.get(section='main', option='hypervisorinfo')
        hpv_list = hi.split(',')
        if not len(hpv_list) == 3:
            raise RuntimeError('No hypervisor info present in config')
        return hpv_list

    @staticmethod
    def set_hypervisor_info(ip, username, password):
        """
        Set info about hypervisor( ip, username and password )

        :param ip:         IP address of hypervisor
        :type ip:          String

        :param username:   Username for hypervisor
        :type username:    String

        :param password:   Password of hypervisor
        :type password:    String

        :return:           None
        """
        if not re.match(Toolbox.regex_ip, ip):
            print 'Invalid IP address specified'
            return False

        if type(username) != str or type(password) != str:
            print 'Username and password need to be str format'
            return False

        value = ','.join([ip, username, password])
        config = General.get_config()
        config.set(section='main', option='hypervisorinfo', value=value)
        General.save_config(config)
        return True


class Hypervisor(object):
    """
    Wrapper class for VMWare and KVM hypervisor classes
    """
    # Disable excessive logging
    logging.getLogger('suds.client').setLevel(logging.WARNING)
    logging.getLogger('suds.transport').setLevel(logging.WARNING)
    logging.getLogger('suds.xsd.schema').setLevel(logging.WARNING)
    logging.getLogger('suds.wsdl').setLevel(logging.WARNING)
    logging.getLogger('suds.resolver').setLevel(logging.WARNING)
    logging.getLogger('suds.xsd.query').setLevel(logging.WARNING)
    logging.getLogger('suds.xsd.basic').setLevel(logging.WARNING)
    logging.getLogger('suds.xsd.sxbasic').setLevel(logging.WARNING)
    logging.getLogger('suds.binding.marshaller').setLevel(logging.WARNING)
    logging.getLogger('suds.mx.literal').setLevel(logging.WARNING)
    logging.getLogger('suds.mx.core').setLevel(logging.WARNING)
    logging.getLogger('suds.sudsobject').setLevel(logging.WARNING)
    logging.getLogger('suds.metrics').setLevel(logging.WARNING)
    logging.getLogger('suds.xsd.sxbase').setLevel(logging.WARNING)
    logging.getLogger('plumbum.shell').setLevel(logging.WARNING)
    logging.getLogger('plumbum.local').setLevel(logging.WARNING)

    @staticmethod
    def get(vpool):
        """
        Retrieve the correct hypervisor class
        :param vpool: vPool DAL object
        :return: Specific hypervisor class
        """
        if len(vpool.storagedrivers) == 0:
            raise ValueError('No Storage Drivers found on vPool {0}'.format(vpool.name))

        htype = GeneralPMachine.get_hypervisor_type()
        if htype == 'VMWARE':
            return Vmware(vpool)
        else:
            return Kvm(vpool)


class Vmware(object):
    """
    VMWare specific hypervisor class
    """
    def __init__(self, vpool):
        self.vpool = vpool
        self.mountpoint = '/mnt/{0}'.format(vpool.name)
        self.sdk = Vmware_sdk(*GeneralHypervisor.get_hypervisor_info())

    def create_vm(self, name, cpus=1, ram=1024):
        """
        Create a Virtual Machine on hypervisor and start it
        :param name: Name of the Virtual Machine
        :param cpus: Amount of CPUs
        :param ram: Amount of RAM
        :return: None
        """
        # not sure if its the proper way to get the datastore
        esxhost = self.sdk._validate_host(None)
        datastores = self.sdk._get_object(esxhost, properties=['datastore']).datastore.ManagedObjectReference
        datastore = [d for d in datastores if self.vpool.name in d.value]
        assert datastore, "Did not found datastore"
        datastore = self.sdk._get_object(datastore[0])

        os_name = General.get_os()
        os_info = General.get_os_info(os_name)
        bootdisk_path_remote = os_info['bootdisk_location']

        os.mkdir('/'.join([self.mountpoint, name]))

        disk_name = "bootdisk.vmdk"
        disk_name_flat = "bootdisk-flat.vmdk"
        bootdisk_path = '/'.join([self.mountpoint, name, disk_name])
        bootdisk_flat_path = '/'.join([self.mountpoint, name, disk_name_flat])

        template_server = General.get_template_server()
        bootdisk_url = urlparse.urljoin(template_server, bootdisk_path_remote + disk_name)
        bootdisk_flat_url = urlparse.urljoin(template_server, bootdisk_path_remote + disk_name_flat)

        GeneralHypervisor.download_to_vpool(bootdisk_url, bootdisk_path)
        GeneralHypervisor.download_to_vpool(bootdisk_flat_url, bootdisk_flat_path)
        """
        task = self.sdk.create_vm(name      = name,
                                  cpus      = cpus,
                                  memory    = ram,
                                  os        = os_info['esx_os_name'],
                                  disks     = [],
                                  nics      = [{'bridge': 'CloudFramesPublic'}],
                                  kvmport   = str(random.randint(0, 100000)),
                                  datastore = datastore.info.name,
                                  wait      = True)
        self.sdk.validate_result(task)
        """

        nics = [{'bridge': 'CloudFramesPublic'}]

        self.sdk._validate_host(None)

        # Build basic config information
        config = self.sdk._client.factory.create('ns0:VirtualMachineConfigSpec')
        config.name = name
        config.numCPUs = cpus
        config.memoryMB = ram
        config.guestId = os_info.get('esx_os_name', 'ubuntu64Guest')
        config.deviceChange = []
        config.extraConfig = []
        config.files = self.sdk._create_file_info(self.sdk._client.factory, datastore.name)

        disk_controller_key = -101
        config.deviceChange.append(
            self.sdk._create_disk_controller(self.sdk._client.factory, disk_controller_key))

        # Add network
        for nic in nics:
            unit = nics.index(nic)
            config.deviceChange.append(self.sdk._create_nic(self.sdk._client.factory,
                                                            'VirtualE1000',
                                                            'Interface %s' % unit,
                                                            '%s interface' % nic['bridge'],
                                                            nic['bridge'],
                                                            unit))

        # Change additional properties
        extra_configs = [
            ('pciBridge0.present', 'true'),
            ('pciBridge4.present', 'true'),
            ('pciBridge4.virtualDev', 'pcieRootPort'),
            ('pciBridge4.functions', '8'),
            ('pciBridge5.present', 'true'),
            ('pciBridge5.virtualDev', 'pcieRootPort'),
            ('pciBridge5.functions', '8'),
            ('pciBridge6.present', 'true'),
            ('pciBridge6.virtualDev', 'pcieRootPort'),
            ('pciBridge6.functions', '8'),
            ('pciBridge7.present', 'true'),
            ('pciBridge7.virtualDev', 'pcieRootPort'),
            ('pciBridge7.functions', '8')
        ]
        for item in extra_configs:
            config.extraConfig.append(
                self.sdk._create_option_value(self.sdk._client.factory,
                                              item[0],
                                              item[1]))

        retries = 100
        vm = None
        while retries:
            vm_objects = self._get_vms()

            vm = [vm for vm in vm_objects if vm['name'] == name]
            if vm:
                vm = vm[0]
                if getattr(vm, "config", None):
                    break
            retries -= 1
            time.sleep(1)

        assert vm, "Did not found vm after creating it"

        vm_dir_name = vm.config.files.vmPathName.split()[1].split("/")[0]
        virt_ide_controller = [dev for dev in vm.config.hardware.device if "VirtualIDEController" in str(type(dev))][0]

        sdk_client = self.sdk._client
        vm_spec = sdk_client.factory.create('ns0:VirtualMachineConfigSpec')

        unit = 0
        device_info = sdk_client.factory.create('ns0:Description')
        device_info.label = disk_name
        device_info.summary = disk_name

        backing = sdk_client.factory.create('ns0:VirtualDiskFlatVer2BackingInfo')
        backing.diskMode = 'persistent'
        backing.fileName = '[{datastore}] {fileName}'.format(datastore=datastore.info.name,
                                                             fileName='/'.join([vm_dir_name, disk_name]))

        device = sdk_client.factory.create('ns0:VirtualDisk')
        device.controllerKey = virt_ide_controller.key
        device.key = -200 - unit
        device.unitNumber = unit
        device.deviceInfo = device_info
        device.backing = backing

        disk_spec = sdk_client.factory.create('ns0:VirtualDeviceConfigSpec')
        disk_spec.operation = 'add'
        disk_spec.fileOperation = None
        disk_spec.device = device
        vm_spec.deviceChange.append(disk_spec)

        task = sdk_client.service.ReconfigVM_Task(vm.obj_identifier, vm_spec)
        self.sdk.wait_for_task(task)
        self.sdk.validate_result(task)

        self.start(name)

    def _get_vms(self):
        esxhost = self.sdk._validate_host(None)
        return self.sdk._get_object(esxhost,
                                    prop_type='VirtualMachine',
                                    traversal={'name': 'HostSystemTraversalSpec',
                                               'type': 'HostSystem',
                                               'path': 'vm'})

    def start(self, name):
        """
        Start a Virtual Machine
        :param name: Name of the Virtual Machine
        :return: None
        """
        vms = self._get_vms()
        vm = [v for v in vms if v.name == name]
        assert vm, "Vm with name {0} not found".format(name)
        vm = vm[0]
        if vm.runtime.powerState == "poweredOn":
            return

        task = self.sdk._client.service.PowerOnVM_Task(vm.obj_identifier)
        self.sdk.wait_for_task(task)
        self.sdk.validate_result(task)

    def shutdown(self, name):
        """
        Shut down a Virtual Machine
        :param name: Name of the Virtual Machine
        :return: None
        """
        vms = self._get_vms()
        vm = [v for v in vms if v.name == name]
        assert vm, "Vm with name {0} not found".format(name)
        vm = vm[0]
        if vm.runtime.powerState == "poweredOff":
            return
        task = self.sdk._client.service.PowerOffVM_Task(vm.obj_identifier)
        self.sdk.wait_for_task(task)
        self.sdk.validate_result(task)

    def poweroff(self, name):
        """
        Power off a Virtual Machine
        :param name: Name of the Virtual Machine
        :return: None
        """
        self.shutdown(name=name)

    def delete_clones(self, vm):
        """
        Delete all clones for Virtual Machine with name
        :param vm: Virtual Machine DAL object
        :return: None
        """
        clones = set()
        for vd in vm.vdisks:
            for child_vd in vd.child_vdisks:
                if child_vd.vmachine:
                    clones.add(child_vd.vmachine)
        for clone in clones:
            self.delete(clone.name)

    def delete(self, name):
        """
        Delete a Virtual Machine
        :param name: Name of the Virtual Machine
        :return: None
        """
        vms = self._get_vms()
        vm = [v for v in vms if v.name == name]
        assert vm, "Vm with name {0} not found".format(name)
        vm = vm[0]
        logging.log(1, "Powering off vm: {0}:".format(vm.name))
        self.poweroff(name)
        logging.log(1, "Deleting vm: {0}:".format(vm.name))
        task = self.sdk._client.service.Destroy_Task(vm.obj_identifier)
        self.sdk.wait_for_task(task)
        self.sdk.validate_result(task)
        logging.log(1, "Deleted vm: {0}:".format(vm.name))


class Kvm(object):
    """
    KVM specific hypervisor class
    """
    def __init__(self, vpool):
        self.vpool = vpool
        self.mountpoint = list(vpool.storagedrivers)[0].mountpoint
        self.sdk = Kvm_sdk()

    def create_vm(self, name, ram=1024, small=False):
        """
        Create a Virtual Machine
        :param name: Name of the Virtual Machine
        :param ram: Amount of RAM
        :param small: Small
        :return: None
        """
        os_name = General.get_os()
        bootdisk_path_remote = General.get_os_info(os_name + '_small' if small else os_name)['bootdisk_location']

        vm_path = '/'.join([self.mountpoint, name])
        if not os.path.exists(vm_path):
            os.mkdir(vm_path)

        if small:
            bootdisk_path = '/'.join([self.mountpoint, name, "bootdiskfast.raw"])
        else:
            bootdisk_path = '/'.join([self.mountpoint, name, "bootdisk.raw"])
        if not os.path.exists(bootdisk_path):
            template_server = General.get_template_server()
            bootdisk_url = urlparse.urljoin(template_server, bootdisk_path_remote)
            logging.log(1, 'Template url: {0}'.format(bootdisk_url))
            logging.log(1, 'Bootdisk path: {0}'.format(bootdisk_path))

            GeneralHypervisor.download_to_vpool(bootdisk_url, bootdisk_path)

            # When running with devstack need to set kvm group
            if GeneralOpenStack.is_openstack_present():
                General.execute_command("chgrp kvm {0}".format(bootdisk_path))

            cmd = "virt-install --connect qemu:///system -n {name} -r {ram} --disk {bootdisk_path},device=disk,format=raw,bus=virtio --import --graphics vnc,listen=0.0.0.0 --vcpus=1 --network network=default,mac=RANDOM,model=e1000 --boot hd"
            cmd = cmd.format(name=name,
                             bootdisk_path=bootdisk_path,
                             ram=ram)
            out, error, _ = General.execute_command(cmd)
            logging.log(1, 'cmd: ---')
            logging.log(1, cmd)
            logging.log(1, 'stdout: ---')
            logging.log(1, 'stdout: ---')
            logging.log(1, out)
            logging.log(1, 'stderr: ---')
            logging.log(1, error)
            # assert error == '', "Exception occurred while running {0}:\n{1}\n{2}".format(cmd, out, error)

    def _wait_for_state(self, name, state):
        retries = 240

        while retries:
            if self.sdk.get_power_state(name) == state:
                return
            retries -= 1
            time.sleep(1)

        actual_state = self.sdk.get_power_state(name)
        assert actual_state == state, "Vm did not go into state {0}, actual {1}".format(state, actual_state)

    def shutdown(self, name):
        """
        Shut down a Virtual Machine
        :param name: Name of the Virtual Machine
        :return: None
        """
        if self.sdk.get_power_state(name) == 'TURNEDOFF':
            return
        self.sdk.shutdown(name)
        self._wait_for_state(name, 'TURNEDOFF')

    def poweroff(self, name):
        """
        Power off a Virtual Machine
        :param name: Name of the Virtual Machine
        :return: None
        """
        if self.sdk.get_power_state(name) == 'TURNEDOFF':
            return
        vm_obj = self.sdk.get_vm_object(name)
        vm_obj.destroy()

    def start(self, name):
        """
        Start a Virtual Machine
        :param name: Name of the Virtual Machine
        :return: None
        """
        if self.sdk.get_power_state(name) == 'RUNNING':
            print "Vm {} already running".format(name)
            return
        self.sdk.power_on(name)
        self._wait_for_state(name, 'RUNNING')

    def get_mac_address(self, name):
        """
        Retrieve a MAC address of a Virtual Machine
        :param name: Name of the Virtual Machine
        :return:
        """
        vmo = self.sdk.get_vm_object(name)
        dom = minidom.parseString(vmo.XMLDesc()).childNodes[0]
        devices = [e for e in dom.childNodes if e.localName == 'devices'][0]
        nic = [e for e in devices.childNodes if e.localName == 'interface'][0]
        mac = [e for e in nic.childNodes if e.localName == 'mac'][0]
        return mac.attributes['address'].value

    def delete_clones(self, vm):
        """
        Delete all clones for Virtual Machine with name
        :param vm: Virtual Machine DAL object
        :return: None
        """
        clones = set()
        for vd in vm.vdisks:
            for child_vd in vd.child_vdisks:
                if child_vd.vmachine:
                    clones.add(child_vd.vmachine)
        for clone in clones:
            self.delete(clone.name)

    def delete(self, name):
        """
        Delete a Virtual Machine
        :param name: Name of the Virtual Machine
        :return: None
        """
        vm = GeneralVMachine.get_vmachine_by_name(name)
        assert vm, "Couldn't find Virtual Machine with name {0}".format(name)
        assert len(vm) == 1, "More than 1 result when looking up vmachine with name: {0}".format(name)

        logging.log(1, "Powering off vm: {0}".format(vm.name))
        self.poweroff(name)
        logging.log(1, "Deleting off vm: {0}".format(vm.name))
        self.sdk.delete_vm(name, vm.devicename, None)
        logging.log(1, "Deleted vm: {0}".format(vm.name))
