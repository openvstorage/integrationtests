import os
import time
import paramiko
import urllib
import urlparse
import random
from xml.dom import minidom

from ci import autotests
import general

from ovs.dal.lists.vpoollist import VPoolList
from ovs.dal.lists.vmachinelist import VMachineList
from ovs.dal.lists.pmachinelist import PMachineList
from ovs.extensions.hypervisor.hypervisors.kvm import Sdk as Kvm_sdk
from ovs.extensions.hypervisor.hypervisors.vmware import Sdk as Vmware_sdk

import logging
#disable excesive logging
logging.getLogger('suds.client').setLevel(logging.WARNING)
logging.getLogger('suds.transport').setLevel(logging.WARNING) # MUST BE THIS?
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

PUBLIC_BRIDGE_NAME_ESX = "CloudFramesPublic"

class Hypervisor(object):
    @staticmethod
    def get(vpool_name, htype = None):
        vpool = [v for v in VPoolList.get_vpools() if v.name == vpool_name]
        assert vpool, "Vpool with name {} not found".format(vpool_name)
        vpool = vpool[0]

        htype = htype or get_hypervisor_type()
        if htype == "VMWARE":
            return Vmware(vpool)
        elif htype == "KVM":
            return Kvm(vpool)
        else:
            raise Exception("{} not implemented".format(htype))

def _download_to_vpool(url, path, overwrite_if_exists = False):
    """
    special method to download to vpool because voldrv does not support extending file at write
    """
    print url
    print path
    if os.path.exists(path) and not overwrite_if_exists:
        return
    u = urllib.urlopen(url)
    bsize = 4096 * 1024
    with open(path, "w") as f:

        size_written = 0
        while 1:
            s = u.read(bsize)
            size_written += len(s)
            os.ftruncate(f.fileno(), size_written)
            f.write(s)
            if len(s) < bsize:
                break
    u.close()

def get_hypervisor_type():
    return PMachineList.get_pmachines()[0].hvtype

def _xml_get_child(dom, name):
    c = [e for e in dom.childNodes if e.localName == name]
    return c

def get_vm_ip_from_mac(mac):
    ip = general.get_virbr_ip()
    cmd = "nmap -sP {ip} >/dev/null && arp -an | grep -i {mac} | awk '{{print $2;}}' | sed 's/[()]//g'".format(ip = ip, mac = mac)
    out = general.execute_command(cmd)
    return out[0].strip()

class HypervisorBase(object):
    def __init__(self):
        self.autotest_check_code = "autotest_check_code"

    def wait_for_vm_pingable(self, name, retries = 50, pingable = True, vm_ip = None):
        while retries:
            mac = self.get_mac_address(name)
            print mac
            vm_ip = vm_ip or get_vm_ip_from_mac(mac)
            print vm_ip

            if vm_ip:
                response = os.system("ping -c 1 >/dev/null 2>&1 " + vm_ip)
                if (response == 0 and pingable) or (response != 0 and not pingable):
                    return vm_ip

            retries -= 1
            time.sleep(1)
        assert retries
        return vm_ip

    def delete_clones(self, vm_name):
        vm_object = VMachineList.get_vmachine_by_name(vm_name)
        assert vm_object, "Vm with name {} was not found".format(vm_name)
        vm_object = vm_object[0]
        clones = []
        for vd in vm_object.vdisks:
            for child_vd in vd.child_vdisks:
                if child_vd.vmachine:
                    clones.append(child_vd.vmachine)
        unique_guids = set()
        clones = [c for c in clones if c.guid not in unique_guids and not unique_guids.add(c.guid)]
        for clone in clones:
            self.delete(clone.name)

    def get_ssh_con(self, vm_name):
        vm_ip = self.wait_for_vm_pingable(vm_name)
        ssh_con = paramiko.SSHClient()
        ssh_con.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        username, password = "root", "rooter"
        ssh_con.connect(vm_ip,
                        username = username,
                        password = password,
                        timeout  = 200)
        return ssh_con

    def write_test_data(self, vm_name, filename, zero_filled = False, zero_filled_count = 1):
        ssh_con = self.get_ssh_con(vm_name)

        path = os.path.join(os.sep, "opt", filename)
        if not zero_filled:
            cmd = "echo -n {0} >{1};sync".format(self.autotest_check_code, path)
        else:
            cmd = "dd if=/dev/zero of={0} bs=1K count={1}".format(path, zero_filled_count)

        _stdin, stdout, _stderr = ssh_con.exec_command(cmd)
        stdout.readlines()
        time.sleep(1)

    def delete_test_data(self, vm_name, filename):
        ssh_con = self.get_ssh_con(vm_name)
        path = os.path.join(os.sep, "opt", filename)
        _stdin, stdout, _stderr = ssh_con.exec_command("rm {0}".format(path))
        stdout.readlines()
        time.sleep(1)

    def check_test_data(self, vm_name, filename, not_present = False):
        ssh_con = self.get_ssh_con(vm_name)
        path = os.path.join(os.sep, "opt", filename)
        _stdin, stdout, _stderr = ssh_con.exec_command("cat {0}".format(path))
        out = stdout.readlines()
        out = out[0] if out else ''
        if not_present:
            assert not out, "Data shouldnt be there: {}".format(out)
        else:
            assert out == self.autotest_check_code, "Wrong test data:{}".format(out)

        time.sleep(1)



class Vmware(HypervisorBase):
    def __init__(self, vpool):
        HypervisorBase.__init__(self)
        self.vpool = vpool
        self.mountpoint = list(vpool.storagedrivers)[0].mountpoint
        hypervisorInfo = autotests.getHypervisorInfo()
        assert hypervisorInfo, "No hypervisor info specified use autotests.setHypervisorInfo"
        self.sdk = Vmware_sdk(*hypervisorInfo)

    def create_vm(self, name, cpus = 1, ram = 1024):

        #not sure if its the propper way to get the datastore
        esxhost = self.sdk._validate_host(None)
        datastores = self.sdk._get_object(esxhost, properties = ['datastore']).datastore.ManagedObjectReference
        datastore = [d for d in datastores if self.vpool.name in d.value]
        assert datastore, "Did not found datastore"
        datastore = self.sdk._get_object(datastore[0])

        os_name = autotests.getOs()
        os_info = autotests.getOsInfo(os_name)
        bootdisk_path_remote = os_info['bootdisk_location']

        os.mkdir(os.path.join(self.mountpoint, name))

        diskName = "bootdisk.vmdk"
        diskNameFlat = "bootdisk-flat.vmdk"
        bootdisk_path = os.path.join(self.mountpoint, name, diskName)
        bootdisk_flat_path = os.path.join(self.mountpoint, name, diskNameFlat)

        template_server = autotests.getTemplateServer()
        bootdisk_url = urlparse.urljoin(template_server, bootdisk_path_remote + diskName)
        bootdisk_flat_url = urlparse.urljoin(template_server, bootdisk_path_remote + diskNameFlat)


        _download_to_vpool(bootdisk_url, bootdisk_path)
        _download_to_vpool(bootdisk_flat_url, bootdisk_flat_path)
        """
        task = self.sdk.create_vm(name      = name,
                                  cpus      = cpus,
                                  memory    = ram,
                                  os        = os_info['esx_os_name'],
                                  disks     = [],
                                  nics      = [{'bridge': PUBLIC_BRIDGE_NAME_ESX}],
                                  kvmport   = str(random.randint(0, 100000)),
                                  datastore = datastore.info.name,
                                  wait      = True)
        self.sdk.validate_result(task)
        """


        nics      = [{'bridge': PUBLIC_BRIDGE_NAME_ESX}]

        esxhost  = self.sdk._validate_host(None)
        hostdata = self.sdk._get_host_data(esxhost)

        # Build basic config information
        config = self.sdk._client.factory.create('ns0:VirtualMachineConfigSpec')
        config.name = name
        config.numCPUs = cpus
        config.memoryMB = ram
        config.guestId = os_info['esx_os_name']
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

        task = self.sdk._client.service.CreateVM_Task(hostdata['folder'],
                                                  config=config,
                                                  pool=hostdata['resourcePool'],
                                                  host=hostdata['host'])



        retries = 100
        while retries:
            vmObjects = self._get_vms()

            vm = [vm for vm in vmObjects if vm['name'] == name]
            if vm:
                vm = vm[0]
                if getattr(vm, "config", None):
                    break
            retries -= 1
            time.sleep(1)

        assert vm, "Did not found vm after creating it"

        vmDirName = vm.config.files.vmPathName.split()[1].split("/")[0]
        virtIdeController = [dev for dev in vm.config.hardware.device if "VirtualIDEController" in str(type(dev))][0]

        sdkClient = self.sdk._client
        vmSpec    = sdkClient.factory.create('ns0:VirtualMachineConfigSpec')

        unit = 0
        deviceInfo         = sdkClient.factory.create('ns0:Description')
        deviceInfo.label   = diskName
        deviceInfo.summary = diskName

        backing          = sdkClient.factory.create('ns0:VirtualDiskFlatVer2BackingInfo')
        backing.diskMode = 'persistent'
        backing.fileName = '[{datastore}] {fileName}'.format(datastore = datastore.info.name, fileName = os.path.join(vmDirName, diskName))

        device               = sdkClient.factory.create('ns0:VirtualDisk')
        device.controllerKey = virtIdeController.key
        device.key           = -200 - unit
        device.unitNumber    = unit
        device.deviceInfo    = deviceInfo
        device.backing       = backing

        diskSpec               = sdkClient.factory.create('ns0:VirtualDeviceConfigSpec')
        diskSpec.operation     = 'add'
        diskSpec.fileOperation = None
        diskSpec.device        = device
        vmSpec.deviceChange.append(diskSpec)

        task = sdkClient.service.ReconfigVM_Task(vm.obj_identifier, vmSpec)
        self.sdk.wait_for_task(task)
        self.sdk.validate_result(task)

        self.start(name)

    def _get_vms(self):
        esxhost = self.sdk._validate_host(None)
        return self.sdk._get_object(esxhost,
                                    prop_type   = 'VirtualMachine',
                                    traversal  = {'name': 'HostSystemTraversalSpec',
                                                  'type': 'HostSystem',
                                                  'path': 'vm',
                                                  })


    def start(self, name):
        vms = self._get_vms()
        vm = [v for v in vms if v.name == name]
        assert vm, "Vm with name {} not found".format(name)
        vm = vm[0]
        if vm.runtime.powerState == "poweredOn":
            return

        task = self.sdk._client.service.PowerOnVM_Task(vm.obj_identifier)
        self.sdk.wait_for_task(task)
        self.sdk.validate_result(task)

    def shutdown(self, name):
        vms = self._get_vms()
        vm = [v for v in vms if v.name == name]
        assert vm, "Vm with name {} not found".format(name)
        vm = vm[0]
        if vm.runtime.powerState == "poweredOff":
            return
        task = self.sdk._client.service.PowerOffVM_Task(vm.obj_identifier)
        self.sdk.wait_for_task(task)
        self.sdk.validate_result(task)

    def poweroff(self, name):
        vms = self._get_vms()
        vm = [v for v in vms if v.name == name]
        assert vm, "Vm with name {} not found".format(name)
        vm = vm[0]
        if vm.runtime.powerState == "poweredOff":
            return
        task = self.sdk._client.service.PowerOffVM_Task(vm.obj_identifier)
        self.sdk.wait_for_task(task)
        self.sdk.validate_result(task)


    def delete(self, name):
        vms = self._get_vms()
        vm = [v for v in vms if v.name == name]
        assert vm, "Vm with name {} not found".format(name)
        vm = vm[0]
        self.poweroff(name)
        task = self.sdk._client.service.Destroy_Task(vm.obj_identifier)
        self.sdk.wait_for_task(task)
        self.sdk.validate_result(task)


class Kvm(HypervisorBase):
    def __init__(self, vpool):
        HypervisorBase.__init__(self)
        self.vpool = vpool
        self.mountpoint = list(vpool.storagedrivers)[0].mountpoint
        self.sdk = Kvm_sdk()

    def create_vm(self, name, ram = 1024):
        os_name = autotests.getOs()
        bootdisk_path_remote = autotests.getOsInfo(os_name)['bootdisk_location']

        vm_path = os.path.join(self.mountpoint, name)
        if not os.path.exists(vm_path):
            os.mkdir(vm_path)

        bootdisk_path = os.path.join(self.mountpoint, name, "bootdisk.raw")
        if not os.path.exists(bootdisk_path):
            template_server = autotests.getTemplateServer()
            bootdisk_url = urlparse.urljoin(template_server, bootdisk_path_remote)

            _download_to_vpool(bootdisk_url, bootdisk_path)

            cmd = "virt-install --connect qemu:///system -n {name} -r {ram} --disk {bootdisk_path},device=disk,format=raw,bus=virtio --import --graphics vnc,listen=0.0.0.0 --vcpus=1 --network network=default,mac=RANDOM,model=e1000 --boot hd"
            cmd = cmd.format(name = name,
                             bootdisk_path = bootdisk_path,
                             ram = ram
                             )
            general.execute_command(cmd)

    def _wait_for_state(self, name, state):
        retries = 240

        while retries:
            if self.sdk.get_power_state(name) == state:
                return
            retries -= 1
            time.sleep(1)

        actuall_state = self.sdk.get_power_state(name)
        assert actuall_state == state, "Vm did not go into state {0}, actual {1}".format(state, actuall_state)

    def shutdown(self, name):
        if self.sdk.get_power_state(name) == 'TURNEDOFF':
            return
        self.sdk.shutdown(name)
        self._wait_for_state(name, 'TURNEDOFF')

    def poweroff(self, name):
        if self.sdk.get_power_state(name) == 'TURNEDOFF':
            return
        vm_obj = self.sdk.get_vm_object(name)
        vm_obj.destroy()

    def start(self, name):
        if self.sdk.get_power_state(name) == 'RUNNING':
            print "Vm {} already running".format(name)
            return
        self.sdk.power_on(name)
        self._wait_for_state(name, 'RUNNING')

    def get_mac_address(self, name):
        vmo = self.sdk.get_vm_object(name)
        dom = minidom.parseString(vmo.XMLDesc()).childNodes[0]
        devices = _xml_get_child(dom, "devices")[0]
        nic = _xml_get_child(devices, "interface")[0]
        mac = _xml_get_child(nic, "mac")[0]
        return mac.attributes['address'].value

    def delete(self, name):
        vm = VMachineList.get_vmachine_by_name(name)
        assert vm, "Couldnt find vm with name {}".format(name)
        vm = vm[0]

        self.poweroff(name)
        self.sdk.delete_vm(name, vm.devicename, None)


