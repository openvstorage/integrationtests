#!/bin/bash -xe
export PATH=$PATH:/sbin
echo "Network interface addresses...";
ip address show
echo "Network routing tables...";
ip route show
ip -6 route show
echo "Network neighbors...";
ip neighbor show

if [[ ! -e devstack-gate ]]; then
    git clone git://git.openstack.org/openstack-infra/devstack-gate
else
    cd devstack-gate
    git remote set-url origin git://git.openstack.org/openstack-infra/devstack-gate
    git remote update
    git reset --hard
    if ! git clean -x -f ; then
        sleep 1
        git clean -x -f
    fi
    git checkout master
    git reset --hard remotes/origin/master
    if ! git clean -x -f ; then
        sleep 1
        git clean -x -f
    fi
    cd ..
fi

if [ -z $ZUUL_PROJECT ]; then
    export ZUUL_PROJECT=openstack-dev/sandbox
fi
if [ -z $ZUUL_BRANCH ]; then
    export ZUUL_BRANCH=master
fi
export PYTHONUNBUFFERED=true
export DEVSTACK_GATE_TIMEOUT=180
export DEVSTACK_GATE_TEMPEST=1
export RE_EXEC=true
export DEVSTACK_LOCAL_CONFIG="disable_service ceilometer-acompute ceilometer-acentral ceilometer-collector ceilometer-api"

function pre_test_hook {
    sudo sed -i '/function load_subunit_stream/i call_hook_if_defined "post_devstack_hook"' /opt/stack/new/devstack-gate/devstack-vm-gate.sh
    sudo sed -i 's/USE_SCREEN=False/USE_SCREEN=True/g' /opt/stack/new/devstack-gate/devstack-vm-gate.sh
    sudo sed -i 's/ADMIN_PASSWORD=secretadmin/ADMIN_PASSWORD=rooter/g' /opt/stack/new/devstack-gate/devstack-vm-gate.sh
    sudo sed -i 's/VOLUME_BACKING_FILE_SIZE=24G/VOLUME_BACKING_FILE_SIZE=32772M/g' /opt/stack/new/devstack-gate/devstack-vm-gate.sh
}

export -f pre_test_hook

function post_devstack_hook {
    IP=`ip a l dev eth0 | grep "inet " | awk '{split($0,a," "); split(a[2],b,"/"); print(b[1])}'`
    PASSWORD=rooter
    CLUSTER_NAME=dsvmcitesting
    MASTER_IP=$IP
    JOIN_CLUSTER=False
    HYPERVISOR_NAME=`hostname`
    ARAKOON_MNTP=/mnt/db
    sudo sed -i 's/nameserver .*/nameserver 172.19.0.1/g' /etc/resolv.conf
    echo 212.88.230.99 packages.cloudfounders.com | sudo tee -a /etc/hosts
    echo "deb http://packages.cloudfounders.com/apt/ alpha/" | sudo tee -a /etc/apt/sources.list.d/ovsaptrepo.list
    sudo apt-get update
    sudo apt-get install openvstorage -y --force-yes
    
    sudo touch /tmp/openvstorage_preconfig.cfg
    echo "[setup]" | sudo tee /tmp/openvstorage_preconfig.cfg
    echo "target_ip = $IP" | sudo tee -a /tmp/openvstorage_preconfig.cfg
    echo "target_password = $PASSWORD" | sudo tee -a /tmp/openvstorage_preconfig.cfg
    echo "cluster_ip = $IP" | sudo tee -a /tmp/openvstorage_preconfig.cfg
    echo "cluster_name = $CLUSTER_NAME" | sudo tee -a /tmp/openvstorage_preconfig.cfg
    echo "join_cluster = $JOIN_CLUSTER" | sudo tee -a /tmp/openvstorage_preconfig.cfg
    echo "master_ip = $MASTER_IP" | sudo tee -a /tmp/openvstorage_preconfig.cfg
    echo "hypervisor_ip = 127.0.0.1" | sudo tee -a /tmp/openvstorage_preconfig.cfg
    echo "hypervisor_type = KVM" | sudo tee -a /tmp/openvstorage_preconfig.cfg
    echo "hypervisor_name = $HYPERVISOR_NAME" | sudo tee -a /tmp/openvstorage_preconfig.cfg
    echo "hypervisor_username = root" | sudo tee -a /tmp/openvstorage_preconfig.cfg
    echo "hypervisor_password = $PASSWORD" | sudo tee -a /tmp/openvstorage_preconfig.cfg
    echo "arakoon_mountpoint = $ARAKOON_MNTP" | sudo tee -a /tmp/openvstorage_preconfig.cfg
    echo "verbose = True" | sudo tee -a /tmp/openvstorage_preconfig.cfg
    echo "auto_config = True" | sudo tee -a /tmp/openvstorage_preconfig.cfg
    echo "disk_layout = {'/mnt/bfs': {'device': 'DIR_ONLY', 'percentage':100, 'label':'', 'type':'storage', 'ssd': False},'/mnt/cache1': {'device': 'DIR_ONLY', 'percentage':100, 'label':'', 'type':'readcache', 'ssd': False},'/mnt/cache2': {'device': 'DIR_ONLY', 'percentage':100, 'label':'', 'type':'writecache', 'ssd': False},'/mnt/db': {'device': 'DIR_ONLY', 'percentage':100, 'label':'', 'type':'storage', 'ssd': False},'/mnt/md': {'device': 'DIR_ONLY', 'percentage':100, 'label':'', 'type':'storage', 'ssd': False},'/var/tmp': {'device': 'DIR_ONLY', 'percentage':100, 'label':'', 'type':'storage', 'ssd': False}}" | sudo tee -a /tmp/openvstorage_preconfig.cfg
    echo "configure_memcached = True" | sudo tee -a /tmp/openvstorage_preconfig.cfg
    echo "configure_rabbitmq = True" | sudo tee -a /tmp/openvstorage_preconfig.cfg
    
    #************************************
    sudo cat /root/.ssh/id_rsa.pub | sudo tee -a /opt/OpenvStorage/.ssh/authorized_keys
	sudo cat /home/jenkins/.ssh/id_rsa.pub | sudo tee -a /opt/OpenvStorage/.ssh/authorized_keys
	sudo chmod 755 /opt/OpenvStorage/.ssh
	sudo cp /home/ubuntu/.ssh/authorized_keys /root/.ssh/
	sudo cat /root/.ssh/id_rsa.pub | sudo tee -a /root/.ssh/authorized_keys
    touch /home/jenkins/.ssh/known_hosts
    touch /home/jenkins/.ssh/authorized_keys
	sudo ssh-keygen -f /home/jenkins/.ssh/known_hosts -R localhost
	sudo ssh-keygen -f /home/jenkins/.ssh/known_hosts -R 127.0.0.1
	ssh-keyscan -H localhost | sudo tee -a /home/jenkins/.ssh/known_hosts
	ssh-keyscan -H 127.0.0.1 | sudo tee -a /home/jenkins/.ssh/known_hosts
	ssh-keyscan -H $IP | sudo tee -a /home/jenkins/.ssh/known_hosts
	ssh-keyscan -H localhost | sudo tee -a /root/.ssh/known_hosts
	ssh-keyscan -H 127.0.0.1 | sudo tee -a /root/.ssh/known_hosts
	ssh-keyscan -H $IP | sudo tee -a /root/.ssh/known_hosts
	cat /home/jenkins/.ssh/id_rsa.pub | sudo tee -a /root/.ssh/authorized_keys
	sudo cat /root/.ssh/id_rsa.pub | sudo tee -a /root/.ssh/authorized_keys
	sudo cat /home/jenkins/.ssh/id_rsa.pub | sudo tee -a /root/.ssh/authorized_keys
	echo "127.0.0.1 `hostname`" | sudo tee -a /etc/hosts
	echo "    NoHostAuthenticationForLocalhost yes" | sudo tee -a /etc/ssh/ssh_config
    sudo sed -i 's/PermitRootLogin no/PermitRootLogin yes/g' /etc/ssh/sshd_config
	sudo sed -i 's/PasswordAuthentication no/PasswordAuthentication yes/g' /etc/ssh/sshd_config
	sudo service ssh restart
    #************************************
   
    #ISSUES WITH ADDING VPOOL
    sudo sed -i 's|/opt/stack/cinder/cinder/|/opt/stack/new/cinder/cinder/|g' /opt/OpenvStorage/ovs/extensions/hypervisor/mgmtcenters/management/openstack_mgmt.py
    sudo sed -i 's|/opt/stack/new/nova/nova/virt/libvirt/volume.py|/opt/stack/new/nova/nova/virt/libvirt/volume/volume.py|g' /opt/OpenvStorage/ovs/extensions/hypervisor/mgmtcenters/management/openstack_mgmt.py
	if [ $ZUUL_BRANCH = "master" ]; then
       sudo sed -i "s/('7.0')/('8.0')/g" /opt/OpenvStorage/ovs/extensions/hypervisor/mgmtcenters/management/openstack_mgmt.py
    fi
    echo "diff --git a/ovs/lib/disk.py b/ovs/lib/disk.py
index 24149bc..c519ee2 100644
--- a/ovs/lib/disk.py
+++ b/ovs/lib/disk.py
@@ -67,7 +67,8 @@ class DiskController(object):
             with Remote(storagerouter.ip, [Context, os]) as remote:
                 context = remote.Context()
                 devices = [device for device in context.list_devices(subsystem='block')
-                           if 'ID_TYPE' in device and device['ID_TYPE'] == 'disk']
+                           if 'ID_TYPE' in device and device['ID_TYPE'] == 'disk'
+                           or (device['DEVTYPE'] in ('disk', 'partition') and device['DEVNAME'].startswith('/dev/vda'))]
                 for device in devices:
                     is_partition = device['DEVTYPE'] == 'partition'
                     device_path = device['DEVNAME']
@@ -97,9 +98,10 @@ class DiskController(object):
                     for path_type in ['by-id', 'by-uuid']:
                         if path is not None:
                             break
-                        for item in device['DEVLINKS'].split(' '):
-                            if path_type in item:
-                                path = item
+                        if 'DEVLINKS' in device:
+                            for item in device['DEVLINKS'].split(' '):
+                                if path_type in item:
+                                    path = item
                     if path is None:
                         path = device_path
                     sectors = int(client.run('cat /sys/block/{0}/size'.format(device_name)))
" | sudo tee /opt/OpenvStorage/patch_disk.diff
    sudo cat /opt/OpenvStorage/patch_disk.diff
    sudo patch /opt/OpenvStorage/ovs/lib/disk.py /opt/OpenvStorage/patch_disk.diff
    sudo timeout -s 9 10m ovs setup 2>&1 | sudo tee /var/log/ovs_setup.log
 
	export PYTHONPATH="${PYTHONPATH}:/opt/OpenvStorage:/opt/OpenvStorage/webapps"
	export OS_TEST_TIMEOUT=0
    
    cat << EOF > /home/jenkins/add_vpool.py
from ovs.extensions.generic.system import System
from ovs.dal.hybrids.mgmtcenter import MgmtCenter
from ovs.dal.hybrids.diskpartition import DiskPartition
from ovs.dal.lists.storagerouterlist import StorageRouterList
from ovs.lib.storagerouter import StorageRouterController
from ovs.extensions.hypervisor.mgmtcenters.management.openstack_mgmt import OpenStackManagement
pmachine = System.get_my_storagerouter().pmachine
mgmt_center = MgmtCenter(data={'name':'Openstack', 'description':'test', 'username':'admin', 'password':'rooter', 'ip':'127.0.0.1', 'port':80, 'type':'OPENSTACK', 'metadata':{'integratemgmt':True}})
mgmt_center.save()
pmachine.mgmtcenter = mgmt_center
pmachine.save()
osm = OpenStackManagement(None)
osm.configure_host('$IP')
for sr in StorageRouterList.get_storagerouters():
     partition = sr.disks[0].partitions[0]
     for role in [DiskPartition.ROLES.DB, DiskPartition.ROLES.SCRUB, DiskPartition.ROLES.READ, DiskPartition.ROLES.READ]:
         partition.roles.append(roles)
     partition.save()
StorageRouterController.add_vpool.apply_async(kwargs={'parameters': {'storagerouter_ip':'$IP', 'vpool_name': 'local', 'type':'local', 'readcache_size': 1, 'writecache_size': 1, 'mountpoint_bfs':'/mnt/bfs', 'mountpoint_temp':'/mnt/tmp', 'mountpoint_md':'/mnt/md', 'mountpoint_readcaches':['/mnt/cache1'], 'mountpoint_writecaches':['/mnt/cache2'], 'mountpoint_foc':'/mnt/cache1', 'storage_ip':'127.0.0.1', 'vrouter_port':12326, 'integratemgmt':True, 'connection_backend': {}, 'connection_password':'', 'connection_username':'', 'connection_host':'', 'connection_port':12326, 'config_params': {'dtl_mode': 'sync', 'sco_size': 4, 'dedupe_mode': 'dedupe', 'dtl_enabled': False, 'dtl_location': '/mnt/cache1', 'write_buffer': 128, 'cache_strategy': 'on_read'}}}).get(timeout=300)
EOF
    
    sudo cp /home/jenkins/add_vpool.py /opt/OpenvStorage/add_vpool.py  
    sudo python /opt/OpenvStorage/add_vpool.py 2>&1 | sudo tee -a /var/log/ovs_setup.log
   
   
    sudo sed -i 's/#build_timeout = 300/build_timeout = 600/g' /opt/stack/new/tempest/etc/tempest.conf
    sudo sed -i 's/build_timeout = 196/build_timeout = 600/g' /opt/stack/new/tempest/etc/tempest.conf
	sudo sed -i '/\[volume\]/a storage_protocol=OVS' /opt/stack/new/tempest/etc/tempest.conf
    sudo sed -i '/\[volume\]/a vendor_name="Open vStorage"' /opt/stack/new/tempest/etc/tempest.conf
    sudo sed -i '/\[volume\]/a backend1_name=lvmdriver-1' /opt/stack/new/tempest/etc/tempest.conf
    sudo sed -i '/\[volume\]/a backend2_name=local' /opt/stack/new/tempest/etc/tempest.conf
    sudo sed -i '/\[volume-feature-enabled\]/a multi_backend=True' /opt/stack/new/tempest/etc/tempest.conf
    sudo sed -i '/\[volume\]/a volume_size=4' /opt/stack/new/tempest/etc/tempest.conf
    
    ps aux | grep volumedriver
    sudo cat /etc/cinder/cinder.conf
   
   	sudo vgdisplay
    sudo rm -f /opt/stack/new/tempest/tempest/api/object_storage/test_container_sync_middleware.py
    sudo rm -f /opt/stack/new/tempest/tempest/scenario/test_swift_telemetry_middleware.py
    sudo rm -f /opt/stack/new/tempest/tempest/api/telemetry/test_telemetry_notification_api.py
    sudo rm -f /opt/stack/new/tempest/tempest/api/telemetry/test_telemetry_alarming_api.py
    sudo rm -f /opt/stack/new/tempest/tempest/scenario/test_object_storage_telemetry_middleware.py
    sudo cat /opt/stack/new/tempest/etc/tempest.conf
}

export -f post_devstack_hook

export DEVSTACK_GATE_TEMPEST_ALL=1
export CINDER_ENABLED_BACKENDS="lvmdriver-1,local"
export TEMPEST_VOLUME_DRIVER=openvstorage
export TEMPEST_VOLUME_VENDOR="Open vStorage"
export TEMPEST_STORAGE_PROTOCOL=OVS
export BUILD_TIMEOUT=600


cp devstack-gate/devstack-vm-gate-wrap.sh ./safe-devstack-vm-gate-wrap.sh
./safe-devstack-vm-gate-wrap.sh
