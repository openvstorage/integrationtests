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

import urllib2
import urllib
import json
import time

from ci.tests.general.general import test_config


class Connection:
    connection = None

    @staticmethod
    def get_connection(ip='', username='', password='', use_config=True):
        if Connection.connection:
            if (not ip and not username and not password) or Connection.connection.get_ip() == ip:
                return Connection.connection
        else:
            if use_config:
                if not ip:
                    ip = test_config.get('main', 'grid_ip')
                    assert ip, "Please specify a valid ip in autotests.cfg for grid_ip"
                if not username:
                    username = test_config.get('main', 'username')
                if not password:
                    password = test_config.get('main', 'password')
            Connection.connection = Connection(ip, username, password)
        if not Connection.connection.is_authenticated():
            Connection.connection.authenticate()

        return Connection.connection

    def __init__(self, ip='', username='', password=''):
        self.ip = ip
        self.username = username
        self.password = password
        self.token = ''
        self.headers = {'Accept': 'application/json; version=*'}

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
        base_url = 'https://{0}/api/{{0}}'.format(self.get_ip())
        request = urllib2.Request(base_url.format(component + '/'), None, headers=self.headers)
        response = urllib2.urlopen(request).read()
        result = json.loads(response)

        return result['data']

    def fetch(self, component, guid):
        base_url = 'https://{0}/api/{{0}}/'.format(self.get_ip())
        request = urllib2.Request(base_url.format(component + '/' + guid), None, headers=self.headers)
        response = urllib2.urlopen(request).read()
        result = json.loads(response)

        return result

    def add(self, component, data):
        base_url = 'https://{0}/api/{1}/'.format(self.get_ip(), component)
        print 'data: {0}'.format(data)
        request = urllib2.Request(base_url, json.dumps(data), headers=self.headers)
        request.add_header('Content-Type', 'application/json')
        response = urllib2.urlopen(request).read()
        result = json.loads(response)

        return result

    def remove(self, component, guid):
        base_url = 'https://{0}/api/{{0}}/'.format(self.get_ip())
        request = urllib2.Request(base_url.format(component + '/' + guid), None, headers=self.headers)
        request.get_method = lambda: 'DELETE'
        response = urllib2.urlopen(request).read()
        result = json.loads(response)

        return result

    def execute_action(self, component, guid, action, data):
        base_url = 'https://{0}/api/{1}/{2}/{3}/'.format(self.get_ip(), component, guid, action)
        print 'data: {0}'.format(data)
        request = urllib2.Request(base_url, json.dumps(data), headers=self.headers)
        request.add_header('Content-Type', 'application/json')
        response = urllib2.urlopen(request).read()
        result = json.loads(response)

        return result

    def get_component_by_name(self, module, name):

        return self.get_components_with_attribute(module, 'name', name)

    def get_components_with_attribute(self, module, attribute, value, single=False):
        result = list()
        components = self.list(module)
        for guid in components:
            component = self.fetch(module, guid)
            attr = component[attribute]
            if (type(attr) == list and value in attr) or (type(attr) == unicode and value == attr):
                if result and single:
                    raise RuntimeError('Multiple results found for component: {0}'.format(module))
                result.append(component)

        if result:
            if single:
                return result[0]
            else:
                return result
        else:
            return None

    def get_component_with_attribute(self, module, attribute, value):
        return self.get_components_with_attribute(module, attribute, value, True)

    def get_components(self, module):
        result = list()
        for guid in self.list(module):
            result.append(self.fetch(module, guid))

        return result

    def wait_for_task(self, task_id, timeout=None):
        start = time.time()
        task_metadata = {'ready': False}
        while task_metadata['ready'] is False:
            if timeout is not None and timeout < (time.time() - start):
                raise RuntimeError('Waiting for task {0} has timed out.'.format(task_id))
            task_metadata = self.fetch('tasks', task_id)
            if task_metadata['ready'] is False:
                time.sleep(1)

        return task_metadata['successful'], task_metadata['result']