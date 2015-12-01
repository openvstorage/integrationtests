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
import re
import sys
import time
import json
import getopt
import ipcalc
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


def configure_alba(hypervisor_ip, public_ip, alba_deploy_type, license, backend_name):
    if alba_deploy_type in ['converged']:
        alba_host_ip = hypervisor_ip
    else:
        alba_host_ip = public_ip

    q.clients.ssh.waitForConnection(alba_host_ip, "root", UBUNTU_PASSWORD, times=120)
    con = q.remote.system.connect(alba_host_ip, "root", UBUNTU_PASSWORD)

    python_cmd = """
# add license
from ovs.lib.license import LicenseController
LicenseController.apply('%(license)s')
""" % {'license': license}

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


def install_autotests(node_ip):
    con = q.remote.system.connect(node_ip, "root", UBUNTU_PASSWORD)
    con.process.execute("apt-get update")
    con.process.execute("apt-get install unzip openvstorage-test -y --force-yes")


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


def run_autotests(node_ip, vpool_host_ip, vmware_info='', dc='', capture_screen=False, test_plan='', reboot_test=False,
                  vpool_name='alba', backend_name='alba', vpool_type='alba', test_project='Open vStorage Engineering',
                  testrail_server='', testrail_key='', output_folder='/var/tmp', qualitylevel=''):
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


def deploy_ovsvsa_vmware(public_ip, hypervisor_ip, hypervisor_password, dns, public_network, gateway, public_netmask,
                         hostname, extra_packages=None, storage_ip_last_octet=None):

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


def handle_ovs_setup(public_ip, qualitylevel, cluster_name, hypervisor_type, hypervisor_ip, hypervisor_password,
                     hostname):

    con = q.remote.system.connect(public_ip, "root", UBUNTU_PASSWORD)
    con.process.execute('echo "deb http://apt.openvstorage.org {0} main" > /etc/apt/sources.list.d/ovsaptrepo.list'.format(qualitylevel))

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
