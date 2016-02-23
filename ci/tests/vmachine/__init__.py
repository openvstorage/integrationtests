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

from ci.tests.general.general import General
from ci.tests.general.general_alba import GeneralAlba
from ci.tests.general.general_backend import GeneralBackend
from ci.tests.general.general_mgmtcenter import GeneralManagementCenter
from ci.tests.general.general_vmachine import GeneralVMachine
from ci.tests.general.general_vpool import GeneralVPool


def setup():
    """
    Setup for Virtual Machine package, will be executed when any test in this package is being executed
    Make necessary changes before being able to run the tests
    :return: None
    """
    autotest_config = General.get_config()
    backend_name = autotest_config.get('backend', 'name')
    assert backend_name, "Please fill out a valid backend name in autotest.cfg file"

    # Download the template
    cmd = '[ -d {0} ] && echo "Dir exists" || echo "Dir does not exists"'.format(GeneralVMachine.template_target_folder)
    out, err = General.execute_command(cmd)
    if err:
        GeneralVMachine.logger.error("Error while executing command {1}: {0}".format(err, cmd))
    if 'not' not in out:
        General.execute_command('rm -rf {0}'.format(GeneralVMachine.template_target_folder))
        General.execute_command('mkdir {0}'.format(GeneralVMachine.template_target_folder))
    grid_ip = General.get_config().get('main', 'grid_ip')

    if grid_ip.split('.')[0] == '172' and grid_ip.split('.')[1] == '20':
        server_location = 'http://172.20.3.8/templates/openvstorage'
    else:
        server_location = 'http://sso-qpackages-loch.cloudfounders.com/templates/openvstorage'

    GeneralVMachine.logger.info("Getting template from {0}".format(server_location))
    out, err = General.execute_command('wget -P {0} {1}{2}{3}'.format(GeneralVMachine.template_target_folder, server_location, '/fio_debian/', GeneralVMachine.template_image))
    if err:
        GeneralVMachine.logger.error("Error while downloading template: {0}".format(err))
    out, err = General.execute_command('chown root {0}{1}'.format(GeneralVMachine.template_target_folder, GeneralVMachine.template_image))
    if err:
        GeneralVMachine.logger.error("Error while changing user owner to root for template: {0}".format(err))

    GeneralAlba.prepare_alba_backend()
    GeneralManagementCenter.create_generic_mgmt_center()
    GeneralVPool.add_vpool()


def teardown():
    """
    Teardown for VirtualMachine package, will be executed when all started tests in this package have ended
    Removal actions of possible things left over after the test-run
    :return: None
    """
    vpool_name = General.get_config().get('vpool', 'name')
    vpool = GeneralVPool.get_vpool_by_name(vpool_name)
    assert vpool is not None, "No vpool found where one was expected"
    GeneralVMachine.logger.info("Cleaning vpool")
    GeneralVPool.remove_vpool(vpool)

    autotest_config = General.get_config()
    be = GeneralBackend.get_by_name(autotest_config.get('backend', 'name'))
    if be:
        GeneralAlba.unclaim_disks_and_remove_alba_backend(alba_backend=be.alba_backend)

    GeneralVMachine.logger.info("Cleaning management center")

    for mgmt_center in GeneralManagementCenter.get_mgmt_centers():
        GeneralManagementCenter.remove_mgmt_center(mgmt_center)
