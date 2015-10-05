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

import logging
import time
import datetime

from browser_ovs import BrowserOvs
from ovs.dal.lists.vmachinelist import VMachineList
from ci.tests.general import general_hypervisor
from ci.tests.general import general


class Vmachine(BrowserOvs):
    def __init__(self, browser_choice='chrome'):

        if not getattr(self, "scr_name", ""):
            self.scr_name = general.get_function_name(1)

        self.bt = BrowserOvs.__init__(self, browser_choice=browser_choice)

    def check_machine_is_present(self, machinename, retries=30):
        logging.log(1, "Checking if vm: {0} is present".format(machinename))
        vmachines_url = self.get_url() + '#full/vmachines'
        self.take_screenshot("before_check_machine_is_not_present")
        if self.browser.url != vmachines_url:
            self.browse_to(vmachines_url, 'vmachines')
        self.take_screenshot("before1_check_machine_is_not_present")
        self.wait_for_text(machinename, retries)
        self.click_on_tbl_item(machinename)
        time.sleep(2)
        self.take_screenshot("after_check_machine_is_not_present")
        self.wait_for_text(machinename, retries)
        time.sleep(2)
        self.take_screenshot("after1_check_machine_is_not_present")

    def check_machine_is_not_present(self, machinename, retries=30):
        self.take_screenshot("before_check_machine_is_not_present")
        self.browse_to(self.get_url() + '#full/vmachines', 'vmachines')
        self.take_screenshot("before1_check_machine_is_not_present")
        self.wait_for_text_to_vanish(machinename, retries)
        self.take_screenshot("after_check_machine_is_not_present")

    def check_machine_disk_is_present(self, name=''):
        """
        assume currently on machine page
        """
        vdisks_url = self.get_url() + '#full/vdisks'
        if self.browser.url != vdisks_url:
            self.browse_to(vdisks_url, 'vdisks')

        logging.log(1, self.browser.url)

        check_ok = False
        retries = 60
        disk_links_all = ''

        self.take_screenshot("before_check_machine_disk_is_present")
        while retries:
            disk_links_all = self.browser.find_link_by_partial_href("#full/vdisk/")
            logging.log(1, 'disk links: {0}'.format(disk_links_all))

            disk_links = [l for l in disk_links_all if name in l.text]
            if disk_links:
                try:
                    disk_links[0].click()
                    check_ok = True
                    break
                except Exception as ex:
                    print str(ex)

            retries -= 1
            time.sleep(1)
        self.take_screenshot("after_check_machine_disk_is_present")
        assert check_ok, "Failed to check machine disks {0} with name: {1}".format(disk_links_all, name)

    def set_as_template(self, name, allowed=True):
        self.check_machine_is_present(name)

        setastemplate_button = self.get_single_item_by_id("buttonVmachineSetAsTemplate")

        if allowed:
            try:
                setastemplate_button.click()
                self.wait_for_modal()
            except Exception as ex:
                print str(ex)

            time.sleep(0.5)

            self.click_modal_button('Set as Template')

            self.wait_for_wait_notification('Machine {} set as template'.format(name), retries=150)
        else:
            try:
                setastemplate_button.click()
            except Exception as ex:
                if "Element is not clickable" not in str(ex):
                    raise
            self.wait_for_modal(should_exist=False)

    def check_vm_stats_overview_update(self, vm_name, prev_stats="", retries=30):
        """
        check stats are updating under the vmachines overview page
        """
        vms_url = self.get_url() + '#full/vmachines'
        if self.browser.url != vms_url:
            self.browse_to(vms_url)

        vm_obj = VMachineList.get_vmachine_by_name(vm_name)
        assert vm_obj, "Vm with name {} not found"
        vm_obj = vm_obj[0]

        self.take_screenshot("before_check_vm_stats_overview_update")
        vm_tr = self.browser.find_by_id("vmachine_{}".format(vm_obj.guid))
        assert vm_tr, "Didn't find table row for {} vm in the vmachines overview".format(vm_name)
        vm_tr = vm_tr[0]
        self.take_screenshot("after_check_vm_stats_overview_update")

        tds = vm_tr.find_by_tag("td")
        stats_line = ""
        while retries:
            stats_line = [td.text for td in tds]
            if stats_line != prev_stats:
                break
            time.sleep(1)
            retries -= 1
        assert stats_line != prev_stats,\
            "Vm stats did not change for vm {0}, prev:\n{1}\nactual:\n{2}".format(vm_name, prev_stats, stats_line)
        return stats_line

    def check_vm_stats_detail_update(self, vm_name, prev_stats="", retries=30):
        """
        check stats are updating under the vmachine detail page
        """
        vm_obj = VMachineList.get_vmachine_by_name(vm_name)
        assert vm_obj, "Vm with name {} not found"
        vm_obj = vm_obj[0]

        self.check_machine_is_present(vm_name)

        self.take_screenshot("before_check_vm_stats_detail_update")
        # only handling first disk currently
        vm_tr = self.browser.find_by_id("vdisk_{}".format(vm_obj.vdisks[0].guid))
        logging.log(1, 'disk guid to look for: {0}'.format(vm_obj.vdisks[0].guid))
        self.take_screenshot("after_check_vm_stats_detail_update")
        assert vm_tr, "Didn't find table row for {0} disk in the vmachine detail overview".format(vm_obj.vdisks[0].name)
        vm_tr = vm_tr[0]

        tds = vm_tr.find_by_tag("td")
        stats_line = ""
        while retries:
            stats_line = [td.text for td in tds]
            if stats_line != prev_stats:
                break
            time.sleep(1)
            retries -= 1
        assert stats_line != prev_stats,\
            "Disk stats did not change for vm {0}, prev:\n{1}\nactual:\n{2}".format(vm_name, prev_stats, stats_line)
        return stats_line

    def create_from_template(self, template_name, vm_name):
        self.browse_to(self.get_url() + '#full/vtemplates', 'vtemplates')

        time.sleep(5)

        tmpl_obj = VMachineList.get_vmachine_by_name(template_name)
        assert tmpl_obj, "Template with name {} not found".format(template_name)
        tmpl_obj = tmpl_obj[0]

        clone_button_id = "vtemplateClone_{}".format(tmpl_obj.guid)
        clone_button = self.browser.find_by_id(clone_button_id)
        clone_button.click()

        # wait for wizard modal window
        _ = self.wait_for_modal()

        # fill out the wizard
        self.fill_out('name', vm_name)
        self.click_on('Nothing selected')
        time.sleep(2)

        # Choose hypervisor node
        menu = [m for m in self.browser.find_by_css("ul.dropdown-menu") if m.visible]
        assert menu
        menu = menu[0]
        items = menu.find_by_tag("li")
        local_vsa = general.get_local_vsa()
        pmachine_name = local_vsa.pmachine.name

        item = [item for item in items if pmachine_name in item.text]
        assert item,\
            "Pmachine {0} not found in list of pmachines {1}".format(pmachine_name, [item.text for item in items])
        item[0].click()

        self.click_on('Finish', retries=100)

        self.wait_for_wait_notification('Creating from {} successfully'.format(template_name), retries=500)

    def delete_template(self, template_name, should_fail=False):

        templates = VMachineList.get_vmachine_by_name(template_name)
        names = [vm.name for vm in templates]
        assert len(templates) == 1, "There should be only one template: {0}".format(','.join(names))

        template = templates[0]
        assert template.is_vtemplate, "Vm name is not a template {}".format(template_name)

        self.browse_to(self.get_url() + '#full/vtemplates', 'vtemplates')
        self.take_screenshot("before_delete_template")
        self.wait_for_text(template_name, 15)
        self.take_screenshot("after_1_delete_template")

        delete_button_id = "vtemplateDelete_{0}".format(template.guid)
        delete_button = self.browser.find_by_id(delete_button_id)
        delete_button.click()
        self.take_screenshot("after_2_delete_template")

        if not should_fail:
            _ = self.wait_for_modal()
            self.click_modal_button("Yes")

            self.wait_for_wait_notification("Machine {} deleted".format(template_name))
            self.wait_for_text_to_vanish(template_name, 25)
            self.take_screenshot("after_3_delete_template")

            assert not VMachineList.get_vmachine_by_name(template_name),\
                "Deleting template did not remove it from the model"
        else:
            time.sleep(15)
            self.wait_for_modal(should_exist=False)

    def snapshot(self, vm_name, snapshot_name, consistent=False):
        self.check_machine_is_present(vm_name)

        snapshot_button = self.browser.find_by_id("buttonVmachineSnapshot")
        assert snapshot_button
        snapshot_button = snapshot_button[0]
        snapshot_button.click()

        vm = VMachineList.get_vmachine_by_name(vm_name)
        assert vm, "Vm with name {} not found".format(vm_name)

        self.wait_for_modal()
        if consistent:
            self.check_checkboxes()
        self.fill_out('name', snapshot_name)
        self.click_modal_button('Finish')

        self.wait_for_wait_notification('Snapshot successfully')
        time.sleep(2)

    def check_snapshot_present(self, vm_name, snapshot_name):
        # verify snapshot present in snapshot tab
        self.check_machine_is_present(vm_name)

        self.click_on_tbl_header('snapshots')
        self.wait_for_text(snapshot_name)

    def rollback(self, vm_name, ss_name, allowed=True):
        vm = VMachineList.get_vmachine_by_name(vm_name)
        assert vm, "Vm with name {} not found".format(vm_name)
        vm = vm[0]
        ss = [ss for ss in vm.snapshots if ss['label'] == ss_name]
        assert ss, "Snapshot with name {} not found".format(ss_name)
        ss = ss[0]

        self.check_machine_is_present(vm_name)

        snapshot_button = self.browser.find_by_id("buttonVmachineRollback")
        assert snapshot_button
        snapshot_button = snapshot_button[0]

        if not allowed:
            snapshot_button.click()
            self.wait_for_modal(should_exist=False)
        else:
            snapshot_button.click()
            self.wait_for_modal()
            d = datetime.datetime.fromtimestamp(float(ss['timestamp'])).strftime("%I:%M:%S")
            if d.startswith("0"):
                d = d[1:]

            self.choose(identifier='(', value=d)
            self.click_modal_button('Finish')
            self.wait_for_wait_notification("rollback successfully")

    @staticmethod
    def check_snapshot_model(snapshots_before, snapshot_name, vm_obj):
        snapshots_after = vm_obj.snapshots
        assert len(snapshots_after) > len(snapshots_before), "Created snapshot did not appear in model"
        assert [ss for ss in vm_obj.snapshots if ss['label'] == snapshot_name],\
            "Newly created snapshot not found in model"

    @staticmethod
    def get_template(template_name, vpool_name):
        browser_object = None
        try:
            vpool = general.get_vpool(vpool_name)
            assert vpool, "Vpool with name: {0} not found!".format(vpool_name)

            templates = [t for t in VMachineList.get_vtemplates() if t.vdisks and
                         t.vdisks[0].vpool.guid == vpool.guid and t.name == template_name]
            logging.log(1, "Detected templates: {0}".format(templates))
            if not templates:
                hpv = general_hypervisor.Hypervisor.get(vpool.name)
                hpv.create_vm(template_name)
                time.sleep(10)
                hpv.poweroff(template_name)

                browser_object = bt = Vmachine()
                bt.login()
                bt.set_as_template(template_name)

                templates = [t for t in VMachineList.get_vtemplates()
                             if t.vdisks and t.vdisks[0].vpool.guid == vpool.guid and t.name == template_name]
                logging.log(1, "Detected templates after creation: {0}".format(templates))
                bt.teardown()

            assert len(templates) == 1, "Failed to get template"
            return templates[0]
        except:
            raise
        finally:
            if browser_object:
                browser_object.teardown()
