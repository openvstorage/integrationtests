import time
import datetime

from browser_ovs                    import BrowserOvs
from ovs.dal.lists.vmachinelist     import VMachineList
from ovs.dal.lists                  import vpoollist
from ci.tests.general               import general_hypervisor
from ci.tests.gui.vpool             import Vpool

class Vmachine(BrowserOvs):
    def __init__(self,
                 browser_choice     = 'chrome' ):

        self.bt = BrowserOvs.__init__(self, browser_choice = browser_choice)

    def check_machine_is_present(self, machinename, retries = 30):
        self.browse_to(self.get_url() + '#full/vmachines', 'vmachines')

        self.wait_for_text(machinename, retries)
        self.click_on_tbl_item(machinename)
        self.wait_for_text(machinename, retries)
        time.sleep(2)

    def check_machine_disk_is_present(self, name = ''):
        """
        assume currently on machine page
        """
        self.log(self.browser.url)

        check_ok = False
        retries = 100
        while retries:
            disk_links_all = self.browser.find_link_by_partial_href("#full/vdisk/")

            self.log(str(disk_links_all))
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

        assert check_ok, "Failed to check machine disks"


    def set_as_template(self, name):
        self.check_machine_is_present(name)

        setastemplate_button = self.browser.find_by_id("buttonVmachineSetAsTemplate")
        assert setastemplate_button
        setastemplate_button = setastemplate_button[0]
        setastemplate_button.click()

        self.click_modal_button('Set as Template')

        self.wait_for_wait_notification('Machine {} set as template'.format(name))

    def create_from_template(self, template_name, vm_name):
        self.browse_to(self.get_url() + '#full/vtemplates', 'vtemplates')

        time.sleep(5)

        tmpl_obj = VMachineList.get_vmachine_by_name(template_name)
        assert tmpl_obj, "Template with name {} not found".format(template_name)
        tmpl_obj = tmpl_obj[0]

        clone_button_id = "vtemplateClone_{}".format(tmpl_obj.guid)
        clone_button = self.browser.find_by_id(clone_button_id)
        clone_button.click()

        #wait for the wizard modal window
        modal = self.wait_for_modal()

        #fill out the wizard
        self.fill_out('name', vm_name)
        self.click_on('Nothing selected')
        time.sleep(2)
        menu = [m for m in self.browser.find_by_css("ul.dropdown-menu") if m.visible]
        assert menu
        #@todo: maybe define which host to select instead of the first one
        menu[0].click()

        self.click_on('Finish', retries = 100)

        self.wait_for_wait_notification('Creating from {} successfully'.format(template_name), retries = 2000)

    def delete_template(self, template_name, should_fail = False):

        tmpl = VMachineList.get_vmachine_by_name(template_name)
        assert tmpl, "Couldnt find template {}".format(template_name)
        tmpl = tmpl[0]
        assert tmpl.is_vtemplate, "Vm name is not a template {}".format(template_name)

        self.browse_to(self.get_url() + '#full/vtemplates', 'vtemplates')

        self.wait_for_text(template_name, 15)

        delete_button_id = "vtemplateDelete_{0}".format(tmpl.guid)
        delete_button = self.browser.find_by_id(delete_button_id)
        delete_button.click()

        if not should_fail:
            modal = self.wait_for_modal()
            self.click_modal_button("Yes")

            self.wait_for_wait_notification("Machine {} deleted".format(template_name))
            self.wait_for_text_to_vanish(template_name, 25)

            assert not VMachineList.get_vmachine_by_name(template_name), "Deleting template did not remove it from the model"
        else:
            time.sleep(15)
            self.wait_for_modal(should_exist = False)

    def snapshot(self, vm_name, snapshot_name, consistent = False):
        self.check_machine_is_present(vm_name)

        snapshot_button = self.browser.find_by_id("buttonVmachineSnapshot")
        assert snapshot_button
        snapshot_button = snapshot_button[0]
        snapshot_button.click()

        vm =  VMachineList.get_vmachine_by_name(vm_name)
        assert vm, "Vm with name {} not found".format(vm_name)

        self.wait_for_modal()
        if consistent:
            self.check_checkboxes()
        self.fill_out('name', snapshot_name)
        self.click_modal_button('Finish')

        self.wait_for_wait_notification('Snapshot successfully')
        time.sleep(2)

    def check_snapshot_present(self, vm_name, snapshot_name):
        #verify snapshot present in snapshot tab
        self.check_machine_is_present(vm_name)

        self.click_on_tbl_header('snapshots')
        self.wait_for_text(snapshot_name)

    def rollback(self, vm_name, ss_name, should_not_allow = False):
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


        if should_not_allow:
            try:
                snapshot_button.click()
            except Exception as ex:
                if "Element is not clickable" not in str(ex):
                    raise
            self.wait_for_modal(should_exist = False)
        else:
            snapshot_button.click()
            self.wait_for_modal()
            d = datetime.datetime.fromtimestamp(float(ss['timestamp'])).strftime("%I:%M:%S")
            if d.startswith("0"):
                d = d[1:]

            self.choose(identifier = '(', value = d)
            self.click_modal_button('Finish')
            self.wait_for_wait_notification("rollback successfully")

    @staticmethod
    def check_snapshot_model(snapshots_before, snapshot_name, vm_obj):
        snapshots_after = vm_obj.snapshots
        assert len(snapshots_after) > len(snapshots_before), "Created snapshot did not appear in model"
        assert [ss for ss in vm_obj.snapshots if ss['label'] == snapshot_name], "Newly created snapshot not found in model"

    @staticmethod
    def get_template(machinename, vpool_name):
        browser_object = None
        try:
            vpool = vpoollist.VPoolList.get_vpool_by_name(vpool_name)
            if not vpool:
                browser_object = vpt = Vpool()
                vpt.login()
                vpt.add_vpool()
                vpool = vpoollist.VPoolList.get_vpool_by_name(vpool_name)
                vpt.teardown()

            assert vpool, "Count not find usable vpool"

            templates = VMachineList.get_vtemplates()

            if not templates:
                tmpl_name = machinename + "tmpl"
                hpv = general_hypervisor.Hypervisor.get(vpool.name)
                hpv.create_vm(tmpl_name)
                time.sleep(10)
                hpv.shutdown(tmpl_name)

                browser_object = bt = Vmachine()
                bt.login()
                bt.set_as_template(tmpl_name)
                templates = VMachineList.get_vtemplates()
                bt.teardown()

            assert templates, "Failed to get template"
            return templates[0]
        except:
            raise
        finally:
            if browser_object:
                browser_object.teardown()
