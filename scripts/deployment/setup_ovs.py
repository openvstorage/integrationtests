# Copyright 2014 Open vStorage NV
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from pylabs.InitBaseCore import q
import re
import sys
import time
import json
import getopt
import ipcalc
import random
import pexpect

DEPLOY_OVS_SCRIPT_LOCATION = "https://bitbucket.org/openvstorage/openvstorage/raw/default/scripts/deployment/deployOvs.py"
PUBLIC_NET_NAME = "CloudFramesPublic"
STORAGE_NET_NAME = "CloudFramesStorage"
UBUNTU_ISO = "ubuntu-14.04-alternate-amd64.iso"
UBUNTU_PASSWORD = "rooter"
SUPPORTED_HYPERVISORS = ["VMWARE", "KVM"]
VPOOL_TYPES = ["none", "local", "ceph", "swift_s3", "alba"]
OVS_NAME = "ovsvsa001"

hypervisor_ip = ""
hypervisor_password = ""
hypervisor_type = ""
public_ip = ""
public_netmask = ""
qualitylevel = ""
cluster_name = ""
use_local_storage = True
vpool_type = ""
hostname = "cloudfounders"
extra_packages = "vim"
storage_nic_mac = ""

connection_port = "80"
connection_password = ""
connection_username = ""
connection_host = ""
install_ovsvsa = True

storage_ip_last_octet = None

print sys.argv


def pick_option(child, opt_name, fail_if_not_found=True, use_select=True):
    if use_select:
        child.expect('Select Nr:')
    opt = [l for l in child.before.splitlines() if opt_name in l]
    assert opt or not fail_if_not_found, "Option {0} not found\n{1}".format(opt_name, child.before)
    if opt:
        opt = opt[0].split(":")[0].strip()
        child.sendline(opt)
    return bool(opt)


def randomMAC():
    mac = [0x00, 0x16, 0x3e,
           random.randint(0x00, 0x7f),
           random.randint(0x00, 0xff),
           random.randint(0x00, 0xff)]
    return ':'.join(map(lambda x: "%02x" % x, mac))

bool_to_yn = lambda b: {True: 'y', False: 'n'}[b]


def setup_mgmt_center(public_ip):
    q.clients.ssh.waitForConnection(public_ip, "root", UBUNTU_PASSWORD, times=120)
    con = q.remote.system.connect(public_ip, "root", UBUNTU_PASSWORD)

    python_cmd = """
from ovs.dal.lists.pmachinelist import PMachineList
from ovs.dal.lists.mgmtcenterlist import MgmtCenterList
from ovs.dal.hybrids.mgmtcenter import MgmtCenter
mcs = MgmtCenterList.get_mgmtcenters()
if len(mcs) >= 1:
    mc = mcs[0]
else:
    mc = MgmtCenter()
    mc.name = 'hmc'
    mc.username = 'admin'
    mc.password = 'rooter'
    mc.ip = '{public_ip}'
    mc.type = 'OPENSTACK'
    mc.port=443
if hasattr(mc, 'metadata'):
    mc.metadata = dict()
    mc.metadata['integratemgmt']=True
mc.save()

for pm in PMachineList.get_pmachines():
    pm.mgmtcenter = mc
    pm.save()
""".format(public_ip=public_ip)

    cmd = """cat <<EOF > /tmp/setup_mgmt_center.py
{0}
EOF
""".format(python_cmd)
    con.process.execute(cmd, dieOnNonZeroExitCode=False)

    cmd = """
    export PYTHONPATH=:/opt/OpenvStorage:/opt/OpenvStorage/webapps
    python /tmp/setup_mgmt_center.py"""

    print con.process.execute(cmd)


def run_deploy_ovs(hypervisor_ip, hypervisor_password, sdk, cli, vifs):
    ovs_deploy_script_name = q.system.fs.getBaseName(DEPLOY_OVS_SCRIPT_LOCATION)
    local_ovs_deploy_script = q.system.fs.joinPaths("/tmp", ovs_deploy_script_name)
    q.system.process.execute("cd /tmp;wget {0}".format(DEPLOY_OVS_SCRIPT_LOCATION))

    datastore = vifs.listds()[0]
    datastore_full_path = "/vmfs/volumes/{0}".format(datastore)
    datastore_alt_path = "[{0}] ".format(datastore)
    remote_ovs_deploy_script = datastore_alt_path + ovs_deploy_script_name

    out = cli.runShellCommand("esxcfg-vmknic -l", "/")
    if STORAGE_NET_NAME in out:
        cli.runShellCommand("esxcfg-vmknic -d -p {0}".format(STORAGE_NET_NAME), "/")

    vifs.put(local_ovs_deploy_script, remote_ovs_deploy_script)
    cli.runShellCommand("chmod +x {0}".format(ovs_deploy_script_name), datastore_full_path)

    q.tools.installerci.shutdown_vm_esx(sdk, OVS_NAME)
    q.tools.installerci.delete_vm_esx(sdk, OVS_NAME)

    ovs_dir = "[{0}] {1}".format(datastore, OVS_NAME)
    try:
        vifs.rm(ovs_dir)
    except:
        pass

    child = pexpect.spawn(
        'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@{0}'.format(hypervisor_ip))
    child.timeout = 200
    child.expect('Password:')
    child.sendline(hypervisor_password)

    child.expect('~ #')
    child.sendline(
        "touch {0}/dummy.iso;{0}/{1} --image {0}/dummy.iso".format(datastore_full_path, ovs_deploy_script_name))

    child.expect('Continue with the install?')
    child.sendline('y')

    child.expect('Please select your public network:')
    pick_option(child, PUBLIC_NET_NAME)

    child.expect('Please select your storage network:')
    pick_option(child, STORAGE_NET_NAME)

    child.expect('Specify the size in GB')
    child.sendline('')

    SELECT_SSD = "Select an SSD device"
    SELECT_HDD = "Select an HDD device"
    idx = child.expect([SELECT_SSD, SELECT_HDD, "~ #"])
    if idx in [0, 1]:
        child.expect("Select Nr:")
        child.sendline("1")

        idx = child.expect([SELECT_HDD, "~ #"])
        if idx == 0:
            child.expect("Select Nr:")
            child.sendline("1")
            child.expect("~ #")

    vmObjects = q.tools.installerci.get_vm_objects_esx(sdk, ['name', 'config'])
    vmObj = [v for v in vmObjects if v.name == OVS_NAME]
    assert vmObj, "DeployOvs script failed to create vm"
    vmObj = vmObj[0]

    storageEthAdapter = [dev for dev in vmObj.config.hardware.device if dev.deviceInfo.summary == STORAGE_NET_NAME]
    storageEthAdapter = storageEthAdapter[0]

    publicEthAdapter = [dev for dev in vmObj.config.hardware.device if dev.deviceInfo.summary == PUBLIC_NET_NAME]
    publicEthAdapter = publicEthAdapter[0]

    return vmObj, storageEthAdapter, publicEthAdapter


def deploy_custom_vm_esx(name, hypervisor_ip, public_ip, public_network, gateway, public_netmask, dns, hostname,
                         min_hdd_size, no_hdds=1):
    hypervisor_login = "root"
    hypervisor_password = "R00t3r123"
    cli = q.hypervisors.cmdtools.esx.cli.connect(hypervisor_ip, hypervisor_login, hypervisor_password)
    vifs = q.hypervisors.cmdtools.esx.vifs.connect(hypervisor_ip, hypervisor_login, hypervisor_password)
    sdk = q.hypervisors.cmdtools.esx.sdk.connect(hypervisor_ip, hypervisor_login, hypervisor_password)

    q.tools.installerci.shutdown_vm_esx(sdk, name)
    q.tools.installerci.delete_vm_esx(sdk, name)

    ovs_deploy_script_name = q.system.fs.getBaseName(DEPLOY_OVS_SCRIPT_LOCATION)
    local_ovs_deploy_script = q.system.fs.joinPaths("/tmp", ovs_deploy_script_name)
    q.system.process.execute("cd /tmp;wget {0}".format(DEPLOY_OVS_SCRIPT_LOCATION))

    datastore = vifs.listds()[0]
    datastore_full_path = "/vmfs/volumes/{0}".format(datastore)
    datastore_alt_path = "[{0}] ".format(datastore)
    remote_ovs_deploy_script = datastore_alt_path + ovs_deploy_script_name
    vifs.put(local_ovs_deploy_script, remote_ovs_deploy_script)

    cmd = '''import sys
sys.path.append('{datastore_full_path}')
import deployOvs
vm_sys = deployOvs.VMwareSystem()
vm_name = '{saio_name}'

all_pgs = deployOvs.VMwareSystem.list_vm_portgroups()
public_pg = '{PUBLIC_NET_NAME}'
private_pg = '{STORAGE_NET_NAME}'
nic_config = deployOvs.VMwareSystem.build_nic_config([private_pg, public_pg])

deployOvs.datastore = '{datastore}'
disk_config = ''
disk_config = vm_sys.create_vdisk(vm_name, 0, '30G', disk_config)

_, scsiluns = deployOvs.InstallHelper.execute_command(['esxcli', '--formatter=keyvalue', 'storage', 'core', 'device', 'list'])
convertedscsiluns = deployOvs.InstallHelper.convert_keyvalue(''.join(scsiluns))
devicestoexclude = list(vm_sys.get_rdms_in_use().values())
devicestoexclude.append(vm_sys.get_boot_device().split(':')[0])
freedevices = [lun for lun in convertedscsiluns if not lun['Device'] in devicestoexclude and lun['Size'] != 0]

no_hdds = {no_hdds}
hdds = [d for d in freedevices if d['Size'] >= {min_hdd_size} * 1000]
for idx in range(no_hdds):
    disk_config = vm_sys.create_vdisk_mapping(vm_name, idx + 1, hdds[idx], disk_config)

cpu = 4
memory = 4 * 1024
guestos = 'ubuntu'
osbits = 64
vm_config = vm_sys.create_vm_config(vm_name, cpu, memory, guestos, osbits, nic_config, disk_config, '')

deployOvs.InstallHelper.execute_command(['esxcli', 'system', 'settings', 'advanced', 'set', '-o', '/Power/UseCStates', '--int-value=1'])
deployOvs.InstallHelper.execute_command(['esxcli', 'system', 'settings', 'advanced', 'set', '-o', '/Power/UsePStates', '--int-value=0'])

_, out = deployOvs.InstallHelper.execute_command(['vim-cmd', 'solo/registervm', vm_config], True)
vm_id = out[0].strip()

deployOvs.InstallHelper.execute_command(['vim-cmd', 'hostsvc/autostartmanager/enable_autostart', '1'])
deployOvs.InstallHelper.execute_command(['vim-cmd', 'hostsvc/autostartmanager/update_autostartentry', '{{0}}'.format(vm_id), 'PowerOn', '5', '1', 'guestShutdown', '5', 'systemDefault'])
deployOvs.InstallHelper.execute_command(['vim-cmd', 'vmsvc/power.on', vm_id])
'''.format(datastore_full_path=datastore_full_path,
           datastore=datastore,
           PUBLIC_NET_NAME=PUBLIC_NET_NAME,
           STORAGE_NET_NAME=STORAGE_NET_NAME,
           saio_name=name,
           no_hdds=no_hdds,
           min_hdd_size=min_hdd_size)

    s_local = q.system.fs.getTempFileName()
    q.system.fs.writeFile(s_local, cmd)
    s_remote = q.system.fs.joinPaths(datastore_full_path, q.system.fs.getBaseName(s_local))
    vifs.put(source=s_local, destination=datastore_alt_path + q.system.fs.getBaseName(s_local))

    print cli.runShellCommand("python '" + s_remote + "'", "/")

    retries = 200
    while retries:
        vmObjects = q.tools.installerci.get_vm_objects_esx(sdk, ['name', 'config', 'runtime'])
        vmObj = [v for v in vmObjects if v.name == name]
        assert vmObj, "failed to create vm"
        vmObj = vmObj[0]
        if vmObj.runtime.powerState == "poweredOn":
            break
        retries -= 1

    storageEthAdapter = [dev for dev in vmObj.config.hardware.device if dev.deviceInfo.summary == STORAGE_NET_NAME]
    storageEthAdapter = storageEthAdapter[0]

    publicEthAdapter = [dev for dev in vmObj.config.hardware.device if dev.deviceInfo.summary == PUBLIC_NET_NAME]
    publicEthAdapter = publicEthAdapter[0]

    command = "python /opt/qbase5/utils/ubuntu_autoinstall.py -M {publicEthAdapter.macAddress} -m {storageEthAdapter.macAddress} -d {dns} -P {public_ip} -n {public_network} -g {gateway} -k {public_netmask} -a sda -x {hypervisor_ip} -b {saio_name} -v {UBUNTU_ISO} -o {hostname}"
    command = command.format(publicEthAdapter=publicEthAdapter,
                             storageEthAdapter=storageEthAdapter,
                             dns=dns,
                             public_ip=public_ip,
                             public_network=public_network,
                             gateway=gateway,
                             public_netmask=public_netmask,
                             hypervisor_ip=hypervisor_ip,
                             saio_name=name,
                             UBUNTU_ISO=UBUNTU_ISO,
                             hostname=hostname)
    q.system.process.execute(command)


def deploy_custom_vm_kvm(name,
                         hypervisor_ip,
                         public_ip,
                         public_network,
                         gateway,
                         public_netmask,
                         dns,
                         hostname,
                         min_hdd_size,
                         no_hdds=1):
    q.clients.ssh.waitForConnection(hypervisor_ip, "root", UBUNTU_PASSWORD, times=120)
    con = q.remote.system.connect(hypervisor_ip, "root", UBUNTU_PASSWORD)

    cmd = '''for d in /sys/class/scsi_disk/*
do
dev=$(ls $d/device/block)
{ mount | grep $dev > /dev/null || [ $(cat /sys/block/$dev/queue/rotational) == '0' ]; } || echo $dev
done'''
    disks = con.process.execute(cmd)[1].splitlines()

    for d in disks:
        size = int(con.process.execute(
            """python -c "from os import *;print lseek(open('/dev/{disk}', O_RDONLY), 0, SEEK_END)" """.format(disk=d))[
            1].strip())
        if size < min_hdd_size * (1024 ** 3):
            disks.remove(d)

    public_mac_address = randomMAC()
    storage_mac_address = randomMAC()

    con.process.execute("mkdir -p /vm/{0}".format(name))
    cmd = "virt-install --connect qemu:///system -n {name} -r 4096 --autostart ".format(name=name)
    cmd += "--disk path=/vm/{0}/bootdisk,size=30,bus=sata ".format(name)
    for idx in range(no_hdds):
        cmd += "--disk /dev/{0},device=disk,format=raw,bus=sata ".format(disks[idx])
    cmd += "--graphics vnc,listen=0.0.0.0 --vcpus=4 --network bridge={private_br},mac={storage_mac_address} --network bridge={public_br},mac={public_mac_address} --pxe --boot network,hd"
    cmd = cmd.format(public_br="pubbr",
                     public_mac_address=public_mac_address,
                     private_br="privbr",
                     storage_mac_address=storage_mac_address)

    con.process.execute(cmd)

    print cmd
    time.sleep(10)

    cmd = "python /opt/qbase5/utils/ubuntu_autoinstall.py -M {public_mac_address} \
-m {storage_mac_address} \
-d {dns} \
-P {public_ip} \
-n {public_network} \
-g {gateway} \
-k {public_netmask} \
-a sda \
-x {hypervisor_ip} \
-b {name} \
-v {UBUNTU_ISO} \
-H KVM \
-o {hostname}"
    cmd = cmd.format(public_mac_address=public_mac_address,
                     storage_mac_address=storage_mac_address,
                     dns=dns,
                     public_ip=public_ip,
                     public_network=public_network,
                     gateway=gateway,
                     public_netmask=public_netmask,
                     hypervisor_ip=hypervisor_ip,
                     name=name,
                     UBUNTU_ISO=UBUNTU_ISO,
                     hostname=hostname)
    q.system.process.execute(cmd)


def deploy_saio(hypervisor_type, hypervisor_ip, public_ip, public_network, gateway, public_netmask, dns, hostname,
                min_hdd_size=500):
    """
    Using saio (swift-all-in-one) as S3 backend
    """

    saio_name = "saio"

    if hypervisor_type == "VMWARE":
        deploy_custom_vm_esx(name=saio_name,
                             hypervisor_ip=hypervisor_ip,
                             public_ip=public_ip,
                             public_network=public_network,
                             gateway=gateway,
                             public_netmask=public_netmask,
                             dns=dns,
                             hostname=hostname,
                             min_hdd_size=min_hdd_size,
                             no_hdds=1)
    else:
        deploy_custom_vm_kvm(name=saio_name,
                             hypervisor_ip=hypervisor_ip,
                             public_ip=public_ip,
                             public_network=public_network,
                             gateway=gateway,
                             public_netmask=public_netmask,
                             dns=dns,
                             hostname=hostname,
                             min_hdd_size=min_hdd_size,
                             no_hdds=1)

    q.clients.ssh.waitForConnection(public_ip, "root", UBUNTU_PASSWORD, times=120)
    con = q.remote.system.connect(public_ip, "root", UBUNTU_PASSWORD)

    time.sleep(60)

    retries = 25
    while retries:
        exit_code = con.process.execute("ping -c1 8.8.8.8", withError=True, dieOnNonZeroExitCode=False)[0]
        print exit_code
        if exit_code == 0:
            break
        retries -= 1

    assert retries, "Saio node cant ping 8.8.8.8"

    print con.process.execute("apt-get update")
    con.process.execute("apt-get install curl gcc memcached rsync sqlite3 xfsprogs git-core libffi-dev python-setuptools unzip -y")
    con.process.execute("apt-get install python-coverage python-dev python-nose python-simplejson python-xattr python-eventlet python-greenlet python-pastedeploy python-netifaces python-pip python-dnspython python-mock -y")

    disk = con.process.execute('for d in /sys/class/scsi_disk/*; do dev=$(ls $d/device/block);mount | grep $dev > /dev/null || echo $dev;done')[1]
    disk = disk.splitlines()[0].strip()

    con.process.execute('''parted /dev/{0} mklabel gpt
parted /dev/{0} mkpart 1 xfs 0 100%
parted /dev/{0} name 1 swift
mkfs.xfs /dev/{0}1'''.format(disk))
    con.process.execute('echo /dev/{0}1 /mnt/{0}1 xfs noatime,nodiratime,nobarrier,logbufs=8 0 0 >> /etc/fstab'.format(disk))

    # create the mount point and subdirectories
    cmd = """mkdir /mnt/{0}1 && mount /dev/{0}1
mkdir /mnt/{0}1/{{1,2,3,4}}
chown ${{USER}}:${{USER}} /mnt/{0}1/*
mkdir -p /srv
for d in 1 2 3 4
do
ln -s /mnt/{0}1/$d /srv/$d
done
mkdir -p /srv/1/node/{0}1 /var/run/swift && chown -R ${{USER}}:${{USER}} /var/run/swift && chown -R ${{USER}}:${{USER}} /srv/1/""".format(disk)
    con.process.execute(cmd)

    # setup rc.local
    cmd = """cat <<EOF >/etc/rc.local
#!/bin/sh -e
mkdir -p /var/cache/swift /var/cache/swift2 /var/cache/swift3 /var/cache/swift4 || true
chown root:root /var/cache/swift*
mkdir -p /var/run/swift || true
chown root:root /var/run/swift
export PATH=$PATH:/usr/local/bin/:/root/bin/
/root/bin/startmain
exit 0
EOF
echo 1"""
    con.process.execute(cmd)

    #python-swiftclient
    cmd = """cd
git clone https://github.com/openstack/python-swiftclient.git
cd python-swiftclient
python setup.py develop"""
    con.process.execute(cmd)

    #swift
    cmd = """cd
git clone https://github.com/openstack/swift.git
cd swift
python setup.py develop"""
    con.process.execute(cmd)

    cmd = """cp $HOME/swift/doc/saio/rsyncd.conf /etc/
sed -i "s/<your-user-name>/${USER}/" /etc/rsyncd.conf"""
    con.process.execute(cmd)

    #enable rsync (in /etc/default/rsync)
    cmd = """sed -i "s/RSYNC_ENABLE=false/RSYNC_ENABLE=true/"  /etc/default/rsync"""
    con.process.execute(cmd)

    #start rsync
    cmd = "service rsync restart"
    con.process.execute(cmd)

    #test
    con.process.execute("rsync rsync://pub@localhost/")

    #start memcached if not running
    con.process.execute("service memcached start")

    #make sure /etc/swift is empty
    con.process.execute("rm -rf /etc/swift")

    #populate it
    cmd = """cd $HOME/swift/doc && cp -r saio/swift /etc/swift
sudo chown -R ${USER}:${USER} /etc/swift"""
    con.process.execute(cmd)

    #configure username
    cmd = 'find /etc/swift/ -name \*.conf | xargs sudo sed -i "s/<your-user-name>/${USER}/"'
    con.process.execute(cmd)

    #configure /etc/swift/swift.conf
    cmd = """function f { od -t x8 -N 8 -A n </dev/random; }
sed -i "s/swift_hash_path_prefix = changeme/swift_hash_path_prefix = $(f)/" /etc/swift/swift.conf
sed -i "s/swift_hash_path_suffix = changeme/swift_hash_path_suffix = $(f)/" /etc/swift/swift.conf"""
    con.process.execute(cmd)

    #Enable saio scripts:
    cmd = """cd $HOME/swift/doc && cp -r saio/bin $HOME/bin
chmod +x $HOME/bin/* && cd"""
    con.process.execute(cmd)

    cmd = 'sed -i "s/sdb1/{0}1/"  $HOME/bin/resetswift'.format(disk)
    con.process.execute(cmd)

    cmd = 'sed -i "/find \/var\/log\/swift/d"  $HOME/bin/resetswift'.format(disk)
    con.process.execute(cmd)

    cmd = 'sed -i "s/bind_ip = 127.0.0.1/bind_ip = {0}/g" /etc/swift/proxy-server.conf'.format(public_ip)
    con.process.execute(cmd)

    cmd = 'echo "export PATH=${PATH}:$HOME/bin" >> $HOME/.bashrc'
    con.process.execute(cmd)

    q.clients.ssh.waitForConnection(public_ip, "root", UBUNTU_PASSWORD, times=120)
    con = q.remote.system.connect(public_ip, "root", UBUNTU_PASSWORD)

    #construct the initial rings using the provided script
    con.process.execute("/root/bin/remakerings")

    #Start swift
    con.process.execute("/root/bin/startmain")

    cmd = """wget https://github.com/fujita/swift3/archive/master.zip && unzip master.zip
cd swift3-master && python setup.py install
cp -r /usr/local/lib/python2.7/dist-packages/swift3-1.7.0-py2.7.egg /root/swift/ && cd /root/swift
mv swift3-1.7.0-py2.7.egg swift3.egg"""
    con.process.execute(cmd)

    cmd = r'''echo -e 'pipeline = catch_errors proxy-logging cache swift3 tempauth proxy-logging proxy-server\n' >new_pipeline
awk 'BEGIN {b=999;} /\[pipeline:main\]/{b=NR;} {if(NR>b){if( $0 ~ /\[.*\]/ ){b=999;system("cat new_pipeline");print;}} else print;} ' /etc/swift/proxy-server.conf > new_conf
mv new_conf /etc/swift/proxy-server.conf
rm new_pipeline
echo -e '[filter:swift3]\nuse = egg:swift3#swift3' >>/etc/swift/proxy-server.conf'''
    con.process.execute(cmd)

    con.process.execute("swift-init all restart")


def deploy_storage_node(hypervisor_type, hypervisor_ip, public_ip, public_network, gateway, public_netmask, dns, qualitylevel, alba_deploy_type):
    hostname = "alba"
    if alba_deploy_type in ['standalone']:
        if hypervisor_type == "VMWARE":
            deploy_custom_vm_esx(name=hostname,
                                 hypervisor_ip=hypervisor_ip,
                                 public_ip=public_ip,
                                 public_network=public_network,
                                 gateway=gateway,
                                 public_netmask=public_netmask,
                                 dns=dns,
                                 hostname=hostname,
                                 min_hdd_size=100,
                                 no_hdds=4)
        else:
            deploy_custom_vm_kvm(name=hostname,
                                 hypervisor_ip=hypervisor_ip,
                                 public_ip=public_ip,
                                 public_network=public_network,
                                 gateway=gateway,
                                 public_netmask=public_netmask,
                                 dns=dns,
                                 hostname=hostname,
                                 min_hdd_size=100,
                                 no_hdds=4)
        q.clients.ssh.waitForConnection(public_ip, "root", UBUNTU_PASSWORD, times=120)
        con = q.remote.system.connect(public_ip, "root", UBUNTU_PASSWORD)
        cmd = """echo "deb http://packages.cloudfounders.com/apt/ %(qualitylevel)s/" > /etc/apt/sources.list.d/ovsaptrepo.list
apt-get update
apt-get install --force-yes --yes openvstorage-sdm
# echo 1 > /dev/null""" % {'qualitylevel': qualitylevel}
        print con.process.execute(cmd)


def configure_alba(hypervisor_ip, public_ip, alba_deploy_type, license, backend_name):
    if alba_deploy_type in ['converged']:
        alba_host_ip = hypervisor_ip
    else:
        alba_host_ip = public_ip

    q.clients.ssh.waitForConnection(alba_host_ip, "root", UBUNTU_PASSWORD, times=120)
    con = q.remote.system.connect(alba_host_ip, "root", UBUNTU_PASSWORD)

    python_cmd = """
from ovs.extensions.api.client import OVSClient
from ovs.dal.hybrids.backend import Backend
from ovs.dal.lists.clientlist import ClientList
from ovs.dal.lists.backendlist import BackendList
from ovs.dal.lists.backendtypelist import BackendTypeList
from ovs.lib.albacontroller import AlbaController
from ovs.lib.albanodecontroller import AlbaNodeController
from ovs.dal.lists.albanodelist import AlbaNodeList

import time

alba_backend_name = '%(backend_name)s'
backend_guid = ''

type_guid = BackendTypeList.get_backend_type_by_code('alba').guid

oauth_client = ClientList.get_by_types('INTERNAL', 'CLIENT_CREDENTIALS')[0]
client = OVSClient('%(public_ip)s', 443, (oauth_client.client_id, oauth_client.client_secret))

existing_backends = BackendList().get_backends()
for backend in existing_backends:
    if backend.name in [alba_backend_name]:
        backend_guid = backend.guid
if not backend_guid:
    # create backend
    print 'creating backend'
    create_result = client.post('/backends/', data={'name': alba_backend_name, 'backend_type_guid': type_guid})
    if not create_result:
        raise Exception('Exception occurred during backend creation: {0}'.format(result))
    backend_guid = create_result['guid']

    # initialize backend
    if create_result['status'] in ['NEW']:
        # @todo: remove try except clause when OVS-2049 is fixed
        try:
            alba_init_result = client.post('/alba/backends/', data={'backend_guid': create_result['guid']})
        except RuntimeError:
            pass

# wait for backend to complete initialization
backend_status = client.get('/backends/{0}/'.format(backend_guid))['status']
count = 100
while backend_status not in ['RUNNING']:
    print 'Backend is in status: {0}'.format(backend_status)
    time.sleep(5)
    count -= 1
    backend_status = client.get('/backends/{0}/'.format(backend_guid))['status']

if backend_status not in ['RUNNING'] or count <= 0:
    raise Exception('Backend initialization failed or timed-out')

# Initialize max 3 disks
backend = client.get('/backends/{0}/'.format(backend_guid))

print backend
print backend['alba_backend_guid']

alba_node = AlbaNodeList.get_albanode_by_ip('%(public_ip)s')
node_guid = alba_node.guid

# claim up to 3 disks
nr_of_claimed_disks = 0
for disk in Backend(backend['guid']).alba_backend.all_disks:
    if 'asd_id' in disk and disk['status'] in 'claimed' and disk['node_id'] == alba_node.node_id:
        nr_of_claimed_disks += 1

if nr_of_claimed_disks < 3:
    disks_to_init = [d['name'] for d in alba_node.all_disks if d['available'] is True][:3 - nr_of_claimed_disks]
    print 'Disks to init:{0} '.format(disks_to_init)

    failures = AlbaNodeController.initialize_disks(node_guid, disks_to_init)

    if failures:
        raise RuntimeException('Alba disk initialization failed for (some) disks: {0}'.format(failures))

# add license

from ovs.lib.license import LicenseController
LicenseController.apply('%(license)s')

# get disks ready to claim from model
claimable_ids = list()
for disk in Backend(backend['guid']).alba_backend.all_disks:
    if 'asd_id' in disk and disk['status'] in 'available':
        claimable_ids.append(disk['asd_id'])

print claimable_ids

# claim disks
osds = dict()
disks_to_claim = [d['name'] for d in alba_node.all_disks if d['available'] is False]
print 'Disks to claim: {0}'.format(disks_to_claim)
for name in disks_to_claim:
    for disk in alba_node.all_disks:
        if name == disk['name'] and disk['asd_id'] in claimable_ids:
            osds[disk['asd_id']] = node_guid
print osds
AlbaController.add_units(backend['alba_backend_guid'], osds)
""" % {'public_ip': alba_host_ip, 'license': license, 'backend_name': backend_name}

    cmd = """cat <<EOF > /tmp/configure_alba.py
{0}
EOF
echo 1
""".format(python_cmd)
    con.process.execute(cmd, dieOnNonZeroExitCode=False)

    cmd = """
export PYTHONPATH=:/opt/OpenvStorage:/opt/OpenvStorage/webapps
python /tmp/configure_alba.py
"""

    print con.process.execute(cmd, dieOnNonZeroExitCode=False)


def configure_mgmt_center(public_ip, qualitylevel=''):
    q.clients.ssh.waitForConnection(public_ip, "root", UBUNTU_PASSWORD, times=120)
    con = q.remote.system.connect(public_ip, "root", UBUNTU_PASSWORD)

    python_cmd = """
# management center is required to configure cinder on openstack
# match jenkins choice values: false/true
from ovs.dal.lists.pmachinelist import PMachineList
from ovs.dal.lists.mgmtcenterlist import MgmtCenterList
from ovs.dal.hybrids.mgmtcenter import MgmtCenter
from ovs.lib.mgmtcenter import MgmtCenterController

mcs = MgmtCenterList.get_mgmtcenters()
if len(mcs) >= 1:
    mc = mcs[0]
else:
    mc = MgmtCenter()
    mc.name = 'hmc'
    mc.username = 'admin'
    mc.password = 'rooter'
    mc.ip = '{public_ip}'
    mc.type = 'OPENSTACK'
    mc.port=443
if hasattr(mc, 'metadata'):
    mc.metadata = dict()
    mc.metadata['integratemgmt']=True
mc.save()

for pm in PMachineList.get_pmachines():
    pm.mgmtcenter = mc
    pm.save()

    from ovs.extensions.hypervisor.factory import Factory
    mgmt_center = Factory.get_mgmtcenter(pm)
    if mgmt_center:
        outcome = ''
        result = MgmtCenterController.configure_host.s(pm.guid, pm.mgmtcenter.guid, True).apply_async(routing_key='sr.%s' % pm.storagerouters[0].machine_id)
        import time
        time.sleep(30)
        if not result.status == 'SUCCESS':
            if result.result:
                if len(result.result):
                    outcome = result.result[1]
            else:
                outcome = 'Status in %s' % result.status
            raise Exception('Following errors found during management center configuration: %s' % outcome)
""".format(public_ip=public_ip)

    cmd = """cat <<EOF > /tmp/configure_mgmt_center.py
{0}
EOF
""".format(python_cmd)
    con.process.execute(cmd, dieOnNonZeroExitCode=False)
    cmd = """
    export PYTHONPATH=:/opt/OpenvStorage:/opt/OpenvStorage/webapps
    python /tmp/configure_mgmt_center.py"""

    print con.process.execute(cmd)


def deploy_vpool(public_ip, vpool_name, vpool_type, vpool_host, vpool_port, vpool_router_port,
                 vpool_storage_ip='127.0.0.1', add_mgmt_center='true', qualitylevel="unstable", backend_name='alba'):
    q.clients.ssh.waitForConnection(public_ip, "root", UBUNTU_PASSWORD, times=120)
    con = q.remote.system.connect(public_ip, "root", UBUNTU_PASSWORD)

    screen_pid = con.process.execute("ps ax | awk '/SCREEN/ && /stack/ && !/awk/ {print $1}'")[1].strip()
    output = con.process.execute("lsof -p {0} | awk '/FIFO/ && !awk'".format(screen_pid))[1].strip()
    if 'deleted' in output:
        print "### screen socket in state deleted ###"
        con.process.execute("kill -SIGCHLD {0}".format(screen_pid))
        output = con.process.execute("lsof -p {0} | awk '/FIFO/ && !awk'".format(screen_pid))[1].strip()
        time.sleep(2)
        if 'deleted' in output:
            print "### screen socket still in state deleted ###"

    vpool_type = vpool_type.lower()

    vpool_mount = '/mnt/dfs/{vpool_name}'.format(vpool_name=vpool_name)
    python_cmd = """from ovs.lib.storagerouter import StorageRouterController
from ovs.dal.lists.backendlist import BackendList
vpool_type = '{vpool_type}'
parameters = {{}}

# management center is required to configure cinder on openstack
# match jenkins choice values: false/true
if '{add_mgmt_center}'.lower() in ['true']:
    from ovs.dal.lists.pmachinelist import PMachineList
    from ovs.dal.lists.mgmtcenterlist import MgmtCenterList
    from ovs.dal.hybrids.mgmtcenter import MgmtCenter
    mcs = MgmtCenterList.get_mgmtcenters()
    if len(mcs) >= 1:
        mc = mcs[0]
    else:
        mc = MgmtCenter()
        mc.name = 'hmc'
        mc.username = 'admin'
        mc.password = 'rooter'
        mc.ip = '{public_ip}'
        mc.type = 'OPENSTACK'
        mc.port=443
    if hasattr(mc, 'metadata'):
        mc.metadata = dict()
        mc.metadata['integratemgmt']=True
    mc.save()

    for pm in PMachineList.get_pmachines():
        pm.mgmtcenter = mc
        pm.save()

if vpool_type.lower() == 'alba':
    alba_backend_guid = [b for b in BackendList.get_backends() if b.name == '{backend_name}'][0].alba_backend_guid
    data = {{'backend': alba_backend_guid,
             'metadata': 'default'}}
    parameters['connection_backend'] = data

parameters['vpool_name']             = '{vpool_name}'
parameters['storage_ip']             = '{storage_ip}'
parameters['storagerouter_ip']       = '{public_ip}'
parameters['readcache_size']         = 50
parameters['writecache_size']        = 50
parameters['type']                   = vpool_type
parameters['connection_host']        = ''
parameters['connection_port']        = {connection_port}
parameters['connection_username']    = '{connection_username}'
parameters['connection_password']    = '{connection_password}'
parameters['config_cinder']          = True
parameters['integratemgmt']          = True
parameters['cinder_controller']      = '{public_ip}'
parameters['cinder_user']            = 'admin'
parameters['cinder_pass']            = 'rooter'
parameters['cinder_tenant']          = 'admin'
StorageRouterController.add_vpool(parameters)
""".format(public_ip=public_ip,
           vpool_name=vpool_name,
           vpool_type=vpool_type,
           connection_host=vpool_host,
           connection_port=vpool_port,
           connection_username="test:tester",
           connection_password="testing",
           vpool_mount=vpool_mount,
           vrouter_port=vpool_router_port,
           storage_ip=vpool_storage_ip,
           add_mgmt_center=add_mgmt_center,
           qualitylevel=qualitylevel,
           backend_name=backend_name)

    cmd = """cat <<EOF > /tmp/deploy_vpool.py
{0}
EOF
""".format(python_cmd)
    con.process.execute(cmd, dieOnNonZeroExitCode=False)
    cmd = """
    export PYTHONPATH=:/opt/OpenvStorage:/opt/OpenvStorage/webapps
    python /tmp/deploy_vpool.py"""

    print con.process.execute(cmd)


def install_archipel(node_ip, install_agent=True, vpool_mount=None):
    q.clients.ssh.waitForConnection(node_ip, "root", UBUNTU_PASSWORD, times=120)
    con = q.remote.system.connect(node_ip, "root", UBUNTU_PASSWORD)

    # 1 installing agent - refer to manual section on:
    cmd = "apt-get install -y --force-yes gfortran python-dev python-setuptools python-libvirt python-magic"
    con.process.execute(cmd)

    # as of doc:
    #this seems to fail the first time but succeeds when ran again - perhaps we can simply ignore the first error
    cmd = "easy_install archipel-agent && archipel-initinstall"
    con.process.execute(cmd, dieOnNonZeroExitCode=False)
    con.process.execute(cmd)

    #2 install xmpp server
    cmd = """apt-get install -y --force-yes ejabberd"""
    con.process.execute(cmd)

    cmd = 'sed -i "s/^{access, register, \[{deny, all}\]}/{access, register, [{allow, all}]}/"  /etc/ejabberd/ejabberd.cfg'
    con.process.execute(cmd)
    cmd = 'sed -i  "s/.*{registration_timeout,.*/{registration_timeout, infinity}./"  /etc/ejabberd/ejabberd.cfg'
    con.process.execute(cmd)
    cmd = "sed -i '/mod_pubsub/a                   {max_items_node, 1000},' /etc/ejabberd/ejabberd.cfg"
    con.process.execute(cmd)
    cmd = "sed -i '/{mod_vcard/a  {mod_http_bind, []},' /etc/ejabberd/ejabberd.cfg"
    con.process.execute(cmd)
    cmd = r'''sed -i "s/{hosts,.*/{hosts, [\"localhost\", \"$(hostname)\"]}./" /etc/ejabberd/ejabberd.cfg'''
    con.process.execute(cmd)

    restart_ejabberd_cmd = "service ejabberd restart"
    con.process.execute(restart_ejabberd_cmd)

    time.sleep(40)
    cmd = "ejabberdctl register admin localhost rooter"
    con.process.execute(cmd)
    con.process.execute(restart_ejabberd_cmd)

    time.sleep(40)
    cmd = "ejabberdctl register admin $(hostname) rooter"
    con.process.execute(cmd)
    con.process.execute(restart_ejabberd_cmd)

    time.sleep(30)

    cmd = """archipel-tagnode --jid=admin@localhost --password=rooter --create
archipel-rolesnode --jid=admin@localhost --password=rooter --create
archipel-adminaccounts --jid=admin@localhost --password=rooter --create

archipel-tagnode --jid=admin@$(hostname) --password=rooter --create
archipel-rolesnode --jid=admin@$(hostname) --password=rooter --create
archipel-adminaccounts --jid=admin@$(hostname) --password=rooter --create"""
    con.process.execute(cmd)

    cmd = 'sed -i "s/hypervisor_xmpp_password.*/hypervisor_xmpp_password = rooter/" /etc/archipel/archipel.conf'
    con.process.execute(cmd)

    if vpool_mount:
        cmd = 'sed -i "s/^archipel_folder_data\s*=.*/archipel_folder_data = {0}/" /etc/archipel/archipel.conf '.format(vpool_mount.replace("/", "\/"))
        con.process.execute(cmd)
        cmd = 'sed -i "s/vm_base_path.*/vm_base_path = %(archipel_folder_data)s/" /etc/archipel/archipel.conf '
        con.process.execute(cmd)

    cmd = '/etc/init.d/archipel restart'
    con.process.execute(cmd)

    if install_agent:
        #3 the webserver part can be be easily installed below the ovs directory structure:
        # install web server part
        cmd = "apt-get -y install nginx unzip"
        con.process.execute(cmd)

        cmd = '''wget http://updates.archipelproject.org/archipel-gui-beta6.zip
unzip archipel-gui-beta6.zip
mv archipel-gui-beta6  /opt/OpenvStorage/webapps/frontend/archipel'''
        con.process.execute(cmd)


def install_autotests(node_ip):
    con = q.remote.system.connect(node_ip, "root", UBUNTU_PASSWORD)
    con.process.execute("apt-get update")
    con.process.execute("apt-get install unzip openvstorage-test -y --force-yes")

    con.process.execute("wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | sudo apt-key add -")
    con.process.execute('echo "deb http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list')
    con.process.execute("apt-get update", dieOnNonZeroExitCode=False)
    con.process.execute("apt-get install google-chrome-beta x11vnc  libav-tools -y --force-yes")
    # con.process.execute("[ -f '/usr/bin/virsh' ] && apt-get install -y virt-viewer")
    con.process.execute("""wget http://chromedriver.storage.googleapis.com/2.19/chromedriver_linux64.zip;unzip chromedriver_linux64.zip;mv chromedriver /usr/bin/""")

    con.process.execute("if [ ! -f /usr/lib/libudev.so.0 ]; then ln -s /lib/x86_64-linux-gnu/libudev.so.1.3.5 /usr/lib/libudev.so.0; fi")

    cmd = """cat <<EOF >>/usr/lib/python2.7/sitecustomize.py
import sys
sys.setdefaultencoding('utf8')
EOF
echo 1"""
    con.process.execute(cmd)

    con.process.execute("pip install vnc2flv")


def run_autotests(node_ip, vpool_host_ip, vmware_info='', dc='', capture_screen=False, test_plan='', reboot_test=False,
                  vpool_name='alba', backend_name='alba', vpool_type='alba', test_project='Open vStorage Engineering', qualitylevel = 'unstable'):
    """
    vmware_info = "10.100.131.221,root,R00t3r123"

    """
    con = q.remote.system.connect(node_ip, "root", UBUNTU_PASSWORD)

    vpool_storage_ip = con.process.execute("ip a | awk '/inet/ && /privbr/ {print $2}'")[0]
    vpool_storage_ip = ipcalc.IP(vpool_storage_ip).dq

    os_name = "ubuntu_desktop14_kvm" if not vmware_info else "small_linux_esx"

    template_server = "http://sso-qpackages-loch.cloudfounders.com"
    if dc == 'bel-jen-axs.cloudfounders.com':
        template_server = "http://sso-qpackages-brussels.cloudfounders.com"

    if not test_plan:
        test_run = "autotests.runAll('TESTRAIL', '/var/tmp')"
    else:
        test_run = "autotests.run('{0}', 'TESTRAIL', '/var/tmp')".format(test_plan)

    if qualitylevel in ['unstable']:
        vpool_foc_name = 'vpool_dtl_mp'
        cache_strategy = 'on_read'
    else:
        vpool_foc_name = 'vpool_foc_mp'
        cache_strategy = 'onread'
    # check for ceph vm
    cmd = 'source /etc/profile.d/ovs.sh;python -c "from ovs.dal.lists.storagerouterlist import StorageRouterList; print  [sr.ip  for sr in StorageRouterList.get_storagerouters()]"'
    nodes = eval(con.process.execute(cmd)[1])
    ceph_vm_name = "ceph"
    ceph_vpool_info = ""

    for node in nodes:
        con2 = q.remote.system.connect(node, "root", UBUNTU_PASSWORD)
        out = con2.process.execute("virsh list --all | grep {0} || true".format(ceph_vm_name))[1]
        if ceph_vm_name not in out:
            con2.close()
            continue
        cmd = '''mac=$(virsh dumpxml %s | grep "bridge='pubbr'" -B 1 | grep -o -P "(?<=address=').*(?=')")
apt-get install nmap -y >/dev/null 2>&1
nmap -sP %s/24 | grep $mac -i -B 2 | grep -oP "([0-9]+\.){3}([0-9]+)" ''' % (ceph_vm_name, node)
        ceph_node_ip = con2.process.execute(cmd, dieOnNonZeroExitCode=False)[1].strip()
        con2.close()
        if not ceph_node_ip:
            continue
        con2 = q.remote.system.connect(ceph_node_ip, "root", UBUNTU_PASSWORD)
        user_info = json.loads(con2.process.execute("/usr/bin/radosgw-admin user info --uid=johndoe")[1])
        ceph_vpool_info = """[vpool3]
vpool_name = {vpool_name}
vpool_type = {vpool_type}
vpool_type_name     = Ceph S3
vpool_host          = {ceph_node_ip}
vpool_port          = 80
vpool_access_key    = {access_key}
vpool_secret_key    = {secret_key}
{vpool_foc_name}    = /mnt/cache1/ceph/foc
vpool_vrouter_port  = 12345
vpool_storage_ip    = {vpool_storage_ip}
vpool_config_params = {{"dtl_mode": "sync", "sco_size": 4, "dedupe_mode": "dedupe", "dtl_enabled": false, "dtl_location": "", "cache_strategy": "{cache_strategy}", "write_buffer": 128}}
""".format(ceph_node_ip=ceph_node_ip,
           access_key=user_info['keys'][0]['access_key'],
           secret_key=user_info['keys'][0]['secret_key'],
           vpool_storage_ip=vpool_storage_ip,
           vpool_name=vpool_name,
           vpool_type=vpool_type,
           vpool_foc_name=vpool_foc_name,
           cache_strategy=cache_strategy)
        break

    if vpool_type == "swift_s3":
        vpool_config = """
[vpool]
vpool_name = {vpool_name}
vpool_type = {vpool_type}
vpool_type_name     = Swift S3
vpool_host          = {vpool_host_ip}
vpool_port          = 8080
vpool_access_key    = test:tester
vpool_secret_key    = testing
{vpool_foc_name}    = /mnt/cache1/saio/foc
vpool_vrouter_port  = 12345
vpool_storage_ip    = {vpool_storage_ip}
vpool_config_params = {{"dtl_mode": "sync", "sco_size": 4, "dedupe_mode": "dedupe", "dtl_enabled": false, "dtl_location": "", "cache_strategy": "{cache_strategy}", "write_buffer": 128}}
""".format(vpool_host_ip=vpool_host_ip,
           vpool_storage_ip=vpool_storage_ip,
           vpool_name=vpool_name,
           vpool_type=vpool_type,
           vpool_foc_name=vpool_foc_name,
           cache_strategy=cache_strategy)
        cinder_type = vpool_name

    elif vpool_type == "alba":
        vpool_config = """
[vpool]
vpool_name = {vpool_name}
vpool_type = {vpool_type}
vpool_type_name = Open vStorage Backend
vpool_host =
vpool_port = 80
vpool_access_key =
vpool_secret_key =
{vpool_foc_name} = /mnt/cache1/alba/foc
vpool_vrouter_port  = 12345
vpool_storage_ip = 0.0.0.0
vpool_config_params = {{"dtl_mode": "sync", "sco_size": 4, "dedupe_mode": "dedupe", "dtl_enabled": false, "dtl_location": "", "cache_strategy": "{cache_strategy}", "write_buffer": 128}}
""".format(vpool_name=vpool_name,
           vpool_type=vpool_type,
           vpool_foc_name=vpool_foc_name,
           cache_strategy=cache_strategy)
        cinder_type = vpool_name

    cmd = '''source /etc/profile.d/ovs.sh
pkill Xvfb
pkill x11vnc
sleep 3
Xvfb :1 -screen 0 1280x1024x16 &
export DISPLAY=:1.0
x11vnc -display :1 -bg -nopw -noipv6 -no6 -listen localhost -xkb  -autoport 5950 -forever

cat << EOF > /opt/OpenvStorage/ci/config/autotest.cfg
[main]
testlevel = 0
hypervisorinfo = {vmware_info}
os = {os_name}
template_server = {template_server}
username = admin
password = admin
screen_capture = {screen_capture}
cleanup = True
grid_ip = {grid_ip}
vpool_name = {vpool_name}
backend_name = {backend_name}
test_project = {test_project}


{vpool_config}

[vpool2]
vpool_name = localvp
vpool_type = local
vpool_type_name = Local FS
vpool_host =
vpool_port =
vpool_access_key =
vpool_secret_key =
{vpool_foc_name} = /mnt/cache3/localvp/foc
vpool_vrouter_port  = 12345
vpool_storage_ip = 127.0.0.1
vpool_config_params = {{"dtl_mode": "sync", "sco_size": 4, "dedupe_mode": "dedupe", "dtl_enabled": false, "dtl_location": "", "cache_strategy": "{cache_strategy}", "write_buffer": 128}}

{ceph_vpool_info}

[openstack]
cinder_type = {cinder_type}

EOF

ipython 2>&1 -c "from ci import autotests
{test_run}
"
'''.format(os_name=os_name,
           vmware_info=vmware_info,
           template_server=template_server,
           screen_capture=str(capture_screen),
           test_run=test_run,
           vpool_config=vpool_config,
           vpool_name=vpool_name,
           backend_name=backend_name,
           ceph_vpool_info=ceph_vpool_info,
           cinder_type=cinder_type,
           grid_ip=node_ip,
           test_project=test_project,
           vpool_foc_name=vpool_foc_name,
           cache_strategy=cache_strategy)

    out = q.tools.installerci._run_command(cmd, node_ip, "root", UBUNTU_PASSWORD, buffered=True)
    out = out[0] + out[1]

    if reboot_test:
        print "Started reboot test"

        m = re.search("http://testrail.openvstorage.com/index.php\?/plans/view/([0-9]*)", out)
        assert m and m.groups(), "Couldn't find the testrail plan"
        existing_plan_id = m.groups()[0]

        cmd = """source /etc/profile.d/ovs.sh; \
python -c 'from ovs.dal.lists.storagerouterlist import StorageRouterList; \
print [sr.ip for sr in StorageRouterList.get_storagerouters() if sr.ip != "{0}"]'""".format(node_ip)
        out = con.process.execute(cmd)[1]
        nodes = eval(out) + [node_ip]

        for rnode_ip in nodes:
            con = q.remote.system.connect(rnode_ip, "root", UBUNTU_PASSWORD)
            con.process.execute("shutdown -r now")
            q.system.net.waitForIpDown(ip=rnode_ip, timeout=600)
            q.system.net.waitForIp(ip=rnode_ip, timeout=600)
            q.clients.ssh.waitForConnection(rnode_ip, "root", UBUNTU_PASSWORD, times=60)

            cmd = """source /etc/profile.d/ovs.sh
export POST_REBOOT_HOST={0}
python -c 'from ci import autotests; autotests.run("api.extended_test:post_reboot_checks_test", "TESTRAIL", "/var/tmp", existing_plan_id = {1})'""".format(
                rnode_ip, existing_plan_id)
            print cmd
            q.tools.installerci._run_command(cmd, node_ip, "root", UBUNTU_PASSWORD, buffered=True)


def install_devstack(node_ip, fixed_range, fixed_range_size, floating_range, master_node_ip=None,
                     branch_name="stable/juno", tag_name="2014.2.3", flat_interface="eth0"):
    """
    https://wiki.openstack.org/wiki/Releases

    Juno: 2014.2.3
    Kilo: 2015.1.1
    Liberty: due Oct 15, 2015
    """
    con = q.remote.system.connect(node_ip, "root", UBUNTU_PASSWORD)
    (exitcode, output) = con.process.execute("apt-get install git -y --force-yes")
    print exitcode
    print output
    (exitcode, output) = con.process.execute("apt-get install curl -y --force-yes")
    print exitcode
    print output

    branch, sub_branches = "", ""
    if tag_name:
        branch = "-b {0}".format(branch_name)
        sub_branches = """
CINDER_BRANCH={0}
GLANCE_BRANCH={0}
HEAT_BRANCH={0}
HORIZON_BRANCH={0}
KEYSTONE_BRANCH={0}
NEUTRON_BRANCH={0}
NOVA_BRANCH={0}
SWIFT_BRANCH={0}
TROVE_BRANCH={0}
REQUIREMENTS_BRANCH={1}
""".format(tag_name, branch_name)

    cmd = """cd /home
git clone {branch} https://github.com/openstack-dev/devstack.git
cd devstack
./tools/create-stack-user.sh
adduser stack sudo
cd ../
chown -R stack:stack /home/devstack

cd devstack

# patch due to: https://bugs.launchpad.net/cinder/+bug/1447608
echo installing devstack pip ...
/home/devstack/tools/install_prereqs.sh
/home/devstack/tools/install_pip.sh

echo reverting futures to 2.2.0
pip install futures==2.2.0

echo reverting oslo utils to 1.4.0 ...
pip install oslo.utils==1.4.0

echo checking oslo.utils version
pip list | grep oslo.utils

chown -R stack:stack /home/devstack

sed -i 's/br100/pubbr/g' ./lib/nova
sed -i 's/br100/pubbr/g' ./lib/nova_plugins/hypervisor-baremetal

cat <<EOF >local.conf
[[local|localrc]]
HOST_IP={host_ip}
FLAT_INTERFACE={flat_interface}
FIXED_RANGE={fixed_range}
FIXED_NETWORK_SIZE={fixed_range_size}
FLOATING_RANGE={floating_range}
MULTI_HOST=1
LOGFILE=/opt/stack/logs/stack.sh.log
ADMIN_PASSWORD=rooter
MYSQL_PASSWORD=rooter
RABBIT_PASSWORD=rooter
SERVICE_PASSWORD=rooter
SERVICE_TOKEN=rooter

EOF

if [ -n "{master_node_ip}" ]; then
cat <<EOF >>local.conf

DATABASE_TYPE=mysql
SERVICE_HOST={master_node_ip}
MYSQL_HOST={master_node_ip}
RABBIT_HOST={master_node_ip}
GLANCE_HOSTPORT={master_node_ip}:9292
ENABLED_SERVICES=n-cpu,n-net,n-api,c-sch,c-api,c-vol

{sub_branches}

EOF

else
cat <<EOF >>local.conf

{sub_branches}

EOF

fi

chown stack:stack local.conf
echo 1""".format(host_ip=node_ip,
                 fixed_range=fixed_range,
                 fixed_range_size=fixed_range_size,
                 floating_range=floating_range,
                 flat_interface=flat_interface,
                 master_node_ip=master_node_ip or '',
                 branch=branch,
                 sub_branches=sub_branches)

    print 'Creating local.conf'
    (exitcode, output) = con.process.execute(cmd)
    print exitcode
    print output

    exports = "export OS_USERNAME=admin;export OS_PASSWORD=rooter;export OS_TENANT_NAME=admin;export OS_AUTH_URL=http://{0}:35357/v2.0;".format(master_node_ip)

    if master_node_ip:
        con_master = q.remote.system.connect(master_node_ip, "root", UBUNTU_PASSWORD)
        # Delete the lvmdriver cinder-type from your first node as the 2nd one will try to add the same and bail out
        print con_master.process.execute(exports + " cinder type-delete lvmdriver-1", dieOnNonZeroExitCode=False)
        con_master.close()

    cmd = """cd /home/devstack;su -c "cd /home/devstack;./stack.sh" stack"""

    if master_node_ip is not None:
        cmd = exports + cmd

    (exitcode, output) = con.process.execute(cmd)
    print exitcode
    print output

    print "Removing librabbitmq1 ..."
    cmd = "apt-get remove librabbitmq1 --purge -y"
    (exitcode, output) = con.process.execute(cmd, dieOnNonZeroExitCode=False)
    print exitcode
    print output

    # https://review.openstack.org/#/c/81489/1/lib/databases/mysql
    print "Increasing mysql max_connections to 10000 ..."
    cmd = """
sed -i 's/.*max_connections.*/max_connections=10000/' /etc/mysql/my.cnf
restart mysql
"""
    (exitcode, output) = con.process.execute(cmd, dieOnNonZeroExitCode=False)
    print exitcode
    print output

def install_cinder_plugin(node_ip, vpool_name, master_ip=None):
    con = q.remote.system.connect(node_ip, "root", UBUNTU_PASSWORD)

    def kill_service_in_screen(name):
        # just send the ctrl+c key in window name of screen
        print "killing ", name
        con.process.execute(r"""su -c 'screen -x stack -p {0} -X stuff "^C"' stack""".format(name))

    def restart_service_in_screen(name):
        # just send the up key + enter in window name of screen
        print "restarting ", name
        con.process.execute(r"""su -c 'screen -x stack -p {0} -X stuff "^[[A^[[A^[[A\n"' stack""".format(name))

    def restart_services(services):
        for service_name in services:
            time.sleep(1)
            kill_service_in_screen(service_name)
            time.sleep(1)
            restart_service_in_screen(service_name)

    cinder_type_name = vpool_name
    max_volumes = 100
    max_snapshots = 500
    max_gigabytes = 5000

    # libvirtd config
    ####################################################################################################################
    con.process.execute("sed -i 's/#listen_tls.*/listen_tls=0/g' /etc/libvirt/libvirtd.conf")
    con.process.execute("sed -i 's/#listen_tcp.*/listen_tcp=1/g' /etc/libvirt/libvirtd.conf")
    con.process.execute('''sed -i 's/.*auth_tcp.*/auth_tcp="none"/g' /etc/libvirt/libvirtd.conf''')
    con.process.execute("sed -i 's/#dynamic_ownership.*/dynamic_ownership = 0/g' /etc/libvirt/qemu.conf")
    con.process.execute('''sed -i 's/.*libvirtd_opts.*/libvirtd_opts="-d -l"/g' /etc/default/libvirt-bin''')
    con.process.execute('''sed -i 's/libvirtd_opts="-d"/libvirtd_opts="-d -l"/g' /etc/init/libvirt-bin.conf''')
    # generate unique uuid for libvirt
    con.process.execute("""sed -i 's/.*host_uuid.*/host_uuid = "'`uuidgen`'"/' /etc/libvirt/libvirtd.conf""")
    con.process.execute("initctl stop libvirt-bin; initctl start libvirt-bin")

    iface_name = con.process.execute("""ip a | awk '/^[0-9]*:/ {{b=$2;gsub(":","",b)}} /{0}/ {{print b;exit}}'""".format(node_ip))[1].strip()

    # nova config
    ####################################################################################################################
    con.process.execute("sed -i 's/br100/pubbr/g'  /etc/nova/nova.conf")

    if iface_name == "pubbr":
        pubbr_iface_port = con.process.execute("awk '/pubbr/{b=1} /bridge_ports/{if(b){print $2; exit}}' /etc/network/interfaces")[1].strip()
    else:
        pubbr_iface_port = iface_name
    print pubbr_iface_port

    con.process.execute("sed -i 's/flat_interface.*/flat_interface = {0}/g' /etc/nova/nova.conf".format(pubbr_iface_port))
    con.process.execute("sed -i 's/vlan_interface.*/vlan_interface = {0}/g' /etc/nova/nova.conf".format(pubbr_iface_port))

    con.process.execute("sed -i 's/^instances_path.*//g' /etc/nova/nova.conf")
    con.process.execute("sed -i 's/vncserver_listen.*/vncserver_listen = 0.0.0.0/g' /etc/nova/nova.conf")
    con.process.execute("""sed -i 's/instance_name_template.*/instance_name_template = "%(hostname)s"/g' /etc/nova/nova.conf""")
    con.process.execute("sed -i 's/force_config_drive.*/force_config_drive = False/g' /etc/nova/nova.conf")
    con.process.execute("sed -i '/public_interface/a live_migration_flag = VIR_MIGRATE_UNDEFINE_SOURCE,VIR_MIGRATE_PEER2PEER,VIR_MIGRATE_LIVE' /etc/nova/nova.conf")
    con.process.execute(r"sed -i 's/\[DEFAULT\]/[DEFAULT]\nuse_cow_images = False/' /etc/nova/nova.conf")
    con.process.execute("""cat <<EOF >> /etc/nova/nova.conf
[serial_console]
base_url = http://127.0.0.1:6083/
enabled = True
listen = 127.0.0.1
port_range = 10000:20000
proxyclient_address = 127.0.0.1
EOF
echo 1""")

    cmd = """
export OS_USERNAME=admin
export OS_PASSWORD=rooter
export OS_TENANT_NAME=admin
export OS_AUTH_URL=http://{node_ip}:35357/v2.0

# configure cinder (on controller node only)
# cinder type-create {cinder_type_name}
# cinder type-key {cinder_type_name} set volume_backend_name={vpool_name}

tenant_id=$(keystone tenant-get admin | awk '/id/ {{print $4}}')
cinder quota-update --volumes {max_volumes} --snapshots {max_snapshots} --gigabytes {max_gigabytes} $tenant_id
cinder quota-update --volumes {max_volumes} --snapshots {max_snapshots} --gigabytes {max_gigabytes} --volume-type {cinder_type_name} $tenant_id

nova keypair-add --pub-key ~/.ssh/id_rsa.pub mykey

echo 1""".format(vpool_name=vpool_name,
                 node_ip=node_ip,
                 cinder_type_name=cinder_type_name,
                 max_volumes=max_volumes,
                 max_snapshots=max_snapshots,
                 max_gigabytes=max_gigabytes)

    if master_ip is None:
        con.process.execute(cmd)

    # restart services
    ####################################################################################################################
    # fix for screen socket detaching
    try:
        kill_service_in_screen("c-vol")
    except:
        screen_pid = con.process.execute("ps ax | awk '/SCREEN/ && /stack/ && !/awk/ {print $1}'")[1].strip()
        # sending SIGCHLD to screen process will make it recreate the socket if its missing
        con.process.execute("kill -SIGCHLD {0}".format(screen_pid))
        kill_service_in_screen("c-vol")

    time.sleep(1)
    con.process.execute("""su -c 'screen -x stack -p c-vol -X stuff "source /etc/profile.d/ovs.sh\n"' stack""")
    time.sleep(1)
    restart_service_in_screen("c-vol")

    services = ["c-api", "c-sch", "n-api", "n-cpu", "n-cond", "n-crt", "n-net", "n-sch", "n-novnc"]
    if master_ip:
        services = ["n-cpu", "n-net", "n-api", "c-sch", "c-api"]

    # restart_services(services)
    if master_ip:
        con.close()
        con = q.remote.system.connect(master_ip, "root", UBUNTU_PASSWORD)
    restart_services(services)

    python_cmd = """
try:
    from ovs.extensions.hypervisor.mgmtcenters.openstack import OpenStackManagement
    from cinderclient.v2 import client as cinder_client
except ImportError:
    print "OpenStackManagement modules not found - not executing"
    exit(0)

osm = OpenStackManagement(cinder_client)
osm._restart_devstack_screen()
"""

    cmd = """cat <<EOF > /tmp/restart_devstack_services.py
{0}
EOF
""".format(python_cmd)
    con.process.execute(cmd, dieOnNonZeroExitCode=False)
    cmd = """
export PYTHONPATH=:/opt/OpenvStorage:/opt/OpenvStorage/webapps
python /tmp/restart_devstack_services.py
echo 1 > /dev/null"""
    print con.process.execute(cmd)


def copy_stack_user_ssh_keys(master_ip):
    """
    call if stable/icehouse and all nodes have been installed
    """

    con = q.remote.system.connect(master_ip, "root", UBUNTU_PASSWORD)

    devstack_branch = con.process.execute("cd /home/devstack/; git branch | awk '{print $2}'")[1].strip()
    if devstack_branch != "stable/icehouse":
        return

    cmd = 'source /etc/profile.d/ovs.sh;python -c "from ovs.dal.lists.storagerouterlist import StorageRouterList;print [sg.ip for sg in StorageRouterList.get_storagerouters()]"'
    out = con.process.execute(cmd)[1]
    node_ips = eval(out)
    con.close()

    cmd_ssh_id_gen = r"""apt-get install sshpass -y
chpasswd <<< "stack:{password}"
su -c "ssh-keygen -f ~/.ssh/id_rsa -t rsa -b 4096 -q -N \"\"" stack
echo 1""".format(password=UBUNTU_PASSWORD)

    for node_ip in node_ips:
        con2 = q.remote.system.connect(node_ip, "root", UBUNTU_PASSWORD)
        con2.process.execute(cmd_ssh_id_gen)
        con2.close()

    for node_ip in node_ips:
        con2 = q.remote.system.connect(node_ip, "root", UBUNTU_PASSWORD)
        for other_node_ip in node_ips:
            if other_node_ip == node_ip:
                continue
            cmd = 'su -c "echo {password} | sshpass ssh-copy-id stack@{other_node_ip} -o StrictHostKeyChecking=no" stack'.format(password=UBUNTU_PASSWORD, other_node_ip=other_node_ip)
            con2.process.execute(cmd)
        con2.close()


def install_additional_node(hypervisor_type, hypervisor_ip, hypervisor_password, first_node_ip, new_node_ip,
                            qualitylevel, cluster_name, dns, public_network, public_netmask, gateway, hostname,
                            storage_ip_last_octet=None, with_devstack=False, fixed_range=None, fixed_range_size=None,
                            floating_range=None, branch_name="", tag_name="", flat_interface="eth0"):
    # check connectivity
    q.clients.ssh.waitForConnection(first_node_ip, "root", UBUNTU_PASSWORD, times=30)

    if hypervisor_type == "VMWARE":
        deploy_ovsvsa_vmware(public_ip=new_node_ip,
                             hypervisor_ip=hypervisor_ip,
                             hypervisor_password=hypervisor_password,
                             dns=dns,
                             public_network=public_network,
                             gateway=gateway,
                             public_netmask=public_netmask,
                             hostname=hostname,
                             extra_packages=None,
                             storage_ip_last_octet=storage_ip_last_octet)

    q.clients.ssh.waitForConnection(new_node_ip, "root", UBUNTU_PASSWORD, times=30)

    if with_devstack:
        install_devstack(node_ip=new_node_ip,
                         fixed_range=fixed_range,
                         fixed_range_size=fixed_range_size,
                         floating_range=floating_range,
                         flat_interface=flat_interface,
                         master_node_ip=first_node_ip,
                         branch_name=branch_name,
                         tag_name=tag_name)

    handle_ovs_setup(public_ip=new_node_ip,
                     qualitylevel=qualitylevel,
                     cluster_name=cluster_name,
                     hypervisor_type=hypervisor_type,
                     hypervisor_ip=hypervisor_ip,
                     hypervisor_password=hypervisor_password,
                     hostname=hostname)

    setup_mgmt_center(public_ip=new_node_ip)

    con = q.remote.system.connect(first_node_ip, "root", UBUNTU_PASSWORD)
    _, out = con.process.execute('source /etc/profile.d/ovs.sh;python -c "from ovs.dal.lists.storagerouterlist import StorageRouterList;print [sr.ip for sr in StorageRouterList.get_storagerouters()]"')
    nodes = eval(out)
    for node in nodes:
        if node != new_node_ip:
            con = q.remote.system.connect(node, "root", UBUNTU_PASSWORD)
            con.process.execute("initctl restart ovs-workers")


def apply_vpool_to_all_nodes(master_ip, vpool_name="saio"):
    q.clients.ssh.waitForConnection(master_ip, "root", UBUNTU_PASSWORD, times=60)
    con = q.remote.system.connect(master_ip, "root", UBUNTU_PASSWORD)

    cmd = '''source /etc/profile.d/ovs.sh
python -c "
from ovs.lib.storagerouter           import StorageRouterController
from ovs.dal.lists.storagerouterlist import StorageRouterList
from ovs.dal.lists.storagedriverlist import StorageDriverList
from ovs.dal.lists.vpoollist         import VPoolList

vpool_name = '{vpool_name}'
master_ip  = '{master_ip}'

vpool = VPoolList.get_vpool_by_name(vpool_name)
assert vpool, 'Vpool with name ' + vpool_name + 'not found'

storagedriver = vpool.storagedrivers[0]

parameters = {{'vpool_name': vpool.name,
              'type': vpool.backend_type.code,
              'connection_host': None if vpool.connection is None else vpool.connection.split(':')[0],
              'connection_port': None if vpool.connection is None else int(vpool.connection.split(':')[1]),
              'connection_username': vpool.login,
              'connection_password': vpool.password,
              'integratemgmt': True,
              'storage_ip': storagedriver.storage_ip,
              'readcache_size': 50,
              'writecache_size': 50}}

existing_storagerouters = [storagedriver.storagerouter.ip for storagedriver in vpool.storagedrivers]

storagerouters = [(sr.ip, sr.machine_id) for sr in StorageRouterList.get_storagerouters() if sr.ip not in existing_storagerouters]

StorageRouterController.update_storagedrivers([], storagerouters, parameters)" '''.format(vpool_name=vpool_name,
                                                                                          master_ip=master_ip)

    print cmd
    print con.process.execute(cmd)


def deploy_ovsvsa_vmware(public_ip,
                         hypervisor_ip,
                         hypervisor_password,
                         dns,
                         public_network,
                         gateway,
                         public_netmask,
                         hostname,
                         extra_packages=None,
                         storage_ip_last_octet=None
                         ):
    assert storage_ip_last_octet, "storage_ip_last_octet needs to be suplied for vmware install"

    hypervisor_login = "root"
    cli = q.hypervisors.cmdtools.esx.cli.connect(hypervisor_ip, hypervisor_login, hypervisor_password)
    vifs = q.hypervisors.cmdtools.esx.vifs.connect(hypervisor_ip, hypervisor_login, hypervisor_password)
    sdk = q.hypervisors.cmdtools.esx.sdk.connect(hypervisor_ip, hypervisor_login, hypervisor_password)

    vmObj, storageEthAdapter, publicEthAdapter = run_deploy_ovs(hypervisor_ip, hypervisor_password, sdk, cli, vifs)

    q.tools.installerci.shutdown_vm_esx(sdk, OVS_NAME)
    q.tools.installerci.poweron_vm_esx(sdk, OVS_NAME)

    storage_nic_mac = storageEthAdapter.macAddress
    command = "python /opt/qbase5/utils/ubuntu_autoinstall.py -M {public_mac_address} \
-m {storage_nic_mac} \
-d {dns} \
-P {public_ip} \
-n {public_network} \
-g {gateway} \
-k {public_netmask} \
-a sda \
-x {hypervisor_ip} \
-b {OVS_NAME} \
-v {UBUNTU_ISO} \
-o {hostname} \
-S {storage_ip_last_octet}"
    command = command.format(public_mac_address=publicEthAdapter.macAddress,
                             storage_nic_mac=storage_nic_mac,
                             dns=dns,
                             public_ip=public_ip,
                             public_network=public_network,
                             gateway=gateway,
                             public_netmask=public_netmask,
                             hypervisor_ip=hypervisor_ip,
                             OVS_NAME=OVS_NAME,
                             UBUNTU_ISO=UBUNTU_ISO,
                             hostname=hostname,
                             storage_ip_last_octet=storage_ip_last_octet
                             )
    if extra_packages:
        command += " -E {extra_packages}".format(extra_packages=extra_packages)

    q.system.process.execute(command)

    q.clients.ssh.waitForConnection(public_ip, "root", UBUNTU_PASSWORD, times=60)


def handle_ovs_setup(public_ip,
                     qualitylevel,
                     cluster_name,
                     hypervisor_type,
                     hypervisor_ip,
                     hypervisor_password,
                     hostname):
    con = q.remote.system.connect(public_ip, "root", UBUNTU_PASSWORD)

    con.process.execute('echo "deb http://packages.cloudfounders.com/apt/ {0}/" > /etc/apt/sources.list.d/ovsaptrepo.list'.format(qualitylevel))
    con.process.execute('apt-get update')
    con.process.execute('apt-get install -y ntp')
    con.process.execute('apt-get install -y --force-yes openvstorage-hc')

    # clean leftover mds
    e, o = con.process.execute("ls /dev/md*", dieOnNonZeroExitCode=False)
    if e == 0:
        for md in o.splitlines():
            e, o = con.process.execute("mdadm --detail {} | awk '/\/dev\/sd?/ {{print $(NF);}}'".format(md),
                                       dieOnNonZeroExitCode=False)
            if e != 0:
                continue
            con.process.execute("mdadm --stop {}".format(md), dieOnNonZeroExitCode=False)
            for d in o.splitlines():
                con.process.execute("mdadm --zero-superblock {}".format(d), dieOnNonZeroExitCode=False)

    child = pexpect.spawn('ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@{0}'.format(public_ip))
    child.timeout = 300

    child.logfile = sys.stdout

    child.expect('password:')
    child.sendline(UBUNTU_PASSWORD)
    child.expect(':~#')

    child.sendline('ovs setup')
    # if qualitylevel in ['beta']:
    #    child.expect('Password:')
    #    child.sendline(UBUNTU_PASSWORD)

    #    idx = child.expect(['Following Open vStorage clusters are found.', 'No existing Open vStorage clusters are found.'])
    #    if idx == 0:
    #        joined_cluster = pick_option(child, cluster_name, fail_if_not_found=False)
    #        if not joined_cluster:
    #            pick_option(child, "Don't join any of these clusters.", use_select=False)
    #            child.expect('Please enter the cluster name')
    #            child.sendline(cluster_name)
    #    else:
    #        child.expect('Please enter the cluster name')
    #        child.sendline(cluster_name)

    # else:
    joined_cluster = pick_option(child, cluster_name, fail_if_not_found=False)
    if not joined_cluster:
        pick_option(child, "Create a new cluster", use_select=False)
        child.expect('Please enter the cluster name')
        child.sendline(cluster_name)

    idx = child.expect(['Select the public ip address of', 'Password:'])
    if idx == 1:
        child.sendline(UBUNTU_PASSWORD)
        child.expect('Select the public ip address of')
    pick_option(child, public_ip)

    if qualitylevel in ['beta']:
        idx = 0
        while idx == 0:
            child.timeout = 30
            idx = child.expect(['Password:', 'Enter number or name; return for next page',
                                'Select Nr:'])
            if idx == 0:
                child.sendline(UBUNTU_PASSWORD)
            elif idx == 1:
                child.expect('\?')
                child.sendline('4')
            elif idx == 2:
                child.sendline('5')

        child.expect('ALL DATA WILL BE ERASED ON THE DISKS ABOVE!')
        child.sendline('yes')

    # 5 minutes to partition disks
    child.timeout = 300
    child.expect(["Which type of hypervisor is this Grid Storage Router",
                  "Which type of hypervisor is this Storage Router backing"])
    pick_option(child, hypervisor_type.upper())

    child.expect("Enter hypervisor hostname")
    child.sendline("")

    if hypervisor_type == "VMWARE":
        child.expect("Enter hypervisor ip address")
        child.sendline(hypervisor_ip)

        try:
            _ = child.expect("Password:")
            child.sendline("R00t3r123")
        except:
            pass
    if qualitylevel in ['beta']:
        child.expect("Select arakoon database mountpoint. Make a selection please:")
        child.sendline("")

    exit_script_mark = "~#"

    # 10 minutes to install ovs components
    child.timeout = 600
    idx = 0
    try:
        idx = child.expect(exit_script_mark)
        return
    except:
        print
        print str(child)
        raise

    child.timeout = 180
    try:
        child.expect("Setup complete")
    except:
        print "--- pexpect before:"
        print child.before
        print "--- pexpect buffer:"
        print child.buffer
        print "--- pexpect after:"
        print child.after
        print "--- pexpect end"
        raise

if __name__ == '__main__':

    options, remainder = getopt.getopt(sys.argv[1:], 'e:w:p:n:g:k:d:q:c:l:h:E:H:M:S:s:N')

    for opt, arg in options:
        if opt == '-e':
            hypervisor_ip = arg
        if opt == '-w':
            hypervisor_password = arg
        if opt == '-p':
            public_ip = arg
        if opt == '-n':
            public_network = arg
        if opt == '-g':
            gateway = arg
        if opt == '-k':
            public_netmask = arg
        if opt == '-d':
            dns = arg
        if opt == '-q':
            qualitylevel = arg
        if opt == '-c':
            cluster_name = arg
        if opt == '-l':
            vpool_type = arg.strip().lower()
            assert vpool_type in VPOOL_TYPES, "Invalid value for vpool_type, supported are: " + str(VPOOL_TYPES)
        if opt == '-h':
            hostname = arg
        if opt == '-E':
            extra_packages = arg
        if opt == '-H':
            hypervisor_type = arg
            assert hypervisor_type in SUPPORTED_HYPERVISORS, "Supported hypervisor types are {0}".format(SUPPORTED_HYPERVISORS)
        if opt == '-M':
            storage_nic_mac = arg
        if opt == '-S':
            connection_host = arg
        if opt == '-s':
            storage_ip_last_octet = arg
        if opt == '-N':
            install_ovsvsa = False

    assert q.system.net.pingMachine(hypervisor_ip), "Invalid ip given or unreachable"

    hypervisor_password = hypervisor_password or "R00t3r123"
    hypervisor_login = "root"
    qualitylevel = qualitylevel or "test"

    if vpool_type == "swift_s3":
        assert q.system.net.pingMachine(connection_host), "swift_s3 invalid ip or unreachable"

    if hypervisor_type == "KVM":
        public_ip = hypervisor_ip
        assert storage_nic_mac, "storage_nic_mac needs to be specified"
        storage_nic_mac = storage_nic_mac.lower()

    if hypervisor_type == "VMWARE" and install_ovsvsa:
        deploy_ovsvsa_vmware(public_ip=public_ip,
                             hypervisor_ip=hypervisor_ip,
                             hypervisor_password=hypervisor_password,
                             dns=dns,
                             public_network=public_network,
                             gateway=gateway,
                             public_netmask=public_netmask,
                             hostname=hostname,
                             extra_packages=extra_packages,
                             storage_ip_last_octet=storage_ip_last_octet)

    handle_ovs_setup(public_ip=public_ip,
                     qualitylevel=qualitylevel,
                     cluster_name=cluster_name,
                     hypervisor_type=hypervisor_type,
                     hypervisor_ip=hypervisor_ip,
                     hypervisor_password=hypervisor_password,
                     hostname=hostname)

    q.clients.ssh.waitForConnection(public_ip, "root", UBUNTU_PASSWORD, times=120)
    con = q.remote.system.connect(public_ip, "root", UBUNTU_PASSWORD)

    vpool_mount = None
    if vpool_type != "none":
        out = con.process.execute("ip a | awk '/inet/ && /privbr/ {print $2}'")[1]
        net = ipcalc.Network(out)
        storage_ip = ipcalc.IP(out).dq
        excluded_ips = [net.network().dq, net.broadcast().dq, storage_ip]
        print storage_ip
        for ip in net:
            if ip.dq in excluded_ips:
                continue
            if q.system.net.pingMachine(ip.dq):
                continue
            break

        print ip.dq

        if vpool_type == "local":
            vpool_name = "vpool1"
        elif vpool_type == "swift_s3":
            vpool_name = "saio"
            connection_port = "8080"
            connection_password = "testing"
            connection_username = "test:tester"
        elif vpool_type == "alba":
            vpool_name = "alba"

        vpool_mount = '/mnt/dfs/{vpool_name}'.format(vpool_name=vpool_name)

        deploy_vpool(public_ip=public_ip,
                     vpool_name=vpool_name,
                     vpool_type=vpool_type,
                     vpool_host=connection_host,
                     vpool_port=connection_port,
                     vpool_router_port=12323,
                     vpool_storage_ip=storage_ip,
                     qualitylevel=qualitylevel)

        if "VMWARE" in hypervisor_type:
            cli = q.hypervisors.cmdtools.esx.cli.connect(hypervisor_ip, hypervisor_login, hypervisor_password)
            print cli.runShellCommand("esxcfg-vmknic --add --ip={0} --netmask={1} {2}".format(ip.dq, net.netmask().dq, STORAGE_NET_NAME), "/")

            time.sleep(30)
            cmd = "esxcli storage nfs add -H {0} -s /mnt/{1} -v {1}".format(storage_ip, vpool_name)
            print cmd
            print cli.runShellCommand(cmd, "/")
