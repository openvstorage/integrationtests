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

"""
Connection class
"""

import os
import re
import json
import time
import urllib
import urllib2
from ci.tests.general.general import General
from ovs.lib.helpers.toolbox import Toolbox


class Connection(object):
    """
    API class
    """
    TOKEN_CACHE_FILENAME = '/tmp/at_token_cache'

    def __init__(self, ip=None, username=None, password=None):
        if ip is None:
            ip = General.get_config().get('main', 'grid_ip')
            assert ip, "Please specify a valid ip in autotests.cfg for grid_ip"
        if username is None:
            username = General.get_config().get('main', 'username')
            assert username, "Please specify a valid username in autotests.cfg"
        if password is None:
            password = General.get_config().get('main', 'password')
            assert password, "Please specify a valid password in autotests.cfg"

        self.ip = ip
        self.username = username
        self.password = password
        self.headers = {'Accept': 'application/json; version=*'}
        if os.path.exists(self.TOKEN_CACHE_FILENAME) \
                and (time.time() - os.path.getmtime(self.TOKEN_CACHE_FILENAME) > 3600.0):
            os.remove(self.TOKEN_CACHE_FILENAME)
        if os.path.exists(self.TOKEN_CACHE_FILENAME):
            with open(self.TOKEN_CACHE_FILENAME, 'r') as token_cache_file:
                self.token = token_cache_file.read()
                self.headers['Authorization'] = 'Bearer {0}'.format(self.token)
        else:
            self.token = ''
            self.authenticate()

        if 'Authorization' not in self.headers.keys():
            self.authenticate()

    def authenticate(self):
        """
        Authenticates the connections
        :return: None
        """
        if 'Authorization' in self.headers.keys():
            self.headers.pop('Authorization')

        auth_url = 'https://{0}/api/oauth2/token/'.format(self.ip)

        request = urllib2.Request(auth_url,
                                  data=urllib.urlencode({'grant_type': 'password',
                                                         'username': self.username,
                                                         'password': self.password}),
                                  headers=self.headers)
        response = urllib2.urlopen(request).read()

        self.token = json.loads(response)['access_token']
        self.headers['Authorization'] = 'Bearer {0}'.format(self.token)
        with open(self.TOKEN_CACHE_FILENAME, 'w') as token_cache_file:
            token_cache_file.write(self.token)

    def list(self, component):
        """
        List all components
        :param component: Component to list
        :return: List of component guids
        """
        base_url = 'https://{0}/api/{1}/'.format(self.ip, component)
        request = urllib2.Request(base_url, None, headers=self.headers)
        response = urllib2.urlopen(request).read()
        return json.loads(response)['data']

    def fetch(self, component, guid):
        """
        Retrieve information about specific component
        :param component: Component type to retrieve
        :param guid: Guid of the component
        :return: Information about component
        """
        base_url = 'https://{0}/api/{1}/{2}/'.format(self.ip, component, guid)
        request = urllib2.Request(base_url, None, headers=self.headers)
        response = urllib2.urlopen(request).read()
        return json.loads(response)

    def add(self, component, data):
        """
        Add a new component
        :param component: Component type to add
        :param data: Data for the new component
        :return: The new component
        """
        base_url = 'https://{0}/api/{1}/'.format(self.ip, component)
        request = urllib2.Request(base_url, json.dumps(data), headers=self.headers)
        request.add_header('Content-Type', 'application/json')
        response = urllib2.urlopen(request).read()
        return json.loads(response)

    def remove(self, component, guid):
        """
        Remove a component
        :param component: Component type to remove
        :param guid: Guid of the component
        :return: None
        """
        base_url = 'https://{0}/api/{1}/{2}/'.format(self.ip, component, guid)
        request = urllib2.Request(base_url, None, headers=self.headers)
        request.get_method = lambda: 'DELETE'
        response = urllib2.urlopen(request).read()
        return json.loads(response) if response else ''

    def execute_get_action(self, component, guid, action, **kwargs):
        """
        Execute a GET action ((Can be determined by the @link() decorator in the API classes)
        :param component: Component to execute an action on
        :param guid: Guid of the component
        :param action: Action to perform
        :return: Output of the action
        """
        base_url = 'https://{0}/api/{1}/{2}/{3}/'.format(self.ip, component, guid, action)
        request = urllib2.Request(base_url, None, headers=self.headers)
        response = urllib2.urlopen(request).read()
        task_id = json.loads(response)

        if kwargs.get('wait') is True and re.match(Toolbox.regex_guid, task_id):
            self.wait_for_task(task_id=task_id, timeout=kwargs.get('timeout'))
        return task_id

    def execute_post_action(self, component, guid, action, data, **kwargs):
        """
        Execute a POST action (Can be determined by the @action() decorator in the API classes)
        :param component: Component (eg: vpools, storagerouters, ...)
        :param guid: Guid of the component to execute an action on
        :param action: Action to perform (eg: add_vpool)
        :param data: Data required for the POST action
        :return: Celery task ID
        """
        base_url = 'https://{0}/api/{1}/{2}/{3}/'.format(self.ip, component, guid, action)
        request = urllib2.Request(base_url, json.dumps(data), headers=self.headers)
        request.add_header('Content-Type', 'application/json')
        response = urllib2.urlopen(request).read()
        task_id = json.loads(response)

        if kwargs.get('wait') is True and re.match(Toolbox.regex_guid, task_id):
            return self.wait_for_task(task_id=task_id, timeout=kwargs.get('timeout'))
        return task_id

    def get_component_by_name(self, component, name, single=False):
        """
        Retrieve a component based on its 'name' field
        :param component: Component type to retrieve
        :param name: Name of the component
        :param single: Expect only 1 return value
        :return: Information about the component
        """
        return self.get_components_with_attribute(component, 'name', name, single)

    def get_components_with_attribute(self, component, attribute, value, single=False):
        """
        Retrieve component information based on a certain attribute
        :param component: Component type to retrieve
        :param attribute: Attribute to compare
        :param value: Value of the attribute
        :param single: Expect only 1 return value
        :return: Information about the retrieved components
        """
        result = []
        for guid in self.list(component):
            component = self.fetch(component, guid)
            attr = component.get(attribute)
            if attr is not None and ((type(attr) == list and value in attr) or (type(attr) == unicode and value == attr)):
                if result and single is True:
                    raise RuntimeError('Multiple results found for component: {0}'.format(component))
                result.append(component)

        if result:
            return result[0] if single is True else result

    def get_components(self, component):
        """
        Retrieve component information
        :param component: Component type to retrieve
        :return: List of components
        """
        return [self.fetch(component, guid) for guid in self.list(component)]

    def wait_for_task(self, task_id, timeout=None):
        """
        Wait for a celery task to end
        :param task_id: Celery task ID to wait for
        :param timeout: Maximum time in seconds to wait for the task to return
        :return: Tuple containing a boolean if the task was successful or not and the result of the task
        """
        start = time.time()
        task_metadata = {'ready': False}
        while task_metadata['ready'] is False:
            if timeout is not None and timeout < (time.time() - start):
                raise RuntimeError('Waiting for task {0} has timed out.'.format(task_id))
            task_metadata = self.fetch('tasks', task_id)
            if task_metadata['ready'] is False:
                time.sleep(1)

        return task_metadata['successful'], task_metadata['result']
