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
import logging

import random
from ci.tests.general           import general
from ci.tests.general           import general_hypervisor
from ci.tests.gui.vpool         import Vpool
from ci.tests.gui.browser_ovs   import BrowserOvs
from ci                         import autotests

from ovs.extensions.grid        import manager
from ovs.dal.lists              import vpoollist
from ovs.dal.lists.vmachinelist import VMachineList

from selenium.webdriver.remote.remote_connection import LOGGER
LOGGER.setLevel(logging.WARNING)

testsToRun = general.getTestsToRun(autotests.getTestLevel())
machinename = "AT" + __name__.split(".")[-1]

def setup():

    print "setup called " + __name__


def teardown():
    pass


def ovs_login_test():
    """
    """

    general.checkPrereqs(testCaseNumber = 1,
                         testsToRun     = testsToRun)

    bt = None
    try:
        bt = BrowserOvs()
        bt.login()
    except Exception as ex:
        print str(ex)
        raise
    finally:
        try:
            if bt:
                bt.teardown()
        except Exception as ex2:
            os.write(1, str(ex2))


def vpool_add_test():
    """
    %s
    """ % general.getFunctionName()

    general.checkPrereqs(testCaseNumber = 2,
                         testsToRun     = testsToRun)

    vpt = None
    try:

        vpt = Vpool()
        vpool = vpoollist.VPoolList.get_vpool_by_name(vpt.vpool_name)
        if vpool:
            for storagedrivers_guid in vpool.storagedrivers_guids:
                manager.Manager.remove_vpool(storagedrivers_guid)

        vpt.login()
        vpt.add_vpool()

    except Exception as ex:
        print str(ex)
        raise

    finally:
        try:
            if vpt:
                vpt.teardown()
        except Exception as ex2:
            os.write(1, str(ex2))

def vpool_remove_test():
    """
    %s
    """ % general.getFunctionName()

    general.checkPrereqs(testCaseNumber = 3,
                         testsToRun     = testsToRun)

    vpt = None
    try:

        vpt = Vpool()
        vpt.login()

        vpool = vpoollist.VPoolList.get_vpool_by_name(vpt.vpool_name)
        if not vpool:
            vpt.add_vpool()


        vpt.remove_vpool(vpt.vpool_name)

    except Exception as ex:
        print str(ex)
        raise

    finally:
        try:
            if vpt:
                vpt.teardown()
        except Exception as ex2:
            os.write(1, str(ex2))



def set_as_template_test():
    """
    %s
    Create a vm and check if it gets registered
    """ % general.getFunctionName()

    general.checkPrereqs(testCaseNumber = 4,
                         testsToRun     = testsToRun)

    name = machinename + "_set_as_template"

    vpool = vpoollist.VPoolList.get_vpools()
    if not vpool:
        vpt = Vpool()
        vpt.login()
        vpt.add_vpool()
        vpool = vpoollist.VPoolList.get_vpools()

    vpool = vpool[0]
    hpv = general_hypervisor.Hypervisor.get(vpool.name)
    hpv.create_vm(name)

    bt = BrowserOvs()
    bt.login()

    bt.check_machine_is_present(name)
    bt.check_machine_disk_is_present()

    hpv.shutdown(name)

    bt.set_as_template(name)

    bt.teardown()


def create_from_template_test():
    """
    %s
    * create vm from template
    """ % general.getFunctionName()

    general.checkPrereqs(testCaseNumber = 5,
                         testsToRun     = testsToRun)

    name = machinename + "_create" + str(random.randrange(0,9999999))

    vpool = vpoollist.VPoolList.get_vpools()[0]
    hpv = general_hypervisor.Hypervisor.get(vpool.name)

    bt = BrowserOvs()
    bt.login()

    templates = VMachineList.get_vtemplates()

    if not templates:
        tmpl_name = name + "tmpl"
        hpv.create_vm(tmpl_name)
        hpv.shutdown(tmpl_name)

        bt.set_as_template(name)
        templates = VMachineList.get_vtemplates()
        assert templates, "Failed to set as template"

    template = templates[0]

    bt.create_from_template(template.name, name)
    bt.check_machine_is_present(name)

    hpv.start(name)

    #hpv.wait_for_vm_pingable(name)

    hpv.shutdown(name)

    bt.teardown()

