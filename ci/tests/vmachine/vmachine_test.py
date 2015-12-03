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
from ci.tests.general import general
from ci import autotests


testsToRun = general.get_tests_to_run(autotests.get_test_level())

VPOOL_NAME = test_config.get('vpool', 'vpool_name')

template_servers = ['http://sso-qpackages-loch.cloudfounders.com/templates/openvstorage', 'http://172.20.3.8/templates/openvstorage']
template_folder = '/fio_debian/'
template_image = 'debian.qcow2'
templateDir = '/var/tmp/templates/'

NUMBER_OF_DISKS = 10
GRID_IP = test_config.get('main', 'grid_ip')


def download_template(server_location):
    general.execute_command('wget -P {0} {1}{2}{3}'.format(templateDir, template_servers[server_location], template_folder, template_image))
    general.execute_command('chown root {0}{1}'.format(templateDir, template_image))


def check_loch_axs():
    if GRID_IP.split('.')[0] == '172' and GRID_IP.split('.')[1] == '20':
        return 1
    else:
        return 0


def check_template_exists():
    out, err = general.execute_command('[ -d {0} ] && echo "Dir exists" || echo "Dir does not exists"'.format(templateDir))
    if 'not' not in out:
        general.execute_command('rm -rf {0}'.format(templateDir))
        general.execute_command('mkdir {0}'.format(templateDir))
    server_location = check_loch_axs()
    download_template(server_location)


def setup():
    check_template_exists()
    vpool_test.setup()
    vpool_test.add_vpool()


def teardown():
    general.execute_command("rm -rf /mnt/{0}".format(VPOOL_NAME))
    general.api_remove_vpool(VPOOL_NAME)
    vpool_test.teardown()


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
        general.execute_command('qemu-img convert -O raw {0}{1} /mnt/{2}/disk-{3}.raw'.format(templateDir, template_image, vpool.name, disk_number))
