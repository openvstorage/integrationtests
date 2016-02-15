# Copyright 2014 iNuron NV
#
# Licensed under the Open vStorage Modified Apache License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.openvstorage.org/license
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import datetime
import json
import os
import re
import time
import urllib2
from splinter.browser import Browser
from splinter.driver import webdriver
from splinter.exceptions import ElementDoesNotExist
from selenium.webdriver.common.keys import Keys
from ci.tests.general import general
from ci import autotests


class BrowserOvs:
    BUTTON_TAG = 'button'
    INPUT_TAG = 'input'

    def __init__(self, username='', password='', url='', browser_choice='chrome'):
        if browser_choice not in ['chrome', 'firefox', 'phantomjs', 'zope.testbrowser']:
            browser_choice = 'chrome'

        self.browser = Browser(browser_choice, service_args=['--verbose ', '--webdriver-loglevel=DEBUG',
                                                             '--log-path=/var/log/chromedriver.log'])

        if browser_choice == 'phantomjs':
            self.log("phantomjs")
            phdriver = webdriver.phantomjs.PhantomJS(service_args=['--ignore-ssl-errors=true',
                                                                   '--webdriver-loglevel=DEBUG', '--ssl-protocol=any',
                                                                   '--web-security=false'])
            phdriver.set_script_timeout(60)
            phdriver.set_page_load_timeout(60)
            self.browser.driver = phdriver
            self.browser.wait_time = 20

        time.sleep(3)

        self.browser.driver.set_window_size(1280, 1024)
        self.username = username or autotests.get_username()
        self.password = password or autotests.get_password()
        self.url = url or 'https://{0}/'.format(general.get_local_vsa().ip)

        self.debug = True
        self.screens_location = "/var/tmp"
        self.teardown_done = False
        if not getattr(self, "scr_name", ""):
            self.scr_name = general.get_function_name(1)
        self.log('BrowserOvs initialized')

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

    def get_debug(self):
        return self.debug

    def set_debug(self, on=True):
        assert isinstance(on, bool), 'Debug must be a boolean'
        self.debug = on

    debug = property(get_debug, set_debug)

    def take_screenshot(self, name):
        location = self.screens_location
        timestamp = str(datetime.datetime.fromtimestamp(time.time())).replace(" ", "_").replace(":", "_").replace(".", "_")
        if general.screenshot_dir is not None:
            if general.current_test is not None:
                location = os.path.join(self.screens_location, general.screenshot_dir, general.current_test)
            else:
                location = os.path.join(self.screens_location, general.screenshot_dir)
        screenshot_name = '{0}_{1}_'.format(timestamp, name)
        general.execute_command('mkdir -p {0}'.format(location))
        self.browser.screenshot(os.path.join(location, screenshot_name))

    def setup(self):
        pass

    def teardown(self):
        self.log('Entering BrowserOvs teardown')

        if self.teardown_done:
            self.log("Teardown {} already done".format(id(self)))
            return

        if self.debug:
            scr_name = getattr(self, "scr_name", "")
            self.take_screenshot(scr_name)

        self.browser.quit()
        self.teardown_done = True

        self.log('Browser shutdown complete ...')
        time.sleep(3)

    def log(self, text):
        if self.debug:
            print text

    def get_single_item_by_id(self, identifier, element=None):
        starting_point = element if element else self.browser

        retries = 30
        while retries:
            items = starting_point.find_by_id(identifier)
            total = len(items)
            if total > 1:
                for item in items:
                    self.log('Item: >{0}< - >{1}<'.format(item.text, item.value))
                raise Exception("Found more than one {0}".format(identifier))
            if items[0].visible:
                return items[0]
            retries -= 1
            time.sleep(0.5)

        assert retries, "Couldnt find {0}".format(identifier)

    def get_task_response(self, url):
        self.log(url)
        request = urllib2.Request(self.url)
        base64string = base64.encodestring('%s:%s' % (self.username, self.password)).replace('\n', '')
        request.add_header("Authorization", "Basic %s" % base64string)

        result = urllib2.urlopen(request)
        data = json.load(result)
        self.log('JSON: {0}\n'.format(data))
        self.log(url + 'tasks/')
        request = urllib2.Request(url + 'users/')
        base64string = base64.encodestring('%s:%s' % (self.username, self.password)).replace('\n', '')
        request.add_header("Authorization", "Basic %s" % base64string)
        result = urllib2.urlopen(request)
        data = json.load(result)
        self.log('JSON: {0}'.format(data))
        return data

    def wait_for_wait_notification(self, text, retries=100, fail_on_error=True):
        while retries:
            notifs_all = self.browser.find_by_css("div.ui-pnotify-text")

            notifs = []
            for n in notifs_all:
                try:
                    if text in n.text:
                        notifs.append(n)
                except Exception as ex:
                    self.log("wait_for_wait_notification 2: " + str(ex))

            if notifs:
                self.log("found notif: " + str(notifs[0]))
                return True

            if fail_on_error:
                err_notifs = []
                for n in notifs_all:
                    try:
                        if re.search("error|failed", n.text.lower()):
                            err_notifs.append(n)
                    except Exception as ex:
                        self.log("wait_for_wait_notification 2: " + str(ex))
                if err_notifs:
                    err_msg = err_notifs[0].text
                    raise Exception("Error notification encountered while waiting for '{0}'\n{1}".format(text, err_msg))

            time.sleep(0.1)
            retries -= 1

        assert retries, "Couldnt find notification with text: " + text

    def wait_for_modal(self, should_exist=True):
        modal = self.browser.find_by_css("#my-modal")
        retries = 30

        while retries:
            time.sleep(1)
            modal = self.browser.find_by_css("#my-modal")
            modal = [m for m in modal if m.visible]
            if should_exist and modal:
                modal = modal[0]
                break
            if not should_exist and not modal:
                break
            retries -= 1

        assert retries, "Modal window " + {True: "not found", False: "still present"}[should_exist]

        return modal

    def click_modal_button(self, button_name):
        modal = self.wait_for_modal()
        retries = 10

        button = None
        while retries:
            buttons = modal.find_by_tag("button")
            button = [b for b in buttons if b.text == button_name]
            retries -= 1
            time.sleep(1)
        assert button, "Could not find button {} in modal window".format(button_name)
        button = button[0]
        button.click()
        return button

    def browse_to(self, url, wait_for_title='', retries=20):
        self.browser.visit(url)
        if wait_for_title:
            while (wait_for_title not in self.browser.title.lower()) and retries:
                time.sleep(1)
                retries -= 1
            assert retries

    def choose(self, identifier, value):
        button = None
        divs = self.browser.find_by_tag(self.BUTTON_TAG)
        for d in divs:
            if identifier in d.value and d.visible:
                d.click()
                button = d
                break
        if not button:
            button = self.browser.find_by_id(identifier)
            if len(button):
                button = button[0]
                button.click()
        if button:
            button_clicked = False
            uls = button.find_by_xpath("//ul/li")
            for ul in uls:
                if value in ul.text and ul.visible:
                    ul.click()
                    button_clicked = True
            if not button_clicked:
                self.log("Choose: could not find value {}".format(value))
        else:
            self.log("Choose: couldn't find identifier {}".format(identifier))

    def click_on(self, identifier, retries=5):

        while retries:
            retries -= 1
            time.sleep(0.1)

            if self.debug:
                self.take_screenshot(str(identifier).lower())

            button = None
            try:
                button = self.browser.find_by_id(self.BUTTON_TAG + identifier)[0]
            except ElementDoesNotExist:
                identifier_low = identifier.lower()
                buttons = self.browser.find_by_tag(self.BUTTON_TAG)

                self.log(str([(b.value, b.text) for b in buttons]))

                for b in buttons:
                    if identifier_low in b.text.lower() or identifier_low in b.value.lower():
                        button = b
                        break

            if not (button and button.visible):
                continue

            try:
                button.click()
                return button
            except Exception as ex:
                self.log(str(ex))

        if self.debug:
            self.take_screenshot(str(identifier).lower())

        raise Exception("Could not find {}".format(identifier))

    def click_on_dropdown_item(self, identifier, retries=5):

        while retries:
            retries -= 1
            time.sleep(0.1)

            if self.debug:
                self.take_screenshot(str(identifier).lower())

            button = None
            try:
                button = self.browser.find_by_id(identifier)[0]
            except ElementDoesNotExist:
                identifier_low = identifier.lower()
                buttons = self.browser.find_by_tag(self.BUTTON_TAG)

                self.log(str([(b.value, b.text) for b in buttons]))

                for b in buttons:
                    if identifier_low in b.text.lower() or identifier_low in b.value.lower():
                        button = b
                        break

            if not (button and button.visible):
                continue

            try:
                button.click()
                return button
            except Exception as ex:
                self.log(str(ex))

        if self.debug:
            self.take_screenshot(str(identifier).lower())

        raise Exception("Could not find {}".format(identifier))

    def click_on_tbl_item(self, identifier):
        for item in self.browser.find_by_xpath('//table/tbody/tr/td/a'):
            try:
                item_text = item.text
            except Exception as ex:
                self.log("click_on_tbl_item " + str(ex))
                item_text = ""
            if item_text.lower() == identifier.lower():
                self.log('Clicking on tbl header: {0}'.format(item_text))
                item.click()

    def click_on_tbl_header(self, identifier, retries=10):

        while retries:
            try:
                columns = self.browser.find_by_xpath('//div/ul/li/a')
                for column in columns:
                    if identifier.lower() in column.outer_html.lower():
                        column.click()
                        return column
            except Exception as ex:
                self.log(str(ex))
            retries -= 1
            time.sleep(1)

        return False

    def check_checkboxes(self, identifier=''):
        count = 0
        search = self.browser.find_by_id(identifier) if identifier else self.browser
        for cb in search.find_by_tag(self.INPUT_TAG):
            if not cb.checked and cb.visible:
                cb.check()
                count += 1
        return count

    def fill_out(self, identifier, value, clear_first=False):
        input_field = self.get_single_item_by_id(identifier)
        if input_field.value != str(value):
            self.log('Filling out {0} in {1}'.format(value, identifier))
            if clear_first:
                input_field.fill('')
                input_field.type(Keys.BACKSPACE)
            input_field.click()
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
        if not fields:
            input_group = self.browser.find_by_xpath("//*[@id='{0}']/../..".format(identifier))
            if input_group:
                fields = input_group[0].find_by_tag("input")

        for field in fields:
            field.click()
            self.log('Field found: >{0}< - >{1}<'.format(field.text, field.value))
            field.fill(value)
            self.log('new value: >{0}<'.format(field.value))
            break
        return True

    def login(self, wait=True):
        self.browser.visit(self.url)
        self.browser.is_element_present_by_id('buttonLogin', wait_time=10)
        if self.debug:
            self.log('Login to {0}'.format(self.browser.title))
        self.fill_out('inputUsername', self.username)
        self.fill_out('inputPassword', self.password)
        self.click_on('Login')
        if wait:
            self.browser.is_element_present_by_id('dashboard.panels.storagerouter', wait_time=10)
        self.take_screenshot("after_login")

    def check_invalid_credentials_alert(self):
        alerts = self.browser.find_by_css(".alert-danger")
        alert = [al for al in alerts if al.visible and "ovs:login.invalidcredentials" in al.outer_html]
        assert alert, "Could not find invalid credentials alert"

    def uncheck_checkboxes(self, element=''):
        search = element if element else self.browser
        for cb in search.find_by_tag(self.INPUT_TAG):
            cb.uncheck()

    def wait_for_title(self, title_text, retries):
        while retries:
            if title_text in self.browser.title:
                break
            time.sleep(0.1)
            retries -= 1
        assert retries, "Page title did not change to {}, in due time".format(title_text)

    def wait_for_visible_element_by_id(self, identifier, timeout=10):
        if self.browser.is_element_present_by_id(identifier, timeout):
            element = self.browser.find_by_id(identifier)[0]
            while timeout > 0:
                if element.visible:
                    return True
                time.sleep(1)
                timeout -= 1
        return False

    def wait_for_text(self, text, timeout=5):
        r = self.browser.is_text_present(text, timeout)
        assert r, "Text '{0}' did not appear in due time".format(text)
        time.sleep(1)

    def wait_for_text_to_vanish(self, text, timeout=5):
        r = self.browser.is_text_not_present(text, timeout)
        assert r, "Text '{0}' did not vanish in due time".format(text)
