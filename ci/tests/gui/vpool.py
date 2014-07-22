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

from browser_ovs          import BrowserOvs
from ci                   import autotests
from ci.tests.general     import general, general_hypervisor
from ci.tests.api         import connection
from nose.plugins.skip    import SkipTest

from splinter.driver.webdriver import NoSuchElementException

REMOTE_VPOOL_TYPES = ['Ceph S3', 'S3 compatible', 'Swift S3']

class Vpool(BrowserOvs):
    def __init__(self,
                 vpool_name         = '',
                 vpool_type         = '',
                 vpool_host         = '',
                 vpool_port         = '',
                 vpool_access_key   = '',
                 vpool_secret_key   = '',
                 vpool_temp_mp      = '',
                 vpool_md_mp        = '',
                 vpool_cache_mp     = '',
                 vpool_bfs_mp       = '',
                 vpool_vrouter_port = '',
                 vpool_storage_ip   = '',
                 browser_choice     = 'chrome' ):

        self.bt = BrowserOvs.__init__(self, browser_choice = browser_choice)

        cfg = autotests._getConfigIni()

        self.vpool_name             = vpool_name         or cfg.get("vpool", "vpool_name")
        self.vpool_type             = vpool_type         or cfg.get("vpool", "vpool_type")
        self.vpool_host             = vpool_host         or cfg.get("vpool", "vpool_host")
        self.vpool_port             = vpool_port         or cfg.get("vpool", "vpool_port")
        self.vpool_access_key       = vpool_access_key   or cfg.get("vpool", "vpool_access_key")
        self.vpool_secret_key       = vpool_secret_key   or cfg.get("vpool", "vpool_secret_key")
        self.vpool_temp_mp          = vpool_temp_mp      or cfg.get("vpool", "vpool_temp_mp")
        self.vpool_md_mp            = vpool_md_mp        or cfg.get("vpool", "vpool_md_mp")
        self.vpool_cache_mp         = vpool_cache_mp     or cfg.get("vpool", "vpool_cache_mp")
        self.vpool_bfs_mp           = vpool_bfs_mp
        if self.vpool_type in ["Local FS"]:
            self.vpool_bfs_mp       = vpool_bfs_mp       or cfg.get("vpool", "vpool_bfs_mp")
        self.vpool_vrouter_port     = vpool_vrouter_port or cfg.get("vpool", "vpool_vrouter_port")
        self.vpool_storage_ip       = vpool_storage_ip   or cfg.get("vpool", "vpool_storage_ip")

        for e in ["vpool_name", "vpool_type", "vpool_temp_mp", "vpool_md_mp", "vpool_cache_mp", "vpool_vrouter_port", "vpool_storage_ip"]:
            if not getattr(self, e):
                raise SkipTest(e)

        print 'VpoolTest initialized'

    def get_vpool_name(self):
        return self.vpool_name

    def set_vpool_name(self, vpool_name):
        assert isinstance(vpool_name, str), 'Vpool name must be a string'
        self.vpool_name = vpool_name

    vpool_name = property(get_vpool_name, set_vpool_name)

    def get_vpool_type(self):
        return self.vpool_type

    def set_vpool_type(self, vpool_type):
        assert isinstance(vpool_type, str), 'Vpool type must be a string'
        self.vpool_type = vpool_type

    vpool_type = property(get_vpool_type, set_vpool_type)

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


    def get_vpool_cache_mp(self):
        return self.vpool_cache_mp

    def set_vpool_cache_mp(self, vpool_cache_mp):
        assert isinstance(vpool_cache_mp, str), 'Vpool cache mountpoint must be a string'
        self.vpool_cache_mp = vpool_cache_mp

    vpool_cache_mp = property(get_vpool_cache_mp, set_vpool_cache_mp)

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

    def add_vpool(self):
        self.browse_to(self.get_url() + '#full/vpools', 'vpools')
        self.click_on('AddVpool')
        self.wait_for_text('Add new vPool')
        time.sleep(2)
        self.choose('Local FS', self.vpool_type)
        self.fill_out('inputVpoolName', self.vpool_name)

        if self.vpool_type in REMOTE_VPOOL_TYPES:
            self.fill_out('inputVpoolHost', self.vpool_host)
            self.fill_out('inputVpoolPort', self.vpool_port, clear_first = True)
            self.fill_out('inputVpoolAccessKey', self.vpool_access_key)
            self.fill_out('inputVpoolSecretKey', self.vpool_secret_key)

        self.click_on('Next', retries = 100)

        # wait for page to load
        self.browser.is_element_present_by_id('dropdown-button-mtpt-temp', 15)
        self.fill_out_custom_field('dropdown-button-mtpt-temp', self.vpool_temp_mp)
        self.fill_out_custom_field('dropdown-button-mtpt-md', self.vpool_md_mp)
        self.fill_out_custom_field('dropdown-button-mtpt-cache', self.vpool_cache_mp)

        if self.vpool_type not in REMOTE_VPOOL_TYPES:
            self.fill_out_custom_field('dropdown-button-mtpt-bfs', self.vpool_bfs_mp)

        self.fill_out('gmtptp-vrouterport', self.vpool_vrouter_port, clear_first = True)
        if general_hypervisor.get_hypervisor_type().lower() != "kvm":
            self.choose('127.0.0.1', self.vpool_storage_ip)
        self.click_on('Next', retries = 100)

        self.click_on('Finish', retries = 100)

        self.wait_for_wait_notification('Creation of vPool {} finished.'.format(self.vpool_name))

        #check vpool is present after adding it
        retries = 100
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

        link.click()

    def add_gsrs_to_vpool(self, vpool_name):
        self.browse_to(self.get_vpool_url())
        self.wait_for_text(vpool_name)
        time.sleep(2)

        self.click_on_tbl_item(vpool_name)
        self.wait_for_text('Actions:')

        self.click_on_tbl_header('management')
        self.wait_for_text('serving this')

        # only deselect = i.e. click when checkbox = selected
        self.check_checkboxes('management')
        self.click_on('VpoolSaveChanges')

        self.wait_for_text('finish')
        self.click_on('Finish')

        #@todo: wait for task to complete
        #self.get_task_response('https://10.100.131.71')

    def remove_vpool(self, vpool_name):
        self.browse_to(self.get_vpool_url())
        self.wait_for_text(vpool_name)

        self.click_on_tbl_item(vpool_name)
        self.wait_for_text('Actions:')

        self.click_on_tbl_header('management')
        self.wait_for_text('serving this')

        # only deselect = i.e. click when checkbox = selected
        management = self.browser.find_by_id("management")
        assert management
        management = management[0]
        self.uncheck_checkboxes(management)
        self.click_on('VpoolSaveChanges')

        self.wait_for_text('Finish')
        self.click_on('Finish')

        self.wait_for_wait_notification('The vPool was added/removed to the selected Storage Routers with success')

        #@todo: wait for task to complete
        #self.get_task_response('https://10.100.131.71')
