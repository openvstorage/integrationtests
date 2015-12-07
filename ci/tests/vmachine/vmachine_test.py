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

from ci.tests.general.general import test_config
from ci.tests.general.connection import Connection
from ovs.dal.lists.vpoollist import VPoolList
from ci.tests.vpool import vpool_test
from ci.tests.mgmtcenter import mgmt_center_test
from ci.tests.general import general
from ci import autotests


testsToRun = general.get_tests_to_run(autotests.get_test_level())

VPOOL_NAME = test_config.get('vpool', 'vpool_name')
TEMPLATE_SERVERS = ['http://sso-qpackages-loch.cloudfounders.com/templates/openvstorage', 'http://172.20.3.8/templates/openvstorage']


template_source_folder = '/fio_debian/'
template_image = 'debian.qcow2'
template_target_folder = '/var/tmp/templates/'

NUMBER_OF_DISKS = 10
GRID_IP = test_config.get('main', 'grid_ip')


def download_template(server_location):
    general.execute_command('wget -P {0} {1}{2}{3}'.format(template_target_folder, server_location, template_source_folder, template_image))
    general.execute_command('chown root {0}{1}'.format(template_target_folder, template_image))


def get_template_location_by_ip(ip):
    if ip.split('.')[0] == '172' and ip.split('.')[1] == '20':
        return TEMPLATE_SERVERS[1]
    else:
        return TEMPLATE_SERVERS[0]


def check_template_exists():
    out, err = general.execute_command('[ -d {0} ] && echo "Dir exists" || echo "Dir does not exists"'.format(template_target_folder))
    if 'not' not in out:
        general.execute_command('rm -rf {0}'.format(template_target_folder))
        general.execute_command('mkdir {0}'.format(template_target_folder))
    download_template(get_template_location_by_ip(GRID_IP))


def setup():
    check_template_exists()
    vpool_test.setup()
    mgmt_center_test.setup()
    vpool_test.add_vpool()


def teardown():
    #vpool = VPoolList.get_vpool_by_name(VPOOL_NAME)
    #if vpool:
    #    general.execute_command("rm -rf /mnt/{0}".format(VPOOL_NAME))
    #    general.api_remove_vpool(VPOOL_NAME)
    #vpool_test.teardown()
    # @todo change mgmgt teardown to delete recently added hmc
    #mgmt_center_test.teardown()
    pass


def vms_with_fio_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=1,
                          tests_to_run=testsToRun)

    api = Connection.get_connection()
    # @TODO change this to api connection call
    vpool = VPoolList.get_vpool_by_name(VPOOL_NAME)
    for disk_number in range(NUMBER_OF_DISKS):
        general.execute_command('qemu-img convert -O raw {0}{1} /mnt/{2}/disk-{3}.raw'.format(template_target_folder, template_image, vpool.name, disk_number))

    assert len(vpool.vdisks) == NUMBER_OF_DISKS, "Only {0} out of {1} VDisks have been created".format(len(vpool.vdisks), NUMBER_OF_DISKS)

    for vm_number in range(NUMBER_OF_DISKS):
        general.execute_command('virt-install --connect qemu:///system -n machine{0} -r 512 --disk /mnt/{1}/disk-{0}.raw,device=disk --noautoconsole --graphics vnc,listen=0.0.0.0 --vcpus=1 --network network=default,mac=RANDOM,model=e1000 --import'.format(vm_number, vpool.name))

    assert len(vpool.vmachines) == NUMBER_OF_DISKS, "Only {0} out of {1} VMachines have been created".format(len(vpool.vmachines), NUMBER_OF_DISKS)

    #for vm_number in range(NUMBER_OF_DISKS):
    #    general.execute_command('virsh destroy machine{0}'.format(vm_number))
    #    general.execute_command('virsh undefine machine{0}'.format(vm_number))
