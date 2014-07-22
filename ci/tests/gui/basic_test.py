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
import logging

import random

from nose.tools                 import with_setup

from ci.tests.general           import general
from ci.tests.general           import general_hypervisor
from ci.tests.gui.vpool         import Vpool
from ci.tests.gui.browser_ovs   import BrowserOvs
from ci.tests.gui.vmachine      import Vmachine
from ci                         import autotests

from ovs.extensions.grid        import manager
from ovs.dal.lists              import vpoollist
from ovs.dal.lists.vmachinelist import VMachineList

from selenium.webdriver.remote.remote_connection import LOGGER
LOGGER.setLevel(logging.WARNING)

testsToRun     = general.getTestsToRun(autotests.getTestLevel())
machinename    = "AT" + __name__.split(".")[-1]
vpool_name     = autotests._getConfigIni().get("vpool", "vpool_name")
browser_object = None


def setup():

    print "setup called " + __name__


def teardown():
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
def vpool_add_test():
    """
    %s
    """ % general.getFunctionName()

    general.checkPrereqs(testCaseNumber = 2,
                         testsToRun     = testsToRun)

    global browser_object

    browser_object = vpt = Vpool()
    vpool = vpoollist.VPoolList.get_vpool_by_name(vpt.vpool_name)
    if vpool:
        for storagedrivers_guid in vpool.storagedrivers_guids:
            manager.Manager.remove_vpool(storagedrivers_guid)

    vpt.login()
    vpt.add_vpool()


@with_setup(None, close_browser)
def vpool_remove_test():
    """
    %s
    """ % general.getFunctionName()

    general.checkPrereqs(testCaseNumber = 3,
                         testsToRun     = testsToRun)

    global browser_object

    browser_object = vpt = Vpool()
    vpt.login()

    vpool = vpoollist.VPoolList.get_vpool_by_name(vpt.vpool_name)
    if not vpool:
        vpt.add_vpool()


    vpt.remove_vpool(vpt.vpool_name)


@with_setup(None, close_browser)
def set_as_template_test():
    """
    %s
    Create a vm and check if it gets registered
    """ % general.getFunctionName()

    general.checkPrereqs(testCaseNumber = 4,
                         testsToRun     = testsToRun)

    global browser_object

    name = machinename + "_set_as_template"

    vpool = vpoollist.VPoolList.get_vpool_by_name(vpool_name)
    if not vpool:
        browser_object = vpt = Vpool()
        vpt.login()
        vpt.add_vpool()
        vpt.teardown()
        vpool = vpoollist.VPoolList.get_vpool_by_name(vpool_name)

    hpv = general_hypervisor.Hypervisor.get(vpool.name)
    hpv.create_vm(name)

    browser_object = bt = Vmachine()
    bt.login()

    bt.check_machine_is_present(name)
    bt.check_machine_disk_is_present()

    hpv.shutdown(name)

    bt.set_as_template(name)

    bt.teardown()


@with_setup(None, close_browser)
def create_from_template_test():
    """
    %s
    * create vm from template
    """ % general.getFunctionName()

    general.checkPrereqs(testCaseNumber = 5,
                         testsToRun     = testsToRun)

    global browser_object

    name = machinename + "_create" + str(random.randrange(0,9999999))

    vpool = vpoollist.VPoolList.get_vpool_by_name(vpool_name)
    hpv = general_hypervisor.Hypervisor.get(vpool.name)

    template = Vmachine.get_template(machinename, vpool_name)

    browser_object = bt = Vmachine()
    bt.login()

    bt.create_from_template(template.name, name)
    bt.check_machine_is_present(name)

    hpv.start(name)
    vm_ip = hpv.wait_for_vm_pingable(name)

    hpv.shutdown(name)
    hpv.wait_for_vm_pingable(name, pingable = False, vm_ip = vm_ip)


@with_setup(None, close_browser)
def delete_clone_test():
    """
    %s
    """ % general.getFunctionName()

    general.checkPrereqs(testCaseNumber = 6,
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

    vpool = vpoollist.VPoolList.get_vpool_by_name(vpool_name)
    hpv = general_hypervisor.Hypervisor.get(vpool.name)

    hpv.delete(name)

    bt.wait_for_text_to_vanish(name, timeout = 10)

    assert not VMachineList.get_vmachine_by_name(name), "Vmachine was not deleted from model after hypervisor deletion"


@with_setup(None, close_browser)
def machine_snapshot_rollback_test():
    """
    %s
    """ % general.getFunctionName()

    general.checkPrereqs(testCaseNumber = 7,
                     testsToRun     = testsToRun)

    global browser_object

    name = machinename + "_sn_roll" + str(random.randrange(0,9999999))

    vpool = vpoollist.VPoolList.get_vpool_by_name(vpool_name)
    hpv = general_hypervisor.Hypervisor.get(vpool.name)

    template = Vmachine.get_template(machinename, vpool_name)

    browser_object = bt = Vmachine()
    bt.login()

    bt.create_from_template(template.name, name)
    bt.check_machine_is_present(name)

    hpv.start(name)
    hpv.wait_for_vm_pingable(name)

    vm =  VMachineList.get_vmachine_by_name(name)[0]

    #First snapshot
    filename1      = "testA"
    snapshot_name1 = name + "ss" + filename1

    hpv.write_test_data(name, filename1)
    hpv.check_test_data(name, filename1)

    snapshots_before = vm.snapshots
    bt.snapshot(name, snapshot_name1)
    bt.check_snapshot_present(name, snapshot_name1)
    Vmachine.check_snapshot_model(snapshots_before, snapshot_name1, vm)

    #Second snapshot
    filename2      = "testB"
    snapshot_name2 = name + "ss" + filename2

    hpv.write_test_data(name, filename2)
    hpv.check_test_data(name, filename2)

    snapshots_before = vm.snapshots
    bt.snapshot(name, snapshot_name2)
    bt.check_snapshot_present(name, snapshot_name2)
    Vmachine.check_snapshot_model(snapshots_before, snapshot_name2, vm)


    hpv.delete_test_data(name, filename1)
    bt.rollback(name, snapshot_name1, should_not_allow = True)

    hpv.shutdown(name)
    time.sleep(3)

    bt.rollback(name, snapshot_name1)

    hpv.start(name)
    hpv.check_test_data(name, filename1)
    hpv.check_test_data(name, filename2, not_present = True)


@with_setup(None, close_browser)
def try_to_delete_template_with_clones_test():
    """
    %s
    """ % general.getFunctionName()

    general.checkPrereqs(testCaseNumber = 8,
                     testsToRun     = testsToRun)

    global browser_object

    name = machinename + "_tmpl_cln" + str(random.randrange(0,9999999))

    template = Vmachine.get_template(machinename, vpool_name)
    vpool = vpoollist.VPoolList.get_vpool_by_name(vpool_name)
    hpv = general_hypervisor.Hypervisor.get(vpool.name)

    browser_object = bt = Vmachine()
    bt.login()

    bt.create_from_template(template.name, name)
    bt.check_machine_is_present(name)

    bt.delete_template(template.name, should_fail = True)
    assert VMachineList.get_vmachine_by_name(template.name)

    #clone should still work
    hpv.start(name)
    vm_ip = hpv.wait_for_vm_pingable(name)

    hpv.shutdown(name)
    hpv.wait_for_vm_pingable(name, pingable = False, vm_ip = vm_ip)


@with_setup(None, close_browser)
def delete_template_test():
    """
    %s
    """ % general.getFunctionName()

    general.checkPrereqs(testCaseNumber = 9,
                     testsToRun     = testsToRun)

    global browser_object


    template = Vmachine.get_template(machinename, vpool_name)
    vpool = vpoollist.VPoolList.get_vpool_by_name(vpool_name)
    hpv = general_hypervisor.Hypervisor.get(vpool.name)
    #first delete all clones:
    hpv.delete_clones(template.name)

    browser_object = bt = Vmachine()
    bt.login()
    bt.delete_template(template.name)

