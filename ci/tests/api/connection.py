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


import urllib2
import urllib
import json


class Connection:
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

    def authenticate(self):
        if self.headers in 'Authorization':
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
        base_url = 'https://{0}/api/customer/{{0}}'.format(self.get_ip())
        request = urllib2.Request(base_url.format('tasks/'), None, headers=self.headers)
        response = urllib2.urlopen(request).read()

        all_tasks = json.loads(response)
        tasks = list()
        tasks.extend(x for x in all_tasks['active'].values() if x)
        tasks.extend(x for x in all_tasks['scheduled'].values() if x)
        tasks.extend(x for x in all_tasks['reserved'].values() if x)

        return tasks
