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
    OVSRELEASE=denver-community
    IP=`ip a l dev eth0 | grep "inet " | awk '{split($0,a," "); split(a[2],b,"/"); print(b[1])}'`
    PASSWORD=rooter
    CLUSTER_NAME=dsvmcitesting
    MASTER_IP=$IP
    JOIN_CLUSTER=False
    HYPERVISOR_NAME=`hostname`
    ARAKOON_MNTP=/mnt/db
    sudo sed -i 's/nameserver .*/nameserver 172.19.0.1/g' /etc/resolv.conf
    echo "deb http://testapt.openvstorage.com $OVSRELEASE main" | sudo tee /etc/apt/sources.list.d/ovsaptrepo.list
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
   
    # APPLY PATCHES
    if [ $ZUUL_BRANCH = "master" ]; then
       sudo sed -i "s/('7.0')/('8.0')/g" /opt/OpenvStorage/ovs/extensions/hypervisor/mgmtcenters/management/openstack_mgmt.py
    fi
    sudo bash ${WORKSPACE}/integrationtests/cinderci/dsvm-tempest-full/patches.sh

    # OVS SETUP
    sudo timeout -s 9 10m ovs setup 2>&1 | sudo tee /var/log/ovs_setup.log

    # ADD VPOOL
	export PYTHONPATH="${PYTHONPATH}:/opt/OpenvStorage:/opt/OpenvStorage/webapps"
	export OS_TEST_TIMEOUT=0
    sudo python ${WORKSPACE}/integrationtests/cinderci/dsvm-tempest-full/add_vpool.py 2>&1 | sudo tee -a /var/log/ovs_setup.log
   
    # CONFIGURE TEMPEST
    sudo sed -i 's/#build_timeout = 300/build_timeout = 600/g' /opt/stack/new/tempest/etc/tempest.conf
    sudo sed -i 's/build_timeout = 196/build_timeout = 600/g' /opt/stack/new/tempest/etc/tempest.conf
	sudo sed -i '/\[volume\]/a storage_protocol=OVS' /opt/stack/new/tempest/etc/tempest.conf
    sudo sed -i '/\[volume\]/a vendor_name="Open vStorage"' /opt/stack/new/tempest/etc/tempest.conf
    sudo sed -i '/\[volume\]/a backend1_name=lvmdriver-1' /opt/stack/new/tempest/etc/tempest.conf
    sudo sed -i '/\[volume\]/a backend2_name=local' /opt/stack/new/tempest/etc/tempest.conf
    sudo sed -i '/\[volume-feature-enabled\]/a multi_backend=True' /opt/stack/new/tempest/etc/tempest.conf
    sudo sed -i '/\[volume\]/a volume_size=4' /opt/stack/new/tempest/etc/tempest.conf

    # CONFIGURE CINDER
    sudo sed -i 's/default_volume_type = lvmdriver-1/default_volume_type = local/g' /etc/cinder/cinder.conf
    sudo sed -i 's/enabled_backends = lvmdriver-1, local/enabled_backends = local/g' /etc/cinder/cinder.conf

    sudo ps aux | grep volumedriver | sudo tee -a /var/log/ovs_setup.log
    sudo cat /etc/cinder/cinder.conf | sudo tee -a /var/log/ovs_setup.log
   	sudo vgdisplay | sudo tee -a /var/log/ovs_setup.log
   	sudo cat /opt/stack/new/tempest/etc/tempest.conf | sudo tee -a /var/log/ovs_setup.log

   	# DISABLE SOME TESTS
    sudo rm -f /opt/stack/new/tempest/tempest/api/object_storage/test_container_sync_middleware.py
    sudo rm -f /opt/stack/new/tempest/tempest/scenario/test_swift_telemetry_middleware.py
    sudo rm -f /opt/stack/new/tempest/tempest/api/telemetry/test_telemetry_notification_api.py
    sudo rm -f /opt/stack/new/tempest/tempest/api/telemetry/test_telemetry_alarming_api.py
    sudo rm -f /opt/stack/new/tempest/tempest/scenario/test_object_storage_telemetry_middleware.py

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
