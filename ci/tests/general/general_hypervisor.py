import os
import time
import urllib
import urlparse
import random
from xml.dom import minidom

from ci import autotests
from ci.tests.general import general

from ovs.dal.lists.vpoollist import VPoolList
from ovs.dal.lists.pmachinelist import PMachineList
from ovs.extensions.hypervisor.hypervisors.kvm import Sdk as Kvm_sdk
from ovs.extensions.hypervisor.hypervisors.vmware import Sdk as Vmware_sdk




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

class Vmware(object):
    def __init__(self, vpool):
        self.vpool = vpool
        self.mountpoint = list(vpool.vsrs)[0].mountpoint
        hypervisorInfo = autotests.getHypervisorInfo()
        assert hypervisorInfo, "No hypervisor info specified use autotests.setHypervisorInfo"
        self.sdk = Vmware_sdk(*hypervisorInfo)

    def create_vm(self, name, cpus = 1, ram = 1024):

        #not sure if its the propper way to get the datastore
        esxhost = self.sdk._validate_host(None)
        datastores = self.sdk._get_object(esxhost, properties = ['datastore']).datastore.ManagedObjectReference
        datastore = [d for d in datastores if self.vpool.vsrs[0].cluster_ip in d.value]
        assert datastore, "Did not found datastore"
        datastore = self.sdk._get_object(datastore[0])

        os_name = autotests.getOs()
        os_info = autotests.getOsInfo(os_name)
        bootdisk_path_remote = os_info['bootdisk_location']

        os.mkdir(os.path.join(self.mountpoint, name))
        diskName = "bootdisk.vmdk"
        bootdisk_path = os.path.join(self.mountpoint, name, diskName)

        template_server = autotests.getTemplateServer()
        bootdisk_url = urlparse.urljoin(template_server, bootdisk_path_remote)

        _download_to_vpool(bootdisk_url, bootdisk_path)
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

        vmObjects = self._get_vms()

        vm = [vm for vm in vmObjects if vm['name'] == name]
        assert vm, "Did not found vm after creating it"
        vm = vm[0]

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
        self.sdk.power_on(vm.obj_identifier.value, wait = True)

    def shutdown(self, name):
        vms = self._get_vms()
        vm = [v for v in vms if v.name == name]
        assert vm, "Vm with name {} not found".format(name)
        vm = vm[0]
        self.sdk.shutdown(vm.obj_identifier.value, wait = True)



class Kvm(object):
    def __init__(self, vpool):
        self.vpool = vpool
        self.mountpoint = list(vpool.vsrs)[0].mountpoint
        self.sdk = Kvm_sdk()

    def create_vm(self, name, ram = 1024):
        os_name = autotests.getOs()
        bootdisk_path_remote = autotests.getOsInfo(os_name)['bootdisk_location']

        vm_path = os.path.join(self.mountpoint, name)
        if not os.path.exists(vm_path):
            os.mkdir(vm_path)
            bootdisk_path = os.path.join(self.mountpoint, name, "bootdisk.raw")

            template_server = autotests.getTemplateServer()
            bootdisk_url = urlparse.urljoin(template_server, bootdisk_path_remote)

            _download_to_vpool(bootdisk_url, bootdisk_path)

            cmd = "virt-install --connect qemu:///system -n {name} -r {ram} --disk {bootdisk_path},device=disk,format=raw,bus=virtio --import --graphics vnc,listen=0.0.0.0 --vcpus=1 --network network=default,mac=RANDOM,model=e1000 --boot hd"
            cmd = cmd.format(name = name,
                             bootdisk_path = bootdisk_path,
                             ram = ram
                             )
            general.execute_command(cmd)
        else:
            print "VM path {} already exists".format(vm_path)

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
        if self.sdk.get_power_state(name) == 'RUNNING':
            self.sdk.shutdown(name)
        self._wait_for_state(name, 'TURNEDOFF')

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



