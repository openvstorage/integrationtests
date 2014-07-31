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

from browser_chrome import BrowserTest

class VpoolTest(BrowserTest):
    def __init__(self, vpool_name='', vpool_type='', vpool_host='', vpool_port='',
                 vpool_access_key='', vpool_secret_key='', vpool_temp_mp='',
                 vpool_md_mp='', vpool_cache_mp='', vpool_vrouter_port='',
                 vpool_storage_ip='', browser_choice='chrome'):

        self.bt = BrowserTest.__init__(self, username='', password='', url='', browser_choice=browser_choice)
        self.vpool_name = vpool_name
        self.vpool_type = vpool_type
        self.vpool_host = vpool_host
        self.vpool_port = vpool_port
        self.vpool_access_key = vpool_access_key
        self.vpool_secret_key = vpool_secret_key
        self.vpool_temp_mp = vpool_temp_mp
        self.vpool_md_mp = vpool_md_mp
        self.vpool_cache_mp = vpool_cache_mp
        self.vpool_vrouter_port = vpool_vrouter_port
        self.vpool_storage_ip = vpool_storage_ip
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
        return self.get_url() + '/#full/vpools'

    def login_test(self):

        self.login_to(self.url, self.username, self.password)
        self.wait_for_text('dashboard')

    def add_vpool_test(self):
        self.browse_to(self.get_url() + '#full/vpools')
        self.click_on('AddVpool')
        self.wait_for_text('Add new vPool')
        time.sleep(1)
        self.choose('Local FS', self.vpool_type)
        self.fill_out('inputVpoolName', self.vpool_name)
        self.fill_out('inputVpoolHost', self.vpool_host)
        self.fill_out('inputVpoolPort', self.vpool_port)
        self.fill_out('inputVpoolAccessKey', self.vpool_access_key)
        self.fill_out('inputVpoolSecretKey', self.vpool_secret_key)
        time.sleep(2)
        self.click_on('Next')

        # wait for page to load
        time.sleep(2)
        self.fill_out_custom_field('dropdown-button-mtpt-temp', self.vpool_temp_mp)
        self.fill_out_custom_field('dropdown-button-mtpt-md', self.vpool_md_mp)
        self.fill_out_custom_field('dropdown-button-mtpt-cache', self.vpool_cache_mp)
        self.fill_out('gmtptp-vrouterport', self.vpool_vrouter_port)
        self.choose('dropdown-button-storageip', self.vpool_storage_ip)
        self.click_on('Next')

        # wait for page to load
        time.sleep(2)
        self.click_on('Finish')
        print "Finish clicked"

    def add_gsrs_to_vpool_test(self):
        self.browse_to(self.get_url() + '#full/vpools')
        self.wait_for_text(self.vpool_name)
        time.sleep(2)

        self.click_on_tbl_item(self.vpool_name)
        self.wait_for_text('Actions:')

        self.click_on_tbl_header('management')
        self.wait_for_text('serving this')

        # only deselect = i.e. click when checkbox = selected
        self.check_checkboxes('management')
        self.click_on('VpoolSaveChanges')

        self.wait_for_text('finish')
        time.sleep(1)
        self.click_on('Finish')

    def remove_vpool_test(self):
        self.browse_to(self.get_url() + '#full/vpools')
        self.wait_for_text(self.vpool_name)

        time.sleep(2)
        self.click_on_tbl_item(self.vpool_name)
        self.wait_for_text('Actions:')

        self.click_on_tbl_header('management')
        self.wait_for_text('serving this')

        # only deselect = i.e. click when checkbox = selected
        self.uncheck_checkboxes()
        self.click_on('VpoolSaveChanges')

        self.wait_for_text('finish')
        time.sleep(1)
        self.click_on('Finish')
