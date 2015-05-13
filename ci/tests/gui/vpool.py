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

# Automated test pre-requisites

# buttons and input fields should have an id starting with button and CamelCase detail:
# e.g. inputVpoolName, buttonAddVpool
#
# dropdown boxes are selected on their default value
#


import time
import urlparse

from browser_ovs import BrowserOvs
from ci import autotests
from ci.tests.general import general, general_hypervisor
from nose.plugins.skip import SkipTest
from splinter.driver.webdriver import NoSuchElementException
from ovs.dal.lists.storagerouterlist import StorageRouterList

LOCAL_VPOOL_TYPES = ['Local FS']
REMOTE_VPOOL_TYPES = ['Ceph S3', 'S3 compatible', 'Swift S3']

class Vpool(BrowserOvs):
    def __init__(self,
                 vpool_name='',
                 vpool_type_name='',
                 vpool_host='',
                 vpool_port='',
                 vpool_access_key='',
                 vpool_secret_key='',
                 vpool_temp_mp='',
                 vpool_md_mp='',
                 vpool_readcaches_mp='',
                 vpool_writecaches_mp='',
                 vpool_foc_mp='',
                 vpool_bfs_mp='',
                 vpool_storage_ip='',
                 browser_choice='chrome'):

        if not getattr(self, "scr_name", ""):
            self.scr_name = general.get_function_name(1)

        self.bt = BrowserOvs.__init__(self, browser_choice=browser_choice)

        cfg = autotests.getConfigIni()

        self.vpool_name = vpool_name or cfg.get("vpool", "vpool_name")
        self.vpool_type_name = vpool_type_name or cfg.get("vpool", "vpool_type_name")
        self.vpool_host = vpool_host or cfg.get("vpool", "vpool_host")
        self.vpool_port = vpool_port or cfg.get("vpool", "vpool_port")
        self.vpool_access_key = vpool_access_key or cfg.get("vpool", "vpool_access_key")
        self.vpool_secret_key = vpool_secret_key or cfg.get("vpool", "vpool_secret_key")
        self.vpool_temp_mp = vpool_temp_mp or cfg.get("vpool", "vpool_temp_mp")
        self.vpool_md_mp = vpool_md_mp or cfg.get("vpool", "vpool_md_mp")
        self.vpool_readcaches_mp = vpool_readcaches_mp or cfg.get("vpool", "vpool_readcaches_mp")
        self.vpool_writecaches_mp = vpool_writecaches_mp or cfg.get("vpool", "vpool_writecaches_mp")
        self.vpool_foc_mp = vpool_foc_mp or cfg.get("vpool", "vpool_foc_mp")
        self.vpool_bfs_mp = vpool_bfs_mp
        if self.vpool_type_name in ["Local FS"]:
            self.vpool_bfs_mp = vpool_bfs_mp or cfg.get("vpool", "vpool_bfs_mp")
        self.vpool_storage_ip = vpool_storage_ip or cfg.get("vpool", "vpool_storage_ip")

        for e in ["vpool_name", "vpool_type_name", "vpool_temp_mp", "vpool_md_mp",
                  "vpool_readcaches_mp", "vpool_writecaches_mp", "vpool_foc_mp"]:
            if not getattr(self, e):
                raise SkipTest(e)

        if self.vpool_type_name in REMOTE_VPOOL_TYPES and not getattr(self, "vpool_storage_ip"):
            raise SkipTest("vpool_storage_ip not filled in")

        print 'VpoolTest initialized'

    def get_vpool_name(self):
        return self.vpool_name

    def set_vpool_name(self, vpool_name):
        assert isinstance(vpool_name, str), 'Vpool name must be a string'
        self.vpool_name = vpool_name

    vpool_name = property(get_vpool_name, set_vpool_name)

    def get_vpool_type(self):
        return self.vpool_type_name

    def set_vpool_type(self, vpool_type_name):
        assert isinstance(vpool_type_name, str), 'Vpool type must be a string'
        self.vpool_type_name = vpool_type_name

    vpool_type_name = property(get_vpool_type, set_vpool_type)

    def get_vpool_host(self):
        return self.vpool_host

    def set_vpool_host(self, vpool_host):
        assert isinstance(vpool_host, str), 'Vpool host must be a string'
        self.vpool_host = vpool_host

    vpool_host = property(get_vpool_host, set_vpool_host)

    def get_vpool_port(self):
        return self.vpool_port

    def set_vpool_port(self, vpool_port):
        assert isinstance(vpool_port, int), 'Vpool port must be an int'
        self.vpool_port = vpool_port

    vpool_port = property(get_vpool_port, set_vpool_port)

    def get_vpool_access_key(self):
        return self.vpool_access_key

    def set_vpool_access_key(self, vpool_access_key):
        assert isinstance(vpool_access_key, str), 'Vpool access key must be a string'
        self.vpool_access_key = vpool_access_key

    vpool_access_key = property(get_vpool_access_key, set_vpool_access_key)

    def get_vpool_secret_key(self):
        return self.vpool_secret_key

    def set_vpool_secret_key(self, vpool_secret_key):
        assert isinstance(vpool_secret_key, str), 'Vpool secret key must be a string'
        self.vpool_secret_key = vpool_secret_key

    vpool_secret_key = property(get_vpool_secret_key, set_vpool_secret_key)

    def get_vpool_temp_mp(self):
        return self.vpool_temp_mp

    def set_vpool_temp_mp(self, vpool_temp_mp):
        assert isinstance(vpool_temp_mp, str), 'Vpool temp mountpoint must be a string'
        self.vpool_temp_mp = vpool_temp_mp

    vpool_temp_mp = property(get_vpool_temp_mp, set_vpool_temp_mp)

    def get_vpool_md_mp(self):
        return self.vpool_md_mp

    def set_vpool_md_mp(self, vpool_md_mp):
        assert isinstance(vpool_md_mp, str), 'Vpool metadata mountpoint must be a string'
        self.vpool_md_mp = vpool_md_mp

    vpool_md_mp = property(get_vpool_md_mp, set_vpool_md_mp)

    def get_vpool_bfs_mp(self):
        return self.vpool_bfs_mp

    def set_vpool_bfs_mp(self, vpool_bfs_mp):
        assert isinstance(vpool_bfs_mp, str), 'Vpool metadata mountpoint must be a string'
        self.vpool_bfs_mp = vpool_bfs_mp

    vpool_bfs_mp = property(get_vpool_bfs_mp, set_vpool_bfs_mp)

    def get_vpool_readcaches_mp(self):
        return self.vpool_readcaches_mp

    def set_vpool_readcaches_mp(self, vpool_readcaches_mp):
        assert isinstance(vpool_readcaches_mp, list), 'Vpool readcaches mountpoint must be a list'
        self.vpool_readcaches_mp = vpool_readcaches_mp

    vpool_readcaches_mp = property(get_vpool_readcaches_mp, set_vpool_readcaches_mp)

    def get_vpool_writecaches_mp(self):
        return self.vpool_writecaches_mp

    def set_vpool_writecaches_mp(self, vpool_writecaches_mp):
        assert isinstance(vpool_writecaches_mp, list), 'Vpool writecaches mountpoint must be a list'
        self.vpool_writecaches_mp = vpool_writecaches_mp

    vpool_writecaches_mp = property(get_vpool_writecaches_mp, set_vpool_writecaches_mp)

    def get_vpool_foc_mp(self):
        return self.vpool_foc_mp

    def set_vpool_foc_mp(self, vpool_foc_mp):
        assert isinstance(vpool_foc_mp, str), 'Vpool foc mountpoint must be a string'
        self.vpool_foc_mp = vpool_foc_mp

    vpool_foc_mp = property(get_vpool_foc_mp, set_vpool_foc_mp)

    def get_vpool_vrouter_port(self):
        return self.vpool_vrouter_port

    def set_vpool_vrouter_port(self, vpool_vrouter_port):
        assert isinstance(vpool_vrouter_port, int), 'Vpool vrouter port must be an int'
        self.vpool_vrouter_port = vpool_vrouter_port

    vpool_vrouter_port = property(get_vpool_vrouter_port, set_vpool_vrouter_port)

    def get_vpool_storage_ip(self):
        return self.vpool_storage_ip

    def set_vpool_storage_ip(self, vpool_storage_ip):
        assert isinstance(vpool_storage_ip, str), 'Vpool storage ip must be a string'
        self.vpool_storage_ip = vpool_storage_ip

    vpool_storage_ip = property(get_vpool_storage_ip, set_vpool_storage_ip)

    def get_vpool_url(self):
        return urlparse.urljoin(self.get_url(), '/#full/vpools')

    def wait_for_backend(self, retries=40):
        while retries:
            backends = self.browser.find_link_by_partial_href("#full/backend-alba/")
            if backends:
                return backends
            retries -= 1

    def wait_for_tbl_row_with_button(self, retries=30):
        while retries:
            b = [e for e in self.browser.find_by_xpath("//tr/td/i") if e.visible and len(e.text) < 2]
            if b:
                return b[0]
            retries -= 1
            time.sleep(1)

    def add_backend(self):
        if self.vpool_type_name == "Remote Alternate Backend":
            self.browse_to(self.get_url() + '#full/backends', 'backends')
            backends = self.wait_for_backend(15)
            if not backends:
                input_field = self.browser.find_by_xpath("//tr/td/input")[0]
                input_field.fill("alba")
                ok = self.wait_for_tbl_row_with_button()
                ok.click()

                backends = self.wait_for_backend()
                assert backends
                backends[0].click()

                self.click_on_tbl_header('management', retries=30)
                add = self.wait_for_tbl_row_with_button(120)
                add.click()
                self.wait_for_modal()
                self.click_on("Yes")
                self.wait_for_wait_notification("was added to the backend.")

    def add_vpool(self):
        self.add_backend()

        self.browse_to(self.get_url() + '#full/vpools', 'vpools')
        assert self.wait_for_visible_element_by_id('buttonAddVpool', 5), 'Button Add vPool not present (yet)'
        self.click_on('AddVpool', retries=20)
        assert self.wait_for_visible_element_by_id('form.gather.vpool', 5), 'Add vPool wizard not present (yet)'
        self.choose('Local FS', self.vpool_type_name)
        self.fill_out('inputVpoolName', self.vpool_name)
        # time.sleep(3)

        # for grid select current node as initial storage router
        current_node_hostname = general.get_this_hostname()
        current_node_selection = sorted([sr.name for sr in StorageRouterList.get_storagerouters()])
        if current_node_selection[0] != current_node_hostname:
            self.choose(current_node_selection[0], current_node_hostname)
        time.sleep(2)

        # necessary to load local alba backend list
        if self.vpool_type_name == 'Open vStorage Backend':
            self.click_on('Reload', retries=100)

        if self.vpool_type_name in REMOTE_VPOOL_TYPES:
            self.fill_out('inputVpoolHost', self.vpool_host)
            self.fill_out('inputVpoolPort', self.vpool_port, clear_first=True)
            self.fill_out('inputVpoolAccessKey', self.vpool_access_key)
            self.fill_out('inputVpoolSecretKey', self.vpool_secret_key)
        time.sleep(2)

        # add check for alba with remote nodes

        self.click_on('Next', retries=150)
        time.sleep(2)

        # wait for page to load
        assert self.wait_for_visible_element_by_id('dropdown-button-mtpt-temp', 5), \
            'vPool wizard with mountpoint details not present (yet)'
        self.fill_out_custom_field('dropdown-button-mtpt-temp', self.vpool_temp_mp)
        self.fill_out_custom_field('dropdown-button-mtpt-md', self.vpool_md_mp)
        # @todo: accept defaults for read/write caches
        self.fill_out_custom_field('dropdown-button-mtpt-foc', self.vpool_foc_mp)
        if self.vpool_type_name in LOCAL_VPOOL_TYPES:
            self.fill_out_custom_field('dropdown-button-mtpt-bfs', self.vpool_bfs_mp)
        if general_hypervisor.get_hypervisor_type().lower() != "kvm":
            self.choose('dropdown-button-storageip', self.vpool_storage_ip)
        self.click_on('Next', retries=100)

        if self.wait_for_visible_element_by_id('configCinder', 5):
            self.fill_out('inputcinderPassword', "rooter")
            self.fill_out('inputcinderCtrlIP', general.get_local_vsa().ip)

        self.click_on('Next', retries=100)

        self.click_on('Finish', retries=100)

        self.wait_for_wait_notification('Creation of vPool {} finished.'.format(self.vpool_name), retries=300)

        # check vpool is present after adding it
        retries = 100
        link = None
        while retries:
            print "Waiting for vpool"
            try:
                link = self.browser.find_link_by_text(self.vpool_name)
                if link:
                    break
            except NoSuchElementException:
                print self.vpool_name + " not found"
            time.sleep(0.5)
            retries -= 1

        assert retries, "Could not find vpool {} after adding it.".format(self.vpool_name)
        if link:
            link.click()

    def add_gsrs_to_vpool(self, vpool_name):
        self.browse_to(self.get_vpool_url())
        self.wait_for_text(vpool_name)
        time.sleep(2)

        self.click_on_tbl_item(vpool_name)
        self.browser.is_element_present_by_id('management', 15)

        self.click_on_tbl_header('management', retries=30)
        self.wait_for_visible_element_by_id('btn.vpool.management', 15)

        # only deselect = i.e. click when checkbox = selected
        retries = 10
        while retries:
            count = self.check_checkboxes('management')
            if count:
                break
            time.sleep(2)
            count -= 1

        time.sleep(3)
        self.wait_for_visible_element_by_id('buttonVpoolSaveChanges', 15)

        time.sleep(3)
        self.click_on('VpoolSaveChanges', retries=300)

        time.sleep(3)
        self.wait_for_text('Finish', timeout=300)
        self.click_on('Finish')

        self.wait_for_wait_notification('The vPool was added/removed to the selected Storage Routers with success')

    def remove_vpool(self, vpool_name):
        self.browse_to(self.get_vpool_url())
        self.wait_for_text(vpool_name, timeout=30)

        self.click_on_tbl_item(vpool_name)
        self.browser.is_element_present_by_id('management', 5)

        self.click_on_tbl_header('management')
        self.wait_for_visible_element_by_id('btn.vpool.management', 5)

        # only deselect = i.e. click when checkbox = selected
        management = self.browser.find_by_id("management")
        assert management
        management = management[0]

        save_changes_id = "VpoolSaveChanges"
        self.browser.is_element_present_by_id(save_changes_id, wait_time=10)
        self.uncheck_checkboxes(management)
        self.click_on(save_changes_id)

        self.wait_for_text('Finish', timeout=30)
        self.click_on('Finish')

        self.wait_for_wait_notification('The vPool was added/removed to the selected Storage Routers with success',
                                        retries=300)
