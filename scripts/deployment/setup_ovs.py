# Copyright 2016 iNuron NV
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

"""
Class to configure OVS via Jenkins
"""

import re
import sys
import getopt
import ipcalc
import pexpect
from pylabs.InitBaseCore import q

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



def _pick_option(pexpect_child, opt_name, fail_if_not_found=True, use_select=True):
    """
    Pick an option
    :param pexpect_child: Child
    :param opt_name: Option name
    :param fail_if_not_found: Raise AssertionError if not found
    :param use_select: Use select
    :return: True if option found
    """
    if use_select:
        pexpect_child.expect('Select Nr:')
    option = [l for l in pexpect_child.before.splitlines() if opt_name in l]
    assert option or not fail_if_not_found, "Option {0} not found\n{1}".format(opt_name, pexpect_child.before)
    if option:
        option = option[0].split(":")[0].strip()
        pexpect_child.sendline(option)
    return bool(option)


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
    _pick_option(child, PUBLIC_NET_NAME)

    child.expect('Please select your storage network:')
    _pick_option(child, STORAGE_NET_NAME)

    child.expect('Specify the size in GB')
    child.sendline('')

    select_ssd = "Select an SSD device"
    select_hdd = "Select an HDD device"
    idx = child.expect([select_ssd, select_hdd, "~ #"])
    if idx in [0, 1]:
        child.expect("Select Nr:")
        child.sendline("1")

        idx = child.expect([select_hdd, "~ #"])
        if idx == 0:
            child.expect("Select Nr:")
            child.sendline("1")
            child.expect("~ #")

    vm_objects = q.tools.installerci.get_vm_objects_esx(sdk, ['name', 'config'])
    vm_object = [v for v in vm_objects if v.name == OVS_NAME]
    assert vm_object, "DeployOvs script failed to create vm"
    vm_object = vm_object[0]

    storage_eth_adapter = [dev for dev in vm_object.config.hardware.device if dev.deviceInfo.summary == STORAGE_NET_NAME][0]
    public_eth_adapter = [dev for dev in vm_object.config.hardware.device if dev.deviceInfo.summary == PUBLIC_NET_NAME][0]

    return storage_eth_adapter, public_eth_adapter


def create_autotest_cfg(os_name, vmware_info, template_server, screen_capture, vpool_config, vpool_name, backend_name,
                        cinder_type, grid_ip, test_project, testrail_server, testrail_key, output_folder, qualitylevel):

    cmd = '''cat << EOF > /opt/OpenvStorage/ci/config/autotest.cfg
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
output_folder = {output_folder}
qualitylevel = {qualitylevel}

{vpool_config}

[vpool2]
vpool_name = localvp
vpool_type = local
vpool_type_name = Local FS
vpool_host =
vpool_port =
vpool_access_key =
vpool_secret_key =
vpool_dtl_mp = /mnt/cache3/localvp/foc
vpool_vrouter_port  = 12345
vpool_storage_ip = 127.0.0.1
vpool_config_params = {{"dtl_mode": "a_sync", "sco_size": 4, "dedupe_mode": "dedupe", "cache_strategy": "on_read", "write_buffer": 128}}

[backend]
name = marie
type = alba
nr_of_disks_to_claim = 3
type_of_disks_to_claim = SATA

[openstack]
cinder_type = {cinder_type}

[testrail]
key = {testrail_key}
server = {testrail_server}
test_project = {test_project}

[mgmtcenter]
name = hmc
username = admin
password = rooter
type = OPENSTACK
port = 443
ip = {grid_ip}

[logger]
default_name = autotest
default_file = main.log
level = INFO
path = /var/log/ovs/autotests
EOF
'''.format(os_name=os_name,
           vmware_info=vmware_info,
           template_server=template_server,
           screen_capture=screen_capture,
           vpool_config=vpool_config,
           vpool_name=vpool_name,
           backend_name=backend_name,
           cinder_type=cinder_type,
           grid_ip=grid_ip,
           test_project=test_project,
           testrail_server=testrail_server,
           testrail_key=testrail_key,
           qualitylevel=qualitylevel,
           output_folder=output_folder)

    return cmd


def get_swift_vpool_config(vpool_host_ip, vpool_storage_ip, vpool_name, vpool_type):
    return """
[vpool]
vpool_name = {vpool_name}
vpool_type = {vpool_type}
vpool_type_name     = Swift S3
vpool_host          = {vpool_host_ip}
vpool_port          = 8080
vpool_access_key    = test:tester
vpool_secret_key    = testing
vpool_dtl_mp    = /mnt/cache1/saio/foc
vpool_vrouter_port  = 12345
vpool_storage_ip    = {vpool_storage_ip}
vpool_config_params = {{"dtl_mode": "a_sync", "sco_size": 4, "dedupe_mode": "dedupe", "cache_strategy": "on_read", "write_buffer": 128}}
""".format(vpool_host_ip=vpool_host_ip,
           vpool_storage_ip=vpool_storage_ip,
           vpool_name=vpool_name,
           vpool_type=vpool_type)


def get_alba_vpool_config(vpool_name, vpool_type):
    return """
[vpool]
vpool_name = {vpool_name}
vpool_type = {vpool_type}
vpool_type_name = Open vStorage Backend
vpool_host =
vpool_port = 80
vpool_access_key =
vpool_secret_key =
vpool_dtl_mp = /mnt/cache1/alba/foc
vpool_vrouter_port  = 12345
vpool_storage_ip = 0.0.0.0
vpool_config_params = {{"dtl_mode": "a_sync", "sco_size": 4, "dedupe_mode": "dedupe", "cache_strategy": "on_read", "write_buffer": 128}}
""".format(vpool_name=vpool_name,
           vpool_type=vpool_type)


def deploy_ovsvsa_vmware(public_ip, hypervisor_ip, hypervisor_password, dns, public_network, gateway, public_netmask,
                         hostname, extra_packages=None, storage_ip_last_octet=None):


    assert storage_ip_last_octet, "storage_ip_last_octet needs to be suplied for vmware install"
    hypervisor_login = "root"
    cli = q.hypervisors.cmdtools.esx.cli.connect(hypervisor_ip, hypervisor_login, hypervisor_password)
    vifs = q.hypervisors.cmdtools.esx.vifs.connect(hypervisor_ip, hypervisor_login, hypervisor_password)
    sdk = q.hypervisors.cmdtools.esx.sdk.connect(hypervisor_ip, hypervisor_login, hypervisor_password)
    vmobj, storage_eth_adapter, public_eth_adapter = run_deploy_ovs(hypervisor_ip, hypervisor_password, sdk, cli, vifs)
    q.tools.installerci.shutdown_vm_esx(sdk, OVS_NAME)
    q.tools.installerci.poweron_vm_esx(sdk, OVS_NAME)
    storage_nic_mac = storage_eth_adapter.macAddress
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
    command = command.format(public_mac_address=public_eth_adapter.macAddress,
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


def handle_ovs_setup(public_ip, qualitylevel, cluster_name, hypervisor_type, hypervisor_ip, hypervisor_password,
                     hostname, branch):
    remote_con = q.remote.system.connect(public_ip, "root", UBUNTU_PASSWORD)
    remote_con.process.execute('echo "deb http://apt.openvstorage.org {0} main" > /etc/apt/sources.list.d/ovsaptrepo.list'.format(qualitylevel))

    remote_con.process.execute('apt-get update')
    remote_con.process.execute('apt-get install -y ntp')
    remote_con.process.execute('apt-get install -y --force-yes openvstorage-hc')
    # clean leftover mds
    e, o = remote_con.process.execute("ls /dev/md*", dieOnNonZeroExitCode=False)
    if e == 0:
        for md in o.splitlines():
            e, o = remote_con.process.execute("mdadm --detail {} | awk '/\/dev\/sd?/ {{print $(NF);}}'".format(md),
                                              dieOnNonZeroExitCode=False)
            if e != 0:
                continue
            remote_con.process.execute("mdadm --stop {}".format(md), dieOnNonZeroExitCode=False)
            for d in o.splitlines():
                remote_con.process.execute("mdadm --zero-superblock {}".format(d), dieOnNonZeroExitCode=False)

    if branch != '':
        repo_map = {'framework': {'config': '/opt/OpenvStorage/config',
                                  'ovs': '/opt/OpenvStorage/ovs',
                                  'webapps': '/opt/OpenvStorage/webapps'},
                    'framework-alba-plugin': {'ovs': '/opt/OpenvStorage/ovs',
                                              'webapps': '/opt/OpenvStorage/webapps'},
                    'alba-asdmanager': {'config': '/opt/asd-manager/config',
                                        'source': '/opt/asd-manager/source'}
                    }
        _patch_code_with(branch, repo_map, remote_con)

    child = pexpect.spawn('ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@{0}'.format(public_ip))
    child.timeout = 30
    child.logfile = sys.stdout
    child.expect('password:')
    child.sendline(UBUNTU_PASSWORD)
    child.expect(':~#')
    child.sendline('ovs setup')
    joined_cluster = _pick_option(child, cluster_name, fail_if_not_found=False)
    if not joined_cluster:
        _pick_option(child, "Create a new cluster", use_select=False)
        child.expect('Please enter the cluster name')
        child.sendline(cluster_name)
    idx = child.expect(['Select the public ip address of', 'Password:'])
    if idx == 1:
        child.sendline(UBUNTU_PASSWORD)
        child.expect('Select the public ip address of')
    _pick_option(child, public_ip)

    # 5 minutes to partition disks
    child.timeout = 300

    provide_root_pwds = True
    while provide_root_pwds:
        idx = child.expect(["Which type of hypervisor is this Grid Storage Router",
                            "Which type of hypervisor is this Storage Router backing",
                            "Password:"])
        if idx == 2:
            child.sendline(UBUNTU_PASSWORD)
        else:
            provide_root_pwds = False

    _pick_option(child, hypervisor_type.upper())
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
    exit_script_mark = "~#"

    # 10 minutes to install ovs components
    child.timeout = 600

    try:
        # IP address to be used for the ASD API
        idx = child.expect(["Select the public IP address to be used for the API", exit_script_mark])
        if idx == 0:
            _pick_option(child, public_ip)
            # port - default 8500
            child.sendline("")
            # IP addresses to be used for the ASDs - default all
            child.sendline("")
            # port to be used for the ASDs - default 8600
            child.sendline("")
        elif idx == 1:
            return
    except:
        print
        print str(child)
        raise
    child.timeout = 180
    try:
        child.expect(exit_script_mark)
    except:
        print "--- pexpect before:"
        print child.before
        print "--- pexpect buffer:"
        print child.buffer
        print "--- pexpect after:"
        print child.after
        print "--- pexpect end"
        raise


def _patch_code_with(branch, repo_map, remote_con):

    remote_con.process.execute("apt-get install -y git")
    url = 'https://github.com/openvstorage/{0}.git'

    for repo in repo_map.iterkeys():
        print remote_con.process.execute("cd /tmp; rm -rf /tmp/{0}".format(repo) + "; git clone " + url.format(repo))
        exit_code, _ = remote_con.process.execute("cd /tmp/{0}; git checkout {1} ".format(repo, branch), dieOnNonZeroExitCode=False)
        if exit_code == 0:
            for source_path in repo_map[repo]:
                cmd = "cd /tmp/{0}; cp -R {1}/* {2}".format(repo, source_path, repo_map[repo][source_path])
                print cmd
                print remote_con.process.execute(cmd)
        else:
            print 'Specific branch: {0} does not exist, target dir will not be overwritten'.format(branch)


#############################
# FUNCTIONS USED BY JENKINS #
#############################

def install_ovs_packages(pub_ip, ql):
    remote_con = q.remote.system.connect(pub_ip, "root", UBUNTU_PASSWORD)
    remote_con.process.execute('echo "deb http://apt.openvstorage.org {0} main" > /etc/apt/sources.list.d/ovsaptrepo.list'.format(ql))

    remote_con.process.execute('apt-get update')
    remote_con.process.execute('apt-get install -y ntp')
    remote_con.process.execute('apt-get install -y --force-yes openvstorage-hc')


def install_autotests(node_ip, patch_branch=''):
    """
    Install the autotest package on node with IP
    :param node_ip: IP of node
    :param patch_branch: code branch to apply as patch on target
    :return: None
    """
    remote_con = q.remote.system.connect(node_ip, "root", UBUNTU_PASSWORD)
    remote_con.process.execute("apt-get update")
    remote_con.process.execute("apt-get install unzip openvstorage-test -y --force-yes")

    if patch_branch != '':
        repo_map = {'integrationtests': {'ci': '/opt/OpenvStorage/ci'}}
        _patch_code_with(patch_branch, repo_map, remote_con)


def run_autotests(node_ip, vpool_host_ip, vmware_info='', dc='', capture_screen=False, test_plan='', reboot_test=False,
                  vpool_name='alba', backend_name='alba', vpool_type='alba', test_project='Open vStorage Engineering',
                  testrail_server='', testrail_key='', output_folder='/var/tmp', qualitylevel=''):
    """
    vmware_info = "10.100.131.221,root,R00t3r123"
    """
    remote_con = q.remote.system.connect(node_ip, "root", UBUNTU_PASSWORD)

    vpool_storage_ip = remote_con.process.execute("ip a | awk '/inet/ && /privbr/ {print $2}'")[0]
    vpool_storage_ip = ipcalc.IP(vpool_storage_ip).dq

    os_name = "ubuntu_desktop14_kvm" if not vmware_info else "small_linux_esx"

    template_server = "http://sso-qpackages-loch.cloudfounders.com"
    if dc == 'bel-jen-axs.cloudfounders.com':
        template_server = "http://sso-qpackages-brussels.cloudfounders.com"

    if not test_plan:
        print 'Running all tests ...'
    else:
        print 'Running specific tests {0}'.format(test_plan)

    test_run = "autotests.run(tests='{0}', output_format='TESTRAIL', output_folder='{1}', project_name='{2}'," \
               "always_die={3}, qualitylevel='{4}', interactive={5})".format(test_plan, output_folder, test_project,
                                                                             False, qualitylevel, False)

    if vpool_type == "swift_s3":
        vpool_config = get_swift_vpool_config(vpool_host_ip=vpool_host_ip,
                                              vpool_storage_ip=vpool_storage_ip,
                                              vpool_name=vpool_name,
                                              vpool_type=vpool_type)
    elif vpool_type == "alba":
        vpool_config = get_alba_vpool_config(vpool_name=vpool_name,
                                             vpool_type=vpool_type)

    cinder_type = vpool_name

    cmd = create_autotest_cfg(os_name=os_name,
                              vmware_info=vmware_info,
                              template_server=template_server,
                              screen_capture=str(capture_screen),
                              vpool_config=vpool_config,
                              vpool_name=vpool_name,
                              backend_name=backend_name,
                              cinder_type=cinder_type,
                              grid_ip=node_ip,
                              test_project=test_project,
                              testrail_server=testrail_server,
                              testrail_key=testrail_key,
                              output_folder=output_folder,
                              qualitylevel=qualitylevel)

    _ = q.tools.installerci._run_command(cmd, node_ip, "root", UBUNTU_PASSWORD, buffered=True)

    cmd = '''source /etc/profile.d/ovs.sh
pkill Xvfb
pkill x11vnc
sleep 3
Xvfb :1 -screen 0 1280x1024x16 &
export DISPLAY=:1.0
x11vnc -display :1 -bg -nopw -noipv6 -no6 -listen localhost -xkb  -autoport 5950 -forever
ipython 2>&1 -c "from ci import autotests
{test_run}"'''.format(test_run=test_run)

    print cmd
    out = q.tools.installerci._run_command(cmd, node_ip, "root", UBUNTU_PASSWORD, buffered=True)
    out = out[0] + out[1]
    print out

    if reboot_test:
        print "Started reboot test"

        m = re.search("http://testrail.openvstorage.com/index.php\?/plans/view/([0-9]*)", out)
        assert m and m.groups(), "Couldn't find the testrail plan"
        existing_plan_id = m.groups()[0]

        cmd = """source /etc/profile.d/ovs.sh; \
python -c 'from ovs.dal.lists.storagerouterlist import StorageRouterList; \
print [sr.ip for sr in StorageRouterList.get_storagerouters() if sr.ip != "{0}"]'""".format(node_ip)
        out = remote_con.process.execute(cmd)[1]
        nodes = eval(out) + [node_ip]

        for rnode_ip in nodes:
            remote_con = q.remote.system.connect(rnode_ip, "root", UBUNTU_PASSWORD)
            remote_con.process.execute("shutdown -r now")
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
                     branch_name="stable/kilo", tag_name="", flat_interface="eth0"):
    """
    https://wiki.openstack.org/wiki/Releases
    Juno: 2014.2.4
    Kilo: 2015.1.2
    Liberty: due Oct 15, 2015
    :param node_ip: Node IP
    :param fixed_range: Fixed range
    :param fixed_range_size: Fixed range size
    :param floating_range: Floating range
    :param master_node_ip: Master node IP
    :param branch_name: Branch name
    :param tag_name: Tag name
    :param flat_interface: Flat interface
    """
    remote_con = q.remote.system.connect(node_ip, "root", UBUNTU_PASSWORD)
    print remote_con.process.execute("apt-get install git -y --force-yes")
    print remote_con.process.execute("apt-get install curl -y --force-yes")

    if not tag_name:
        if branch_name == 'stable/juno':
            tag_name = '2014.2.4'
        elif branch_name == 'stable/kilo':
            tag_name = '2015.1.2'

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

# https://bugs.launchpad.net/horizon/+bug/1532048
pip install django-compressor==1.6
echo checking django-compressor version
pip list | grep django-compressor

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
disable_service tempest
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
    print remote_con.process.execute(cmd)

    exports = "export OS_USERNAME=admin;export OS_PASSWORD=rooter;export OS_TENANT_NAME=admin;export OS_AUTH_URL=http://{0}:35357/v2.0;".format(master_node_ip)
    if master_node_ip:
        con_master = q.remote.system.connect(master_node_ip, "root", UBUNTU_PASSWORD)
        # Delete the lvmdriver cinder-type from your first node as the 2nd one will try to add the same and bail out
        print con_master.process.execute(exports + " cinder type-delete lvmdriver-1", dieOnNonZeroExitCode=False)
        con_master.close()

    cmd = """cd /home/devstack;su -c "cd /home/devstack;./stack.sh" stack"""

    if master_node_ip is not None:
        cmd = exports + cmd
    print remote_con.process.execute(cmd)

    print "Removing librabbitmq1 ..."
    cmd = "apt-get remove librabbitmq1 --purge -y"
    print remote_con.process.execute(cmd, dieOnNonZeroExitCode=False)

    # https://review.openstack.org/#/c/81489/1/lib/databases/mysql
    print "Increasing mysql max_connections to 10000 ..."
    cmd = """
sed -i 's/.*max_connections.*/max_connections=10000/' /etc/mysql/my.cnf
restart mysql
"""
    print remote_con.process.execute(cmd, dieOnNonZeroExitCode=False)


def copy_stack_user_ssh_keys(master_ip):
    """
    call if stable/icehouse and all nodes have been installed
    """
    remote_con = q.remote.system.connect(master_ip, "root", UBUNTU_PASSWORD)
    devstack_branch = remote_con.process.execute("cd /home/devstack/; git branch | awk '{print $2}'")[1].strip()
    if devstack_branch != "stable/icehouse":
        return
    cmd = 'source /etc/profile.d/ovs.sh;python -c "from ovs.dal.lists.storagerouterlist import StorageRouterList;print [sg.ip for sg in StorageRouterList.get_storagerouters()]"'
    out = remote_con.process.execute(cmd)[1]
    node_ips = eval(out)
    remote_con.close()
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
                            floating_range=None, branch_name="", tag_name="", flat_interface="eth0", branch=''):
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
                     hostname=hostname,
                     branch=branch)


def integrate_papertrail(ip):
    """
    Setup beaver config to log to papertrail
    :param ip: IP where papertrail needs to be configured
    """
    remote_con = q.remote.system.connect(ip, "root", UBUNTU_PASSWORD)
    print remote_con.process.execute('apt-get -y install python-pip')
    print remote_con.process.execute('pip install beaver --upgrade')

    sentinel_transport_cmd = """
mkdir -p /usr/local/lib/python2.7/dist-packages/beaver/transports

cat <<EOF > /usr/local/lib/python2.7/dist-packages/beaver/transports/sentinel_transport.py

# -*- coding: utf-8 -*-
import redis
import traceback
import time
import socket
import ast

from beaver.transports.base_transport import BaseTransport
from beaver.transports.exception import TransportException
from redis.sentinel import *


class SentinelTransport(BaseTransport):
    LIST_DATA_TYPE = 'list'
    CHANNEL_DATA_TYPE = 'channel'

    def __init__(self, beaver_config, logger=None):
        super(SentinelTransport, self).__init__(beaver_config, logger=logger)

        self._nodes = ast.literal_eval(beaver_config.get('sentinel_nodes'))
        self._namespace = beaver_config.get('redis_namespace')
        self._sentinel_master_name = beaver_config.get('sentinel_master_name')

        self._data_type = beaver_config.get('redis_data_type')
        if self._data_type not in [self.LIST_DATA_TYPE,
                                   self.CHANNEL_DATA_TYPE]:
            raise TransportException('Unknown Redis data type')

        self._sentinel = Sentinel(self._nodes, socket_timeout=0.1)
        self._get_master()

    def _get_master(self):
        if self._check_connection():
            self._master = self._sentinel.master_for(self._sentinel_master_name, socket_timeout=0.1)

    def _check_connection(self):
        try:
            if self._is_reachable():
                master_info = self._sentinel.discover_master(self._sentinel_master_name)
                self._logger.info('Master found: ' + str(master_info))
                return True
        except MasterNotFoundError:
            self._logger.warn('Master not found')
        except Exception, ex:
            self._logger.warn('Error in _check_connection(): %s' %traceback.print_exc())

        return False

    def _is_reachable(self):
        for node in self._nodes:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(node)
            sock.close()
            return (result == 0)

        self._logger.warn('Cannot connect to one of the given sentinel servers')
        return False

    def reconnect(self):
        self._check_connections()

    def invalidate(self):
        super(SentinelTransport, self).invalidate()
        self._master.connection_pool.disconnect()
        return False

    def callback(self, filename, lines, **kwargs):
        self._logger.debug('Redis transport called')

        timestamp = self.get_timestamp(**kwargs)
        if kwargs.get('timestamp', False):
            del kwargs['timestamp']

        namespaces = self._beaver_config.get_field('redis_namespace', filename)

        if not namespaces:
            namespaces = self._namespace
            namespaces = namespaces.split(",")

        self._logger.debug('Got namespaces: '.join(namespaces))

        data_type = self._data_type
        self._logger.debug('Got data type: ' + data_type)

        pipeline = self._master.pipeline(transaction=False)

        callback_map = {
            self.LIST_DATA_TYPE: pipeline.rpush,
            self.CHANNEL_DATA_TYPE: pipeline.publish,
        }
        callback_method = callback_map[data_type]

        for line in lines:
            for namespace in namespaces:
                callback_method(
                    namespace.strip(),
                    self.format(filename, line, timestamp, **kwargs)
                )

        try:
            pipeline.execute()
        except redis.exceptions.RedisError, exception:
            self._logger.warn('Cannot push lines to redis server: ' + server['url'])
            raise TransportException(exception)
EOF
"""
    print remote_con.process.execute(sentinel_transport_cmd, dieOnNonZeroExitCode=False)

    config_cmd = """
mkdir -p /etc/beaver

cat <<EOF > /etc/beaver/beaver.conf
[beaver]
transport: sentinel
sentinel_nodes: [('172.19.10.15',26379),('172.19.10.16',26379),('172.19.10.17',26379)]
sentinel_master_name: master
redis_namespace: logs
logstash_version: 1

[/var/log/rabbitmq/*.log]
multiline_regex_before = ^[^=].*
ignore_empty: 1
type: rabbitmq
tags: rabbitmq

[/var/log/ovs/*.log]
type: ovs
tags: ovs

[/var/log/upstart/*.log]
type: upstart
tags: upstart

[/var/log/kern.log]
type: kernel
tags: kernel

[/var/log/syslog]
type: syslog
tags: syslog

[/var/log/auth.log]
type: auth
tags: auth

[/var/log/libvirt/*.log]
type: libvirt
tags: libvirt

[/var/log/nginx/error.log]
type: nginx
tags: nginx
EOF
"""
    print remote_con.process.execute(config_cmd, dieOnNonZeroExitCode=False)

    upstart_cmd = """cat <<EOF > /etc/init/ovs-beaver.conf
description "Beaver upstart for papertrail"

start on (local-filesystems and started networking)
stop on runlevel [016]

kill timeout 60
respawn
respawn limit 10 5
console log

exec /usr/local/bin/beaver -c /etc/beaver/beaver.conf -P /var/tmp
EOF

stop ovs-beaver
start ovs-beaver
"""
    print remote_con.process.execute(upstart_cmd, dieOnNonZeroExitCode=False)


if __name__ == '__main__':
    options, remainder = getopt.getopt(sys.argv[1:], 'e:w:p:n:g:k:d:q:c:l:h:E:H:M:S:s:b:N')
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
        if opt == '-b':
            patchbranch = arg
        if opt == '-N':
            install_ovsvsa = False
    assert q.system.net.pingMachine(hypervisor_ip), "Invalid ip given or unreachable"
    hypervisor_password = hypervisor_password or "R00t3r123"
    hypervisor_login = "root"
    qualitylevel = qualitylevel or "test"

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
                     hostname=hostname,
                     branch=patchbranch)
    # TODO: remove this if when OVS-3984 is resolved
    if hypervisor_type == "KVM":
        remote_con = q.remote.system.connect(public_ip, "root", UBUNTU_PASSWORD)
        exitcode, output = remote_con.process.execute("grep -c 'ovs' /etc/passwd")
        if exitcode == 0 and output[0] == '1':
            # user ovs exists
            remote_con.process.execute("usermod -a -G ovs libvirt-qemu")
