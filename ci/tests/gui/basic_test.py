# Copyright 2014 CloudFounders NV
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
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


from nose.tools                 import with_setup

from ci.tests.general           import general
from ci.tests.general           import general_hypervisor
from ci.tests.gui.vpool         import Vpool
from ci.tests.gui.browser_ovs   import BrowserOvs
from ci.tests.gui.vmachine      import Vmachine
from ci                         import autotests

from ovs.dal.lists.vpoollist         import VPoolList
from ovs.dal.lists.vmachinelist      import VMachineList

from selenium.webdriver.remote.remote_connection import LOGGER

LOGGER.setLevel(logging.WARNING)

testsToRun     = general.getTestsToRun(autotests.getTestLevel())
machinename    = "AT_" + __name__.split(".")[-1]
vpool_name     = autotests.getConfigIni().get("vpool", "vpool_name")
browser_object = None


def setup():
    global dnsmasq_pid

    print "setup called " + __name__

    #make sure we start with clean env
    general.cleanup()

    virbr_ip    = ipcalc.IP(general.get_virbr_ip())
    dhcp_start  = ipcalc.IP(virbr_ip.ip + 1).dq
    dhcp_end    = ipcalc.IP(virbr_ip.ip + 11).dq
    cmd = ["/usr/sbin/dnsmasq", "--listen-address=0.0.0.0", "--dhcp-range={0},{1},12h".format(dhcp_start, dhcp_end), "--interface=virbr0", "--no-daemon"]
    dnsmasq_pid = general.execute_command(cmd, wait = False, shell = False)


def teardown():
    global dnsmasq_pid
    try:
        os.kill(dnsmasq_pid, signal.SIGKILL)
    except:
        pass


def close_browser():
    global browser_object
    if browser_object:
        browser_object.teardown()


@with_setup(None, close_browser)
def ovs_login_test():
    """
    """

    general.checkPrereqs(testCaseNumber = 1,
                         testsToRun     = testsToRun)

    global browser_object

    browser_object = bt = BrowserOvs()

    bt.login()


@with_setup(None, close_browser)
def ovs_wrong_password_test():
    """
    """

    general.checkPrereqs(testCaseNumber = 2,
                         testsToRun     = testsToRun)

    global browser_object

    browser_object = bt = BrowserOvs()
    bt.password = "wrong_password"
    bt.login(wait = False)
    time.sleep(5)
    bt.check_invalid_credentials_alert()
    assert "dashboard" not in bt.browser.title, "Failed login should not go to dashboard"


@with_setup(None, close_browser)
def ovs_wrong_username_test():
    """
    """

    general.checkPrereqs(testCaseNumber = 3,
                         testsToRun     = testsToRun)

    global browser_object

    browser_object = bt = BrowserOvs()
    bt.username = "wrong_username"
    bt.login(wait = False)
    time.sleep(5)
    bt.check_invalid_credentials_alert()
    assert "dashboard" not in bt.browser.title, "Failed login should not go to dashboard"


@with_setup(None, close_browser)
def vpool_add_test():
    """
    %s
    """ % general.getFunctionName()

    general.checkPrereqs(testCaseNumber = 4,
                         testsToRun     = testsToRun)

    global browser_object

    browser_object = vpt = Vpool()
    vpool = VPoolList.get_vpool_by_name(vpt.vpool_name)
    if vpool:
        general.remove_vpool(vpt)

    vpt.login()
    general.add_vpool(vpt)

    vpt.browse_to(vpt.get_url() + '#full/vpools', '')
    time.sleep(5)
    vpt.wait_for_text(vpt.vpool_name)


@with_setup(None, close_browser)
def vpool_remove_test():
    """
    %s
    """ % general.getFunctionName()

    general.checkPrereqs(testCaseNumber = 5,
                         testsToRun     = testsToRun)

    global browser_object


    browser_object = vpt = Vpool()
    vpool = VPoolList.get_vpool_by_name(vpt.vpool_name)

    vpt.login()
    if not vpool:
        general.add_vpool(vpt)

    general.remove_vpool(vpt)

    vpt.browse_to(vpt.get_url() + '#full/vpools', '')
    time.sleep(5)
    vpt.wait_for_text_to_vanish(vpt.vpool_name)


@with_setup(None, close_browser)
def validate_vpool_cleanup_test():
    """
    %s
    """ % general.getFunctionName()

    general.checkPrereqs(testCaseNumber = 6,
                         testsToRun     = testsToRun)

    global browser_object

    def check_voldrv_services(vpool_name, storagedrivers, running = True):
        voldrv_services = (pr + vpool_name for pr in ("ovs-volumedriver_", "ovs-failovercache_"))
        for sd in storagedrivers:
            node = sd.storagerouter.ip
            for voldrv_service in voldrv_services:
                retries = 15
                while retries:
                    if general.is_service_running(voldrv_service, node) == running:
                        break
                    time.sleep(1)
                    retries -= 1
                assert general.is_service_running(voldrv_service, node) == running, \
                "Service {0} is not {1} on node {2}".format(voldrv_service,
                                                           {True: "running", False: "stopped"}[running],
                                                           node)

    def check_mountpoints(storagedrivers, is_present = True):
        for sd in storagedrivers:
            mountpoint = sd.mountpoint
            node = sd.storagerouter.ip

            retries = 20
            while retries:
                out = general.execute_command_on_node(node, "df | grep {0} || true".format(mountpoint))
                if (mountpoint in out) == is_present:
                    break
                time.sleep(1)
                retries -= 1

            assert (mountpoint in out) == is_present, "Vpool mountpoint {0} is {1} mounted on node {2}\n{3}".format(mountpoint,
                                                                                                                  {True: "not", False: "still"}[is_present],
                                                                                                                  node,
                                                                                                                  out)


    browser_object = vpt = Vpool()
    vpt.login()


    for idx in range(2):

        general.add_vpool(vpt)
        vpool = VPoolList.get_vpool_by_name(vpt.vpool_name)
        #hold a copy of these for later
        storagedrivers = list(vpool.storagedrivers)

        check_voldrv_services(vpool_name, storagedrivers)
        check_mountpoints(storagedrivers)

        #create volume
        local_vsa = general.get_local_vsa()
        sd = [sd for sd in vpool.storagedrivers if sd.storagerouter.ip == local_vsa.ip][0]
        file_name = os.path.join(sd.mountpoint, "validate_vpool" + str(time.time()).replace(".","") + ".raw")
        general.execute_command("truncate {0} --size 10000000".format(file_name))

        time.sleep(10)
        general.execute_command("rm {0}".format(file_name))

        general.remove_vpool(vpt)

        time.sleep(5)
        check_voldrv_services(vpool_name, storagedrivers, running = False)
        check_mountpoints(storagedrivers, is_present = False)




@with_setup(None, close_browser)
def set_as_template_test():
    """
    %s
    Create a vm and check if it gets registered
    """ % general.getFunctionName()

    general.checkPrereqs(testCaseNumber = 7,
                         testsToRun     = testsToRun)

    global browser_object

    name = machinename + "_set_as_template"

    vpool = VPoolList.get_vpool_by_name(vpool_name)
    if not vpool:
        browser_object = vpt = Vpool()
        vpt.login()
        general.add_vpool(vpt)
        vpt.teardown()
        vpool = VPoolList.get_vpool_by_name(vpool_name)

    hpv = general_hypervisor.Hypervisor.get(vpool.name)
    hpv.create_vm(name)

    browser_object = bt = Vmachine()
    bt.login()

    bt.check_machine_is_present(name, 100)
    bt.check_machine_disk_is_present()
    bt.set_as_template(name, should_not_allow = True)

    hpv.shutdown(name)

    bt.set_as_template(name)
    bt.check_machine_is_not_present(name)

    bt.teardown()


@with_setup(None, close_browser)
def create_from_template_test():
    """
    %s
    * create vm from template
    """ % general.getFunctionName()

    general.checkPrereqs(testCaseNumber = 8,
                         testsToRun     = testsToRun)

    global browser_object

    name = machinename + "_create" + str(random.randrange(0,9999999))

    vpool = VPoolList.get_vpool_by_name(vpool_name)
    hpv = general_hypervisor.Hypervisor.get(vpool.name)

    template = Vmachine.get_template(machinename, vpool_name)

    browser_object = bt = Vmachine()
    bt.login()

    bt.create_from_template(template.name, name)
    bt.check_machine_is_present(name)

    hpv.delete(name)


@with_setup(None, close_browser)
def start_stop_vm_test():
    """
    %s
    """ % general.getFunctionName()

    general.checkPrereqs(testCaseNumber = 9,
                         testsToRun     = testsToRun)

    name = machinename + "_start" + str(random.randrange(0,9999999))

    vpool = VPoolList.get_vpool_by_name(vpool_name)
    hpv = general_hypervisor.Hypervisor.get(vpool.name)

    template = Vmachine.get_template(machinename, vpool_name)

    browser_object = bt = Vmachine()
    bt.login()

    bt.create_from_template(template.name, name)
    bt.check_machine_is_present(name)

    hpv.start(name)

    if general_hypervisor.get_hypervisor_type() == "KVM":
        vm_ip = hpv.wait_for_vm_pingable(name)

        prev_stats = bt.check_vm_stats_overview_update(name)
        hpv.write_test_data(vm_name           = name,
                            filename          = "test",
                            zero_filled       = True,
                            zero_filled_count = 500 * 1024)
        prev_stats = bt.check_vm_stats_overview_update(name, prev_stats = prev_stats)


        prev_stats = bt.check_vm_stats_detail_update(name)
        hpv.write_test_data(vm_name           = name,
                            filename          = "test2",
                            zero_filled       = True,
                            zero_filled_count = 500 * 1024)

        prev_stats = bt.check_vm_stats_detail_update(name, prev_stats = prev_stats)


    hpv.shutdown(name)
    if general_hypervisor.get_hypervisor_type() == "KVM":
        hpv.wait_for_vm_pingable(name, pingable = False, vm_ip = vm_ip)

    hpv.delete(name)


@with_setup(None, close_browser)
def delete_clone_test():
    """
    %s
    """ % general.getFunctionName()

    general.checkPrereqs(testCaseNumber = 10,
                         testsToRun     = testsToRun)

    global browser_object

    name = machinename + "_delete" + str(random.randrange(0,9999999))

    template = Vmachine.get_template(machinename, vpool_name)

    browser_object = bt = Vmachine()
    bt.login()

    bt.create_from_template(template.name, name)
    bt.check_machine_is_present(name)

    bt.browse_to(bt.get_url() + '#full/vmachines', 'vmachines')
    bt.wait_for_text(name)

    vpool = VPoolList.get_vpool_by_name(vpool_name)
    hpv = general_hypervisor.Hypervisor.get(vpool.name)

    hpv.delete(name)

    bt.wait_for_text_to_vanish(name, timeout = 10)

    assert not VMachineList.get_vmachine_by_name(name), "Vmachine was not deleted from model after hypervisor deletion"


@with_setup(None, close_browser)
def machine_snapshot_rollback_test():
    """
    %s
    """ % general.getFunctionName()

    general.checkPrereqs(testCaseNumber = 11,
                     testsToRun     = testsToRun)

    global browser_object

    name = machinename + "_sn_roll" + str(random.randrange(0,9999999))

    vpool = VPoolList.get_vpool_by_name(vpool_name)
    hpv = general_hypervisor.Hypervisor.get(vpool.name)

    template = Vmachine.get_template(machinename, vpool_name)

    browser_object = bt = Vmachine()
    bt.login()

    bt.create_from_template(template.name, name)
    bt.check_machine_is_present(name)

    hpv.start(name)
    if general_hypervisor.get_hypervisor_type() == "KVM":
        hpv.wait_for_vm_pingable(name)

    vm =  VMachineList.get_vmachine_by_name(name)[0]

    #First snapshot
    filename1      = "testA"
    snapshot_name1 = name + "ss" + filename1

    if general_hypervisor.get_hypervisor_type() == "KVM":
        hpv.write_test_data(name, filename1)
        hpv.check_test_data(name, filename1)

    snapshots_before = vm.snapshots
    bt.snapshot(name, snapshot_name1)
    bt.check_snapshot_present(name, snapshot_name1)
    Vmachine.check_snapshot_model(snapshots_before, snapshot_name1, vm)

    #Second snapshot
    filename2      = "testB"
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

    bt.rollback(name, snapshot_name1, should_not_allow = True)

    hpv.shutdown(name)
    time.sleep(3)

    bt.rollback(name, snapshot_name1)

    hpv.start(name)
    if general_hypervisor.get_hypervisor_type() == "KVM":
        hpv.check_test_data(name, filename1)
        hpv.check_test_data(name, filename2, not_present = True)


@with_setup(None, close_browser)
def try_to_delete_template_with_clones_test():
    """
    %s
    """ % general.getFunctionName()

    general.checkPrereqs(testCaseNumber = 12,
                     testsToRun     = testsToRun)

    global browser_object

    name = machinename + "_tmpl_cln" + str(random.randrange(0,9999999))

    template = Vmachine.get_template(machinename, vpool_name)
    vpool = VPoolList.get_vpool_by_name(vpool_name)
    hpv = general_hypervisor.Hypervisor.get(vpool.name)

    browser_object = bt = Vmachine()
    bt.login()

    bt.create_from_template(template.name, name)
    bt.check_machine_is_present(name)

    bt.delete_template(template.name, should_fail = True)
    assert VMachineList.get_vmachine_by_name(template.name)

    #clone should still work
    hpv.start(name)
    if general_hypervisor.get_hypervisor_type() == "KVM":
        vm_ip = hpv.wait_for_vm_pingable(name)

    hpv.shutdown(name)
    if general_hypervisor.get_hypervisor_type() == "KVM":
        hpv.wait_for_vm_pingable(name, pingable = False, vm_ip = vm_ip)


@with_setup(None, close_browser)
def delete_template_test():
    """
    %s
    """ % general.getFunctionName()

    general.checkPrereqs(testCaseNumber = 13,
                     testsToRun     = testsToRun)

    global browser_object


    template = Vmachine.get_template(machinename, vpool_name)
    vpool = VPoolList.get_vpool_by_name(vpool_name)
    hpv = general_hypervisor.Hypervisor.get(vpool.name)
    #first delete all clones:
    hpv.delete_clones(template.name)

    browser_object = bt = Vmachine()
    bt.login()
    bt.delete_template(template.name)

