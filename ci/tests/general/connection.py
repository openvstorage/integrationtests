# Copyright (C) 2016 iNuron NV
#
# This file is part of Open vStorage Open Source Edition (OSE),
# as available from
#
#      http://www.openvstorage.org and
#      http://www.openvstorage.com.
#
# This file is free software; you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License v3 (GNU AGPLv3)
# as published by the Free Software Foundation, in version 3 as it comes
# in the LICENSE.txt file of the Open vStorage OSE distribution.
#
# Open vStorage is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY of any kind.

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
from ci.tests.general.logHandler import LogHandler
from ovs.lib.helpers.toolbox import Toolbox
from requests.packages.urllib3 import disable_warnings
from requests.packages.urllib3.exceptions import InsecurePlatformWarning
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from requests.packages.urllib3.exceptions import SNIMissingWarning


class Connection(object):
    """
    API class
    """
    TOKEN_CACHE_FILENAME = '/tmp/at_token_cache'
    disable_warnings(InsecurePlatformWarning)
    disable_warnings(InsecureRequestWarning)
    disable_warnings(SNIMissingWarning)

    logger = LogHandler.get('backend', name='api-connection')

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
        self.headers = {'Accept': 'application/json; version=2'}
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
            return self.wait_for_task(task_id=task_id, timeout=kwargs.get('timeout'))
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
        try:
            response = urllib2.urlopen(request).read()
        except urllib2.HTTPError, error:
            Connection.logger.error(str(error.read()))
            raise
        task_id = json.loads(response)

        if kwargs.get('wait') is True and re.match(Toolbox.regex_guid, task_id):
            return self.wait_for_task(task_id=task_id, timeout=kwargs.get('timeout'))
        return task_id

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
