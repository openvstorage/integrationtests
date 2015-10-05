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

import os
import time
import ipcalc
import signal
import random
import logging

from nose.tools import with_setup
from nose.plugins.skip import SkipTest

from ci.tests.general import general
from ci.tests.general import general_hypervisor
from ci.tests.gui.vpool import Vpool
from ci.tests.gui.browser_ovs import BrowserOvs
from ci.tests.gui.vmachine import Vmachine
from ci import autotests

from ovs.dal.lists.vpoollist import VPoolList
from ovs.dal.lists.vmachinelist import VMachineList

from selenium.webdriver.remote.remote_connection import LOGGER

LOGGER.setLevel(logging.WARNING)

tests_to_run = general.get_tests_to_run(autotests.getTestLevel())
machine_name = "AT_" + __name__.split(".")[-1]
vpool_name = general.test_config.get("vpool", "vpool_name")
vpool_name = 'gui-' + vpool_name
browser_object = None


def setup():
    global dnsmasq_pid, screen_cap_pid, flv_cap_loc

    print "Setup called " + __name__

    # make sure we start with clean env
    general.cleanup()

    # setup dhcp for vms
    virbr_ip = ipcalc.IP(general.get_virbr_ip())
    dhcp_start = ipcalc.IP(virbr_ip.ip + 1).dq
    dhcp_end = ipcalc.IP(virbr_ip.ip + 11).dq
    cmd = ["/usr/sbin/dnsmasq", "--listen-address=0.0.0.0", "--dhcp-range={0},{1},12h".format(dhcp_start, dhcp_end),
           "--interface=virbr0", "--no-daemon"]
    dnsmasq_pid = general.execute_command(cmd, wait=False, shell=False)

    screen_cap_pid = None
    if general.test_config.get("main", "screen_capture") == "True":
        flv_cap_loc = "/root/screen_capture_{0}.flv".format(str(int(time.time())))
        cmd = ["flvrec.py", "-o", flv_cap_loc, "localhost:50"]
        screen_cap_pid = general.execute_command(cmd, wait=False, shell=False)


def teardown():
    global dnsmasq_pid, screen_cap_pid, flv_cap_loc
    try:
        os.kill(dnsmasq_pid, signal.SIGKILL)
    except:
        pass

    if screen_cap_pid is not None:
        try:
            os.kill(screen_cap_pid, signal.SIGKILL)
            general.execute_command(["avconv", "-i", flv_cap_loc, "-b", "2048k", flv_cap_loc.replace(".flv", ".avi")],
                                    shell=False)
        except:
            pass

    # revert the environment to it's clean state
    general.cleanup()


def close_browser():
    general.cleanup()
    global browser_object
    if browser_object:
        browser_object.teardown()


@with_setup(None, close_browser)
def ovs_login_test():
    """
    """

    general.check_prereqs(testcase_number=1, tests_to_run=tests_to_run)

    global browser_object

    browser_object = bt = BrowserOvs()
    bt.take_screenshot("start_ovs_login_test")
    bt.login()
    bt.take_screenshot("end_ovs_login_test")


@with_setup(None, close_browser)
def ovs_wrong_password_test():
    """
    """

    general.check_prereqs(testcase_number=2, tests_to_run=tests_to_run)

    global browser_object

    browser_object = bt = BrowserOvs()
    bt.take_screenshot("start_ovs_wrong_password_test")
    bt.password = "wrong_password"
    bt.login(wait=False)
    time.sleep(5)
    bt.check_invalid_credentials_alert()
    bt.take_screenshot("end_ovs_wrong_password_test")
    assert "dashboard" not in bt.browser.title, "Failed login should not go to dashboard"


@with_setup(None, close_browser)
def ovs_wrong_username_test():
    """
    """

    general.check_prereqs(testcase_number=3, tests_to_run=tests_to_run)

    global browser_object

    browser_object = bt = BrowserOvs()
    bt.take_screenshot("start_ovs_wrong_username_test")
    bt.username = "wrong_username"
    bt.login(wait=False)
    time.sleep(5)
    bt.check_invalid_credentials_alert()
    bt.take_screenshot("end_ovs_wrong_username_test")
    assert "dashboard" not in bt.browser.title, "Failed login should not go to dashboard"


@with_setup(None, close_browser)
def vpool_add_test():
    """
    %s
    """ % general.get_function_name()

    general.check_prereqs(testcase_number=4, tests_to_run=tests_to_run)

    global browser_object

    browser_object = bt = Vpool(vpool_name=vpool_name)
    bt.take_screenshot("start_vpool_add_test")
    vpool = VPoolList.get_vpool_by_name(bt.vpool_name)
    if vpool:
        general.remove_vpool(bt)

    bt.login()
    general.add_vpool(bt)

    bt.browse_to(bt.get_url() + '#full/vpools', '')
    time.sleep(5)
    bt.wait_for_text(bt.vpool_name)
    bt.take_screenshot("end_vpool_add_test")


@with_setup(None, close_browser)
def vpool_remove_test():
    """
    %s
    """ % general.get_function_name()

    general.check_prereqs(testcase_number=5, tests_to_run=tests_to_run)

    global browser_object

    browser_object = bt = Vpool(vpool_name=vpool_name)
    bt.take_screenshot("start_vpool_remove_test")
    vpool = VPoolList.get_vpool_by_name(bt.vpool_name)

    bt.login()
    if not vpool:
        general.add_vpool(bt)

    time.sleep(30)

    general.remove_vpool(bt)

    bt.browse_to(bt.get_url() + '#full/vpools', '')
    time.sleep(5)
    bt.wait_for_text_to_vanish(bt.vpool_name)
    bt.take_screenshot("end_vpool_remove_test")


@with_setup(None, close_browser)
def validate_vpool_cleanup_test():
    """
    %s
    """ % general.get_function_name()

    general.check_prereqs(testcase_number=6, tests_to_run=tests_to_run)

    global browser_object
    browser_object = bt = Vpool(vpool_name=vpool_name)
    bt.take_screenshot("start_validate_vpool_cleanup_test")
    bt.login()

    vpool = VPoolList.get_vpool_by_name(bt.vpool_name)
    if vpool:
        general.remove_vpool(bt)

    for _idx in range(2):
        general.add_vpool(bt)
        vpool = VPoolList.get_vpool_by_name(bt.vpool_name)
        # hold a copy of these for later
        storagedrivers = list(vpool.storagedrivers)

        general.check_voldrv_services(vpool_name, storagedrivers)
        general.check_mountpoints(storagedrivers)

        # create volume
        local_vsa = general.get_local_vsa()
        sd = [sd for sd in vpool.storagedrivers if sd.storagerouter.ip == local_vsa.ip][0]
        file_name = os.path.join(sd.mountpoint, "validate_vpool" + str(time.time()).replace(".", "") + ".raw")

        cmd = "truncate {0} --size 10000000".format(file_name)
        out, error = general.execute_command(cmd)
        assert error == '', "Exception occurred while running {0}:\n{1}\n{2}".format(cmd, out, error)

        time.sleep(10)
        general.execute_command("rm {0}".format(file_name))

        general.remove_vpool(bt)

        time.sleep(5)
        general.check_voldrv_services(vpool_name, storagedrivers, running=False)
        general.check_mountpoints(storagedrivers, is_present=False)
    bt.take_screenshot("end_validate_vpool_cleanup_test")


@with_setup(None, close_browser)
def set_as_template_test():
    """
    %s
    Create a vm and check if it gets registered
    """ % general.get_function_name()

    general.check_prereqs(testcase_number=7, tests_to_run=tests_to_run)

    global browser_object
    browser_object = bt = Vmachine()
    bt.login()
    bt.take_screenshot("start_set_as_template_test")

    name = machine_name + "_set_as_template"

    vpool = general.setup_vpool(vpool_name)
    hpv = general_hypervisor.Hypervisor.get(vpool_name)
    hpv.create_vm(name, small=False)

    logging.log(1, 'Check if vmachine with name: {0} is present'.format(name))
    bt.check_machine_is_present(name, 100)

    vm = VMachineList.get_vmachine_by_name(name)[0]
    for vdisk in vm.vdisks:
        logging.log(1, 'Check if vdisk {0} is present'.format(vdisk.name))
        bt.check_machine_disk_is_present(vdisk.name)

    logging.log(1, 'Check if running vmachine {0} cannot be set as template'.format(name))
    bt.set_as_template(name, allowed=False)

    logging.log(1, 'Shutting down vmachine {0}'.format(name))
    hpv.poweroff(name)

    logging.log(1, 'Check if running vmachine {0} can be set as template'.format(name))
    bt.set_as_template(name)
    bt.check_machine_is_not_present(name)

    bt.take_screenshot("end_set_as_template_test")


@with_setup(None, close_browser)
def create_from_template_test():
    """
    %s
    * create vm from template
    """ % general.get_function_name()

    general.check_prereqs(testcase_number=8, tests_to_run=tests_to_run)

    global browser_object
    browser_object = bt = Vmachine()
    bt.login()
    bt.take_screenshot("start_create_from_template_test")

    name = machine_name + "_create" + str(random.randrange(0, 9999999))

    vpool = general.setup_vpool(vpool_name)
    hpv = general_hypervisor.Hypervisor.get(vpool_name)
    hpv.create_vm(machine_name, small=False)

    logging.log(1, 'Check if vmachine with name: {0} is present'.format(machine_name))
    bt.check_machine_is_present(machine_name, 100)
    hpv.poweroff(machine_name)
    bt.set_as_template(machine_name, allowed=True)

    template = Vmachine.get_template(machine_name, vpool_name)

    browser_object = bt = Vmachine()
    bt.login()

    bt.create_from_template(template.name, name)
    bt.check_machine_is_present(name)
    hpv.delete(name)

    bt.take_screenshot("end_create_from_template_test")


@with_setup(None, close_browser)
def start_stop_vm_test():
    """
    %s
    """ % general.get_function_name()

    general.check_prereqs(testcase_number=9, tests_to_run=tests_to_run)

    name = machine_name + "_start" + str(random.randrange(0, 9999999))
    template_name = machine_name + '_template'

    global browser_object

    browser_object = bt = Vmachine()
    bt.login()
    bt.take_screenshot("start_start_stop_vm_test")

    vpool = general.setup_vpool(vpool_name)
    hpv = general_hypervisor.Hypervisor.get(vpool_name)

    template = Vmachine.get_template(template_name, vpool_name)

    bt.create_from_template(template.name, name)
    bt.check_machine_is_present(name)

    hpv.start(name)

    if general_hypervisor.get_hypervisor_type() == "KVM":
        vm_ip = hpv.wait_for_vm_pingable(name)

        prev_stats = bt.check_vm_stats_overview_update(name)
        hpv.write_test_data(vm_name=name,
                            filename="test",
                            zero_filled=True,
                            zero_filled_count=500 * 1024)
        _ = bt.check_vm_stats_overview_update(name, prev_stats=prev_stats)

        prev_stats = bt.check_vm_stats_detail_update(name)
        hpv.write_test_data(vm_name=name,
                            filename="test2",
                            zero_filled=True,
                            zero_filled_count=500 * 1024)

        _ = bt.check_vm_stats_detail_update(name, prev_stats=prev_stats)

    hpv.shutdown(name)
    if general_hypervisor.get_hypervisor_type() == "KVM":
        hpv.wait_for_vm_pingable(name, pingable=False, vm_ip=vm_ip)

    hpv.delete(name)
    bt.take_screenshot("end_start_stop_vm_test")


@with_setup(None, close_browser)
def delete_clone_test():
    """
    %s
    """ % general.get_function_name()

    general.check_prereqs(testcase_number=10, tests_to_run=tests_to_run)

    global browser_object
    browser_object = bt = Vmachine()
    bt.login()
    bt.take_screenshot("start_delete_clone_test")

    vpool = general.setup_vpool(vpool_name)

    name = machine_name + "_delete" + str(random.randrange(0, 9999999))
    template = Vmachine.get_template(machine_name, vpool_name)

    bt.create_from_template(template.name, name)
    bt.check_machine_is_present(name)

    bt.browse_to(bt.get_url() + '#full/vmachines', 'vmachines')
    bt.wait_for_text(name)

    hpv = general_hypervisor.Hypervisor.get(vpool_name)

    hpv.delete(name)

    bt.wait_for_text_to_vanish(name, timeout=10)

    assert not VMachineList.get_vmachine_by_name(name), "Vmachine was not deleted from model after hypervisor deletion"
    bt.take_screenshot("end_delete_clone_test")


@with_setup(None, close_browser)
def machine_snapshot_rollback_test():
    """
    %s
    """ % general.get_function_name()

    general.check_prereqs(testcase_number=11, tests_to_run=tests_to_run)

    global browser_object
    browser_object = bt = Vmachine()
    bt.login()
    bt.take_screenshot("start_machine_snapshot_rollback_test")

    name = machine_name + "_sn_roll" + str(random.randrange(0, 9999999))
    vpool = general.setup_vpool(vpool_name)
    template = Vmachine.get_template(machine_name, vpool_name)

    hpv = general_hypervisor.Hypervisor.get(vpool_name)

    bt.create_from_template(template.name, name)
    bt.check_machine_is_present(name)

    hpv.start(name)
    if general_hypervisor.get_hypervisor_type() == "KVM":
        hpv.wait_for_vm_pingable(name)

    vm = VMachineList.get_vmachine_by_name(name)[0]

    # First snapshot
    filename1 = "testA"
    snapshot_name1 = name + "ss" + filename1

    if general_hypervisor.get_hypervisor_type() == "KVM":
        hpv.write_test_data(name, filename1)
        hpv.check_test_data(name, filename1)

    snapshots_before = vm.snapshots
    bt.snapshot(name, snapshot_name1)
    bt.check_snapshot_present(name, snapshot_name1)
    Vmachine.check_snapshot_model(snapshots_before, snapshot_name1, vm)

    # Second snapshot
    filename2 = "testB"
    snapshot_name2 = name + "ss" + filename2

    if general_hypervisor.get_hypervisor_type() == "KVM":
        hpv.write_test_data(name, filename2)
        hpv.check_test_data(name, filename2)

    snapshots_before = vm.snapshots
    bt.snapshot(name, snapshot_name2)
    bt.check_snapshot_present(name, snapshot_name2)
    Vmachine.check_snapshot_model(snapshots_before, snapshot_name2, vm)

    if general_hypervisor.get_hypervisor_type() == "KVM":
        hpv.delete_test_data(name, filename1)

    bt.rollback(name, snapshot_name1, allowed=False)

    hpv.poweroff(name)
    time.sleep(3)

    bt.rollback(name, snapshot_name1)

    hpv.start(name)
    if general_hypervisor.get_hypervisor_type() == "KVM":
        hpv.check_test_data(name, filename1)
        hpv.check_test_data(name, filename2, not_present=True)

    bt.take_screenshot("end_machine_snapshot_rollback_test")


@with_setup(None, close_browser)
def try_to_delete_template_with_clones_test():
    """
    %s
    """ % general.get_function_name()

    general.check_prereqs(testcase_number=12, tests_to_run=tests_to_run)

    global browser_object
    browser_object = bt = Vmachine()
    bt.login()
    bt.take_screenshot("start_try_to_delete_template_with_clones_test")

    vpool = VPoolList.get_vpool_by_name(vpool_name)
    if vpool:
        general.cleanup()

    name = machine_name + "_tmpl_cln" + str(random.randrange(0, 9999999))

    vpool = general.setup_vpool(vpool_name)
    template = Vmachine.get_template(machine_name, vpool_name)
    hpv = general_hypervisor.Hypervisor.get(vpool_name)

    bt.create_from_template(template.name, name)
    bt.check_machine_is_present(name)

    bt.delete_template(template.name, should_fail=True)
    assert VMachineList.get_vmachine_by_name(template.name)

    # clone should still work

    vm_ip = None
    hpv.start(name)
    if general_hypervisor.get_hypervisor_type() == "KVM":
        vm_ip = hpv.wait_for_vm_pingable(name)

    hpv.shutdown(name)
    if general_hypervisor.get_hypervisor_type() == "KVM" and vm_ip:
        hpv.wait_for_vm_pingable(name, pingable=False, vm_ip=vm_ip)

    bt.take_screenshot("end_try_to_delete_template_with_clones_test")


@with_setup(None, close_browser)
def delete_template_test():
    """
    %s
    """ % general.get_function_name()

    vpool = VPoolList.get_vpool_by_name(vpool_name)
    if vpool:
        general.cleanup()

    general.check_prereqs(testcase_number=13, tests_to_run=tests_to_run)

    global browser_object
    browser_object = bt = Vmachine()
    bt.login()
    bt.take_screenshot("start_delete_template_test")

    vpool = general.setup_vpool(vpool_name)
    hpv = general_hypervisor.Hypervisor.get(vpool_name)
    template = Vmachine.get_template(machine_name, vpool_name)

    # first delete all clones:
    hpv.delete_clones(template.name)

    bt.delete_template(template.name)
    bt.take_screenshot("end_delete_template_test")


@with_setup(None, close_browser)
def multiple_vpools_test():
    """
    %s
    """ % general.get_function_name()

    general.check_prereqs(testcase_number=14, tests_to_run=tests_to_run)

    global browser_object

    vpool = VPoolList.get_vpool_by_name(vpool_name)
    if vpool:
        general.cleanup()

    required_backends = ["alba", "local"]

    vpool_params = ['vpool_name', 'vpool_type_name', 'vpool_host', 'vpool_port', 'vpool_access_key', 'vpool_secret_key',
                    'vpool_temp_mp', 'vpool_md_mp', 'vpool_readcaches_mp', 'vpool_writecaches_mp', 'vpool_foc_mp',
                    'vpool_bfs_mp', 'vpool_vrouter_port', 'vpool_storage_ip']

    vpool_configs = {}

    for section_name in ['vpool', 'vpool2', 'vpool3', 'vpool4']:
        if general.test_config.has_section(section_name):
            vpool_type = general.test_config.get(section_name, "vpool_type")
            if vpool_type in required_backends:
                vpool_configs[vpool_type] = dict(
                    [(vpool_param, general.test_config.get(section_name, vpool_param)) for vpool_param in vpool_params])

    if len(vpool_configs) < len(required_backends):
        raise SkipTest()

    logging.log(1, 'vpool configs to use: {0}'.format(vpool_configs))

    browser_object = bt = Vpool(vpool_name=vpool_name)
    bt.login()
    bt.take_screenshot("start_multiple_vpools_test")

    for vpool_config in vpool_configs.itervalues():

        logging.log(1, 'vpool_config: {0}'.format(vpool_config))
        browser_object = bt = Vpool(**vpool_config)
        bt.login()
        logging.log(3, 'vpool vpool_name: {0}'.format(bt.vpool_name))
        vpool = VPoolList.get_vpool_by_name(bt.vpool_name)
        if vpool:
            general.remove_vpool(bt)

        general.add_vpool(bt)

        bt.browse_to(bt.get_url() + '#full/vpools', '')
        time.sleep(10)
        bt.wait_for_text(bt.vpool_name)

        vpool = VPoolList.get_vpool_by_name(bt.vpool_name)

        storagedrivers = list(vpool.storagedrivers)

        general.check_voldrv_services(bt.vpool_name, storagedrivers)
        general.check_mountpoints(storagedrivers)

        hpv = general_hypervisor.Hypervisor.get(vpool.name)
        vpool_config['vm_name'] = machine_name + '_' + vpool.name
        hpv.create_vm(vpool_config['vm_name'], small=True)

        bt.teardown()

    for vpool_config in vpool_configs.itervalues():
        vm_name = vpool_config['vm_name']
        del vpool_config['vm_name']

        hpv = general_hypervisor.Hypervisor.get(vpool_config['vpool_name'])
        hpv.poweroff(vm_name)
        hpv.delete(vm_name)

        vpool = VPoolList.get_vpool_by_name(vpool_config['vpool_name'])
        storagedrivers = list(vpool.storagedrivers)

        bt = Vpool(**vpool_config)
        bt.login()
        general.remove_vpool(bt)

        general.check_voldrv_services(vpool_config['vpool_name'], storagedrivers, running=False)
        general.check_mountpoints(storagedrivers, is_present=False)

        bt.take_screenshot("end_multiple_vpools_test")
        bt.teardown()
