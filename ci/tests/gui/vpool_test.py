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

from browser_test import BrowserTest


class VpoolTest(BrowserTest):
    def __init__(self, browser_choice='chrome'):
        BrowserTest.__init__(self, browser_choice)
        # super().__init__(browser_choice)

    def login_test(self):
        self.login_to('https://10.100.131.71/', 'admin', 'admin')
        self.wait_for_text('dashboard')

    def add_vpool_test(self, vpool_name):
        self.browse_to('https://10.100.131.71/#full/vpools')
        self.click_on('AddVpool')
        self.wait_for_text('Add new vPool')
        time.sleep(1)
        self.choose('Local FS', 'Ceph S3')
        self.fill_out('inputVpoolName', vpool_name)
        self.fill_out('inputVpoolHost', '10.100.131.91')
        self.fill_out('inputVpoolPort', '80')
        self.fill_out('inputVpoolAccessKey', '0OMK2V3HQJ4JNDT766UF')
        self.fill_out('inputVpoolSecretKey', 'RCz00qAo+jgRlPLVdXoP1RUZfU5RzjOFRQJBJxyR')
        time.sleep(1)
        self.click_on('Next')

        # wait for page to load
        time.sleep(2)
        self.fill_out_custom_field('dropdown-button-mtpt-temp', '/var/tmp')
        self.fill_out_custom_field('dropdown-button-mtpt-dfs', '/mnt/dfs/' + vpool_name)
        self.fill_out_custom_field('dropdown-button-mtpt-md', '/mnt/md')
        self.fill_out_custom_field('dropdown-button-mtpt-cache', '/mnt/cache')
        self.fill_out('gmtptp-vrouterport', 12323)
        self.choose('127.0.0.1', '172.22.131.10')
        self.click_on('Next')

        # wait for page to load
        time.sleep(2)
        self.click_on('Finish')
        self.get_task_response('https://10.100.131.71')

    def add_gsrs_to_vpool_test(self, vpool_name):
        self.browse_to('https://10.100.131.71/#full/vpools')
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

    def remove_vpool_test(self, vpool_name):
        self.browse_to('https://10.100.131.71/#full/vpools')
        self.wait_for_text(vpool_name)

        self.click_on_tbl_item(vpool_name)
        self.wait_for_text('Actions:')

        self.click_on_tbl_header('management')
        self.wait_for_text('serving this')

        # only deselect = i.e. click when checkbox = selected
        self.uncheck_checkboxes('management')
        self.click_on('VpoolSaveChanges')

        self.wait_for_text('finish')
        self.click_on('Finish')

    def run(self):
        self.setup()
        # self.get_task_response('https://10.100.131.71')
        self.login_test()
        self.add_vpool_test('ceph')
        # #@todo wait for job to complete
        # self.login_test()
        # self.add_gsrs_to_vpool_test('ceph')
        # #@todo wait for job to complete
        # self.remove_vpool_test('ceph')
        # #@todo wait for job to complete
        self.teardown()


if __name__ == "__main__":
    vpt = VpoolTest('chrome')
    vpt.run()
