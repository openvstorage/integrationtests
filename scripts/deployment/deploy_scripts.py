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

from pylabs.InitBaseCore import q
import sys
import time
import random

DEPLOY_OVS_SCRIPT_LOCATION = "https://bitbucket.org/openvstorage/openvstorage/raw/default/scripts/deployment/deployOvs.py"
PUBLIC_NET_NAME = "CloudFramesPublic"
STORAGE_NET_NAME = "CloudFramesStorage"
UBUNTU_ISO = "ubuntu-14.04-alternate-amd64.iso"
UBUNTU_PASSWORD = "rooter"

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

print sys.argv


def randomMAC():
    mac = [0x00, 0x16, 0x3e,
           random.randint(0x00, 0x7f),
           random.randint(0x00, 0xff),
           random.randint(0x00, 0xff)]
    return ':'.join(map(lambda x: "%02x" % x, mac))


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
    con.process.execute("apt-get install curl gcc memcached rsync sqlite3 xfsprogs git-core libffi-dev -y")
    con.process.execute("apt-get install python-setuptools lsscsi unzip -y")
    con.process.execute("apt-get install python-coverage python-dev python-nose python-simplejson python-xattr -y")
    con.process.execute("apt-get install python-eventlet python-greenlet python-pastedeploy python-netifaces -y ")
    con.process.execute("apt-get install python-pip python-dnspython python-mock liberasurecode-dev libjerasure-dev -y")

    disk = con.process.execute('for d in /sys/class/scsi_disk/*; do dev=$(ls $d/device/block);mount | grep $dev > /dev/null || echo $dev;done')[1]
    disk = disk.splitlines()[0].strip()

    con.process.execute('''parted /dev/{0} mklabel gpt
parted /dev/{0} mkpart 1 xfs 0 100%
parted /dev/{0} name 1 swift
mkfs.xfs -f /dev/{0}1'''.format(disk))
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

    # python-swiftclient
    cmd = """cd
git clone https://github.com/openstack/python-swiftclient.git
cd python-swiftclient
python setup.py develop"""
    con.process.execute(cmd)

    # swift
    cmd = """cd
git clone https://github.com/openstack/swift.git
cd swift
python setup.py develop"""
    con.process.execute(cmd)

    cmd = """cp $HOME/swift/doc/saio/rsyncd.conf /etc/
sed -i "s/<your-user-name>/${USER}/" /etc/rsyncd.conf"""
    con.process.execute(cmd)

    # enable rsync (in /etc/default/rsync)
    cmd = """sed -i "s/RSYNC_ENABLE=false/RSYNC_ENABLE=true/"  /etc/default/rsync"""
    con.process.execute(cmd)

    # start rsync
    cmd = "service rsync restart"
    con.process.execute(cmd)

    # test
    con.process.execute("rsync rsync://pub@localhost/")

    # start memcached if not running
    con.process.execute("service memcached start")

    # make sure /etc/swift is empty
    con.process.execute("rm -rf /etc/swift")

    # populate it
    cmd = """cd $HOME/swift/doc && cp -r saio/swift /etc/swift
sudo chown -R ${USER}:${USER} /etc/swift"""
    con.process.execute(cmd)

    # configure username
    cmd = 'find /etc/swift/ -name \*.conf | xargs sudo sed -i "s/<your-user-name>/${USER}/"'
    con.process.execute(cmd)

    # configure /etc/swift/swift.conf
    cmd = """function f { od -t x8 -N 8 -A n </dev/random; }
sed -i "s/swift_hash_path_prefix = changeme/swift_hash_path_prefix = $(f)/" /etc/swift/swift.conf
sed -i "s/swift_hash_path_suffix = changeme/swift_hash_path_suffix = $(f)/" /etc/swift/swift.conf"""
    con.process.execute(cmd)

    # Enable saio scripts:
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

    # construct the initial rings using the provided script
    con.process.execute("/root/bin/remakerings")

    # Start swift
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
