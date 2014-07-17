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
from ci.tests.general           import general
from ci.tests.general           import general_hypervisor
from ci.tests.gui.vpool         import Vpool
from ci.tests.gui.browser_ovs   import BrowserOvs
from ci                         import autotests

from ovs.extensions.grid        import manager
from ovs.dal.lists              import vpoollist
from ovs.dal.lists.vmachinelist import VMachineList

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

    try:
        bt = BrowserOvs()
        bt.login()
    except Exception as ex:
        print str(ex)
        raise
    finally:
        try:
            bt.teardown()
        except Exception as ex2:
            os.write(1, str(ex2))



def vpool_add_test():
    """
    """

    general.checkPrereqs(testCaseNumber = 2,
                         testsToRun     = testsToRun)


    """
    vpt.set_username('admin')
    vpt.set_password('admin')
    vpt.set_url('https://10.100.131.71/')
    vpt.set_debug(True)

    vpt.set_vpool_name('saio')
    vpt.set_vpool_type('Swift S3')
    vpt.set_vpool_host('10.100.131.91')
    vpt.set_vpool_port(8080)
    vpt.set_vpool_access_key('test:tester')
    vpt.set_vpool_secret_key('testing')

    vpt.set_vpool_temp_mp('/var/tmp')
    vpt.set_vpool_md_mp('/mnt/metadata/saio')
    vpt.set_vpool_cache_mp('/mnt/cache/saio')
    vpt.set_vpool_vrouter_port(12323)
    vpt.set_vpool_storage_ip('172.22.131.10')
    """


    try:
        vpt = Vpool()
        vpool = vpoollist.VPoolList.get_vpool_by_name(vpt.vpool_name)
        if vpool:
            for vsrs_guid in vpool.vsrs_guids:
                manager.Manager.remove_vpool(vsrs_guid)
        vpt.login()
        vpt.add_vpool()
    except Exception as ex:
        print str(ex)
        raise
    finally:
        try:
            vpt.teardown()
        except Exception as ex2:
            os.write(1, str(ex2))


def set_as_template_test():
    """
    set_as_template_test
    Create a vm and check if it gets registered
    """

    general.checkPrereqs(testCaseNumber = 3,
                         testsToRun     = testsToRun)

    name = machinename + _set_as_template"

    vpool = vpoollist.VPoolList.get_vpools()[0]
    hpv = general_hypervisor.Hypervisor.get(vpool.name)
    hpv.create_vm(name)

    bt = BrowserOvs()
    bt.login()

    bt.check_machine_is_present(name)
    bt.check_machine_disk_is_present()

    hpv.shutdown(name)

    bt.set_as_template(name)


def create_from_template_test():
    """

    * create vm from template
    """

    general.checkPrereqs(testCaseNumber = 4,
                         testsToRun     = testsToRun)

    name = machinename + "_create"

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

    hpv.shutdown(name)

