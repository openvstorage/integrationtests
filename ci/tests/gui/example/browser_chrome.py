# Copyright 2014 iNuron NV
#
# Licensed under the Open vStorage Non-Commercial License, Version 1.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.openvstorage.org/OVS_NON_COMMERCIAL
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import time

from splinter.browser import Browser
from splinter.exceptions import ElementDoesNotExist
from selenium.webdriver.common.keys import Keys


class BrowserTest():
    BUTTON_TAG = 'button'
    CHECKBOX_TAG = 'checkbox'
    INPUT_TAG = 'input'

    def __init__(self, username='', password='', url='', browser_choice='chrome'):
        if not browser_choice in ['chrome', 'firefox']:
            browser_choice = 'chrome'

        self.browser = Browser(browser_choice)

        self.username = username
        self.password = password
        self.url = url
        self.debug = False
        print 'BrowserTest initialized'

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
        self.debug = on

    debug = property('', set_debug)

    def setup(self):
        pass

    def teardown(self):
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

    def browse_to(self, url, wait_for_title=''):
        self.browser.visit(url)
        if wait_for_title:
            while not wait_for_title in self.browser.title.lower():
                time.sleep(1)

    def choose(self, identifier, value):
        button = self.browser.find_by_id(identifier)
        if button:
            button = button[0]
            button.click()
        elif not button:
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
            input_field.fill('')
            input_field.type(Keys.BACKSPACE)
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
        print url
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
