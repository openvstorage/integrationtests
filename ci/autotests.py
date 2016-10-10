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
OVS automatic test lib
"""


import os
import re
import json
import importlib
import subprocess
from datetime import datetime
from ci.helpers.testrailapi import TestrailApi
from ci.helpers.storagerouter import StoragerouterHelper

TEST_SCENARIO_LOC = "/opt/OpenvStorage/ci/scenarios/"
CONFIG_LOC = "/opt/OpenvStorage/ci/config/setup.json"
TESTTRAIL_LOC = "/opt/OpenvStorage/ci/config/testtrail.json"


def run(scenarios=['ALL']):
    """
    Run single, multiple or all test scenarios

    :param scenarios: run scenarios defined by the test_name, leave empty when ALL test scenarios need to be executed
                      (e.g. ['ci.scenarios.alba.asd_benchmark', 'ci.scenarios.arakoon.collapse'])
    :type scenarios: list
    """

    # grab the tests to execute
    if scenarios == ['ALL']:
        tests = list_tests()
    else:
        tests = scenarios

    # execute the tests
    results = {}
    for test in tests:
        module = importlib.import_module('{0}.main'.format(test))
        module_result = module.run()
        results[test] = module_result
        print module_result

    return


def list_tests():
    """
    Lists all the test scenarios
    """

    # collect sections
    sections = os.listdir(TEST_SCENARIO_LOC)

    # collect tests/scenarios under sections
    scenarios = []
    for section in sections:
        if section != 'example' and section != '__init__.py' and section != '__init__.pyc':
            for scenario in os.listdir("{0}/{1}".format(TEST_SCENARIO_LOC, section)):
                if scenario != '__init__.py' and scenario != 'main.py' \
                        and scenario != '__init__.pyc' and scenario != 'main.pyc':
                    scenarios.append("ci.scenarios.{0}.{1}".format(section, scenario))

    return scenarios


def push_to_testrail(config_path=TESTTRAIL_LOC):
    """
    Push results to testtrail

    :param config_path: path to testrail config file
    :type config_path: str
    :return: Testrail URL
    """

    TESTRAIL_STATUS_ID_PASSED = '1'
    TESTRAIL_STATUS_ID_BLOCKED = '2'
    TESTRAIL_STATUS_ID_FAILED = '5'
    TESTRAIL_STATUS_ID_SKIPPED = '11'
    TESTRAIL_KEY = ""
    TESTRAIL_SERVER = ""

    with open(config_path, "r") as JSON_CONFIG:
            testtrail_config = json.load(JSON_CONFIG)

    # fetch test-name based on environment, environment version & datetime
    test_name = "{0}_{1}_{2}".format(_get_test_name(), _get_ovs_version(), datetime.now())

    tapi = TestrailApi(testtrail_config['url'], testtrail_config['username'], testtrail_config['password'])
    project_id = tapi.get_project_by_name(testtrail_config['project'])['id']
    suite_id = tapi.get_suite_by_name(project_id, testtrail_config['suite'])['id']

    # add plan
    plan = tapi.add_plan(project_id, test_name)
    # link suite to plan
    entry = tapi.add_plan_entry(plan['id'], suite_id, testtrail_config['suite'])



    return


def _get_package_info():
    """
    Retrieve package information for installation
    """
    command = "dpkg-query -W -f='${binary:Package} ${Version}\t${Description}\n' " \
              "| grep '^openvstorage\|^volumedriver\|^alba\|^arakoon\|^python-celery'"

    child_process = subprocess.Popen(command, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)

    (output, _error) = child_process.communicate()
    return output


def _get_test_name():
    """
    Retrieve a structured environment test name
    """
    number_of_nodes = len(StoragerouterHelper.get_storagerouter_ips())
    split_ip = StoragerouterHelper.get_local_storagerouter().ip.split('.')
    return str(number_of_nodes) + 'N-' + split_ip[2] + '.' + split_ip[3]


def _get_ovs_version():
    """
    Retrieve version of ovs installation
    """
    packages = _get_package_info()
    main_pkg = [pck for pck in packages.splitlines() if "openvstorage " in pck]
    if not main_pkg:
        return ""

    return re.split("\s*", main_pkg[0])[1]
