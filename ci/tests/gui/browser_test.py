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



import time
import urllib2
import base64
import json

from splinter.browser import Browser
from splinter.exceptions import ElementDoesNotExist


class BrowserTest():
    BUTTON_TAG = 'button'
    INPUT_TAG = 'input'

    def __init__(self, browser_choice='chrome'):
        if not browser_choice in ['chrome', 'firefox']:
            browser_choice = 'chrome'

        self.browser = Browser(browser_choice)
        self.debug = False

    def setup(self):
        username = 'admin'
        password = 'admin'

        password_mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
        top_level_url = 'https://10.100.131.71'
        password_mgr.add_password(None, top_level_url, username, password)

        handler = urllib2.HTTPBasicAuthHandler(password_mgr)
        opener = urllib2.build_opener(handler)
        opener.open(top_level_url + '/api/customer')
        urllib2.install_opener(opener)

    def teardown(self):
        self.browser.quit()

    def set_debug_off(self):
        self.debug = False

    def set_debug_on(self):
        self.debug = True

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
        username = 'admin'
        password = 'admin'

        if internal:
            url = url + '/api/internal/'
        else:
            url = url + '/api/customer/'

        print url
        request = urllib2.Request(url)
        base64string = base64.encodestring('%s:%s' % (username, password)).replace('\n', '')
        request.add_header("Authorization", "Basic %s" % base64string)

        result = urllib2.urlopen(request)
        data = json.load(result)
        print 'JSON: {0}'.format(data)
        print
        print url + 'tasks/'
        request = urllib2.Request(url + 'users/')
        base64string = base64.encodestring('%s:%s' % (username, password)).replace('\n', '')
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
        divs = self.browser.find_by_tag(BrowserTest.BUTTON_TAG)
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

    def click_on(self, identifier):
        button = None
        try:
            button = self.browser.find_by_id(BrowserTest.BUTTON_TAG + identifier)[0]
        except ElementDoesNotExist:
            identifier = identifier.lower()
            buttons = self.browser.find_by_tag(BrowserTest.BUTTON_TAG)
            for button in buttons:
                if identifier in button.text.lower() or identifier in button.value.lower():
                    break

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
        for cb in search.find_by_tag(BrowserTest.INPUT_TAG):
            if not cb.checked and cb.visible:
                cb.check()

    def fill_out(self, identifier, value):
        input_field = self.get_single_item_by_id(identifier)
        if input_field.value != str(value):
            return input_field.fill(value)
        return True

    def fill_out_custom_field(self, identifier, value):
        element = self.get_single_item_by_id(identifier)
        self.log('Filling out: {0}'.format(identifier))
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

    def login_to(self, url, username, password):
        self.browser.visit(url)
        if self.debug: print 'Login to {0}'.format(self.browser.title)
        self.fill_out('inputUsername', username)
        self.fill_out('inputPassword', password)
        self.click_on('Login')

    def uncheck_checkboxes(self, element=''):
        search = element if element else self.browser
        for cb in search.find_by_tag(BrowserTest.INPUT_TAG):
            cb.uncheck()

    def wait_for_text(self, text, timeout=5):
        self.browser.is_text_present(text, timeout)
        time.sleep(1)