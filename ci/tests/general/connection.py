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

import urllib2
import urllib
import json
import os
import time
from ci.tests.general import general


class Connection:
    connection = None
    TOKEN_CACHE_FILENAME = '/tmp/at_token_cache'

    @staticmethod
    def get_connection(ip='', username='', password='', use_config=True):
        if Connection.connection:
            if (not ip and not username and not password) or Connection.connection.get_ip() == ip:
                return Connection.connection
        else:
            if use_config:
                if not ip:
                    ip = general.get_config().get('main', 'grid_ip')
                    assert ip, "Please specify a valid ip in autotests.cfg for grid_ip"
                if not username:
                    username = general.get_config().get('main', 'username')
                    assert username, "Please specify a valid username in autotests.cfg"
                if not password:
                    password = general.get_config().get('main', 'password')
                    assert password, "Please specify a valid password in autotests.cfg"
            Connection.connection = Connection(ip, username, password)

        if not Connection.connection.is_authenticated():
            Connection.connection.authenticate()

        return Connection.connection

    def __init__(self, ip='', username='', password=''):
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

    def get_ip(self):
        return self.ip

    def set_ip(self, ip):
        assert isinstance(ip, str), 'IP address must be a string'
        self.ip = ip

    ip = property(get_ip, set_ip)

    def is_authenticated(self):
        return 'Authorization' in self.headers.keys()

    def authenticate(self):
        if 'Authorization' in self.headers.keys():
            self.headers.pop('Authorization')

        auth_url = 'https://{0}/api/oauth2/token/'.format(self.get_ip())

        request = urllib2.Request(auth_url,
                                  data=urllib.urlencode({'grant_type': 'password',
                                                         'username': self.get_username(),
                                                         'password': self.get_password()}),
                                  headers=self.headers)
        response = urllib2.urlopen(request).read()

        self.token = json.loads(response)['access_token']
        self.headers['Authorization'] = 'Bearer {0}'.format(self.token)
        with open(self.TOKEN_CACHE_FILENAME, 'w') as token_cache_file:
            token_cache_file.write(self.token)

    def get_active_tasks(self):
        base_url = 'https://{0}/api/{{0}}'.format(self.get_ip())
        request = urllib2.Request(base_url.format('tasks/'), None, headers=self.headers)
        response = urllib2.urlopen(request).read()

        all_tasks = json.loads(response)
        tasks = list()
        tasks.extend(x for x in all_tasks['active'].values() if x)
        tasks.extend(x for x in all_tasks['scheduled'].values() if x)
        tasks.extend(x for x in all_tasks['reserved'].values() if x)

        return tasks

    def list(self, component):
        base_url = 'https://{0}/api/{1}/'.format(self.get_ip(), component)
        request = urllib2.Request(base_url, None, headers=self.headers)
        response = urllib2.urlopen(request).read()
        return json.loads(response)['data']

    def fetch(self, component, guid):
        base_url = 'https://{0}/api/{1}/{2}/'.format(self.get_ip(), component, guid)
        request = urllib2.Request(base_url, None, headers=self.headers)
        response = urllib2.urlopen(request).read()
        return json.loads(response)

    def add(self, component, data):
        base_url = 'https://{0}/api/{1}/'.format(self.get_ip(), component)
        request = urllib2.Request(base_url, json.dumps(data), headers=self.headers)
        request.add_header('Content-Type', 'application/json')
        response = urllib2.urlopen(request).read()
        return json.loads(response)

    def get(self, component, guid, action):
        base_url = 'https://{0}/api/{1}/{2}/{3}/'.format(self.get_ip(), component, guid, action)
        request = urllib2.Request(base_url, None, headers=self.headers)
        response = urllib2.urlopen(request).read()
        return json.loads(response)

    def remove(self, component, guid):
        base_url = 'https://{0}/api/{1}/{2}/'.format(self.get_ip(), component, guid)
        request = urllib2.Request(base_url, None, headers=self.headers)
        request.get_method = lambda: 'DELETE'
        response = urllib2.urlopen(request).read()
        return json.loads(response) if response else ''

    def execute_action(self, component, guid, action, data):
        """
        Execute a POST action
        :param component: Component (eg: vpools, storagerouters, ...)
        :param guid: Guid of the component to execute an action on
        :param action: Action to perform (eg: add_vpool)
        :param data: Data required for the POST action
        :return: Celery task ID
        """
        base_url = 'https://{0}/api/{1}/{2}/{3}/'.format(self.get_ip(), component, guid, action)
        request = urllib2.Request(base_url, json.dumps(data), headers=self.headers)
        request.add_header('Content-Type', 'application/json')
        response = urllib2.urlopen(request).read()
        return json.loads(response)

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

    def get_components(self, module):
        result = list()
        for guid in self.list(module):
            result.append(self.fetch(module, guid))

        return result

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
