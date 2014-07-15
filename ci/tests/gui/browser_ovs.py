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
import urllib2
import base64
import json

from splinter.browser    import Browser
from splinter.driver     import webdriver
from splinter.exceptions import ElementDoesNotExist

from ci.tests.general    import general
from ci                  import autotests

class BrowserOvs():
    BUTTON_TAG = 'button'
    INPUT_TAG = 'input'

    def __init__(self, username = '', password = '', url = '', browser_choice = 'phantomjs'):
        if not browser_choice in ['chrome', 'firefox', 'phantomjs', 'zope.testbrowser']:
            browser_choice = 'chrome'

        self.browser = Browser(browser_choice)

        if browser_choice == 'phantomjs':
            print "phantomjs"
            phdriver = webdriver.phantomjs.PhantomJS(service_args=['--ignore-ssl-errors=true', '--webdriver-loglevel=DEBUG',   '--ssl-protocol=any', '--web-security=false'])


            phdriver.set_script_timeout(60)
            phdriver.set_page_load_timeout(60)
            self.browser.driver = phdriver
            self.browser.wait_time = 20

        self.browser.driver.set_window_size(1280, 1024)
        self.username = username or autotests.getUserName()
        self.password = password or autotests.getPassword()
        self.url      = url or 'https://{0}/'.format(general.get_local_vsa().ip)

        self.debug = True
        self.screens_location = "/var/tmp"
        print 'BrowserOvs initialized'

    def get_username(self):
        return self.username

    def set_username(self, username):
        assert isinstance(username, str), 'Username must be a string'
        self.username = username

    username = property(get_username, set_username)

    def get_password(self):
        return self.password

    def set_password(self, password):
        assert isinstance(password, str), 'Password must be a string'
        self.password = password

    password = property(get_password, set_password)

    def get_url(self):
        return self.url

    def set_url(self, url):
        assert isinstance(url, str), 'Username must be a string'
        self.url = url

    url = property(get_url, set_url)

    def set_debug(self, on=True):
        assert isinstance(on, bool), 'Debug must be a boolean'
        self.__debug = on

    debug = property('', set_debug)

    def setup(self):
        #@todo: add authentication
        pass
        # password_mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
        # password_mgr.add_password(None, self.url, self.username, self.password)
        #
        # handler = urllib2.HTTPBasicAuthHandler(password_mgr)
        # opener = urllib2.build_opener(handler)
        # opener.open(self.url + '/api/customer')
        # urllib2.install_opener(opener)

    def teardown(self):
        if self.debug:
            self.browser.driver.save_screenshot(os.path.join(self.screens_location, str(time.time()) + ".png"))
        self.browser.quit()
        print 'Browser shutdown complete ...'

    def log(self, text):
        if self.debug:
            print text

    def get_single_item_by_id(self, identifier, element=None):
        starting_point = element if element else self.browser
        items = starting_point.find_by_id(identifier)
        total = len(items)
        if total == 1:
            return items[0]
        else:
            if total == 0:
                self.log('No result found')
            else:
                self.log('Found {0} items:'.format(total))
            for item in items:
                self.log('Item: >{0}< - >{1}<'.format(item.text, item.value))
            raise RuntimeError("Expected only 1 result")

    def get_task_response(self, url, internal=False):

        if internal:
            customer_api = self.url + '/api/internal/'
        else:
            customer_api = self.url + '/api/customer/'

        print url
        request = urllib2.Request(self.url)
        base64string = base64.encodestring('%s:%s' % (self.username, self.password)).replace('\n', '')
        request.add_header("Authorization", "Basic %s" % base64string)

        result = urllib2.urlopen(request)
        data = json.load(result)
        print 'JSON: {0}'.format(data)
        print
        print url + 'tasks/'
        request = urllib2.Request(url + 'users/')
        base64string = base64.encodestring('%s:%s' % (self.username, self.password)).replace('\n', '')
        request.add_header("Authorization", "Basic %s" % base64string)
        result = urllib2.urlopen(request)
        data = json.load(result)
        print 'JSON: {0}'.format(data)
        return data


    def browse_to(self, url, wait_for_title=''):
        self.browser.visit(url)
        if wait_for_title:
            while not wait_for_title in self.browser.title.lower():
                time.sleep(1)

    def choose(self, identifier, value):
        button = None
        divs = self.browser.find_by_tag(self.BUTTON_TAG)
        for d in divs:
            if identifier in d.value and d.visible:
                d.click()
                button = d
                break
        if button:
            uls = button.find_by_xpath("//ul/li")
            for ul in uls:
                if value in ul.text and ul.visible:
                    ul.click()

    def click_on(self, identifier, retries = 1):

        while retries:

            if self.debug:
                self.browser.driver.save_screenshot(os.path.join(self.screens_location, str(identifier) + str(time.time()) + ".png"))

            button = None
            try:
                button = self.browser.find_by_id(self.BUTTON_TAG + identifier)[0]
            except ElementDoesNotExist:
                identifier_low = identifier.lower()
                buttons = self.browser.find_by_tag(self.BUTTON_TAG)

                print [(b.value, b.text) for b in buttons]

                for b in buttons:
                    if identifier_low in b.text.lower() or identifier_low in b.value.lower():
                        button = b
                        break
            if button:
                break
            retries -= 1
            time.sleep(1)

        if self.debug:
            self.browser.driver.save_screenshot(os.path.join(self.screens_location, str(identifier) + str(time.time()) + ".png"))

        assert button, "Could not find {}".format(identifier)
        return button.click() if button else False

    def click_on_tbl_item(self, identifier):
        for item in self.browser.find_by_xpath('//table/tbody/tr/td/a'):
            if item.text.lower() == identifier.lower():
                self.log('Click on tbl header: {0}'.format(item.text))
                item.click()

    def click_on_tbl_header(self, identifier):
        columns = self.browser.find_by_xpath('//div/ul/li/a')
        for column in columns:
            if identifier.lower() in column.outer_html.lower():
                column.click()
                return column
        return False

    def check_checkboxes(self, identifier=''):
        search = self.browser.find_by_id(identifier) if identifier else self.browser
        for cb in search.find_by_tag(self.INPUT_TAG):
            if not cb.checked and cb.visible:
                cb.check()

    def fill_out(self, identifier, value):
        input_field = self.get_single_item_by_id(identifier)
        if input_field.value != str(value):
            self.log('Filling out {0} in {1}'.format(value, identifier))
            input_field.fill(value)
        else:
            self.log('Value {0} already present in {1}'.format(value, identifier))
        return True

    def fill_out_custom_field(self, identifier, value):
        element = self.get_single_item_by_id(identifier)
        self.log('Filling out: {0} with {1}'.format(identifier, value))
        previous_value = element.value
        element.click()
        items = element.find_by_xpath('//ul/li')
        for item in items:
            if item.visible and 'Custom' in item.text:
                self.log('item {0}'.format(item.text))
                previous_value = element.value
                item.click()
                break

        self.log('previous value: >{0}<'.format(previous_value))
        time.sleep(2)
        # reselect element to access custom field
        element = self.get_single_item_by_id(identifier)
        fields = element.find_by_tag('input')
        self.log('Nr of fields found: {0}'.format(len(fields)))
        for field in fields:
            field.click()
            self.log('Field found: >{0}< - >{1}<'.format(field.text, field.value))
            field.fill(value)
            self.log('new value: >{0}<'.format(field.value))
            break
        return True

    def login(self):
        self.browser.visit(self.url)
        if self.debug: print 'Login to {0}'.format(self.browser.title)
        self.fill_out('inputUsername', self.username)
        self.fill_out('inputPassword', self.password)
        self.click_on('Login')
        self.wait_for_text('dashboard')

    def uncheck_checkboxes(self, element=''):
        search = element if element else self.browser
        for cb in search.find_by_tag(self.INPUT_TAG):
            cb.uncheck()

    def wait_for_text(self, text, timeout=5):
        self.browser.is_text_present(text, timeout)
        time.sleep(1)

