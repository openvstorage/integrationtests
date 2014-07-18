import time

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

    def check_machine_disk_is_present(self, name = ''):
        """
        assume currently on machine page
        """
        self.log(self.browser.url)

        retries = 30
        while retries:
            disk_links_all = self.browser.find_link_by_partial_href("#full/vdisk/")

            self.log(str(disk_links_all))
            disk_links = [l for l in disk_links_all if name in l.text]
            if disk_links:
                break
            retries -= 1
            time.sleep(1)

        assert disk_links
        disk_links[0].click()

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

    def delete_template(self, template_name):

        tmpl = VMachineList.get_vmachine_by_name(template_name)
        assert tmpl, "Couldnt find template {}".format(template_name)
        tmpl = tmpl[0]
        assert tmpl.is_vtemplate, "Vm name is not a template {}".format(template_name)

        self.browse_to(self.get_url() + '#full/vtemplates', 'vtemplates')

        self.wait_for_text(template_name, 15)

        delete_button_id = "vtemplateDelete_{0}".format(tmpl.guid)
        delete_button = self.browser.find_by_id(delete_button_id)
        delete_button.click()

        modal = self.wait_for_modal()

        self.click_modal_button("Yes")

        self.wait_for_text_to_vanish(template_name, 25)
        assert not VMachineList.get_vmachine_by_name(template_name), "Deleting template did not remove it from the model"

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
