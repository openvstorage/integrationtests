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
import math
import importlib
import subprocess
from datetime import datetime
from ci.helpers.exceptions import SectionNotFoundError
from ci.helpers.storagerouter import StoragerouterHelper
from ci.helpers.testrailapi import TestrailApi, TestrailCaseType, TestrailResult

TEST_SCENARIO_LOC = "/opt/OpenvStorage/ci/scenarios/"
CONFIG_LOC = "/opt/OpenvStorage/ci/config/setup.json"
TESTTRAIL_LOC = "/opt/OpenvStorage/ci/config/testtrail.json"


def run(scenarios=['ALL'], send_to_testrail=False, fail_on_failed_scenario=False):
    """
    Run single, multiple or all test scenarios

    :param scenarios: run scenarios defined by the test_name, leave empty when ALL test scenarios need to be executed
                      (e.g. ['ci.scenarios.alba.asd_benchmark', 'ci.scenarios.arakoon.collapse'])
    :type scenarios: list
    :param send_to_testrail: send results of test to testrail in a new testplan
    :type send_to_testrail: bool
    :param fail_on_failed_scenario: the run will block all other tests if one scenario would fail
    :type fail_on_failed_scenario: bool
    :returns: results and possible testrail url
    :rtype: tuple
    """

    # grab the tests to execute
    if scenarios == ['ALL']:
        tests = list_tests()
    else:
        complete_scenarios = []
        # check if a scenario is specified with a section
        for scenario in scenarios:
            if len(scenario.split('.')) == 3:
                # a full section needs to be added to the scenarios
                for test in os.listdir("{0}/{1}".format(TEST_SCENARIO_LOC, scenario.split('.')[2])):
                    if test != "__init__.pyc" and test != "__init__.py" and test != "main.py" and test != "main.pyc":
                        # check if the scenario already exists in the tests
                        scenario_fullname = "{0}.{1}".format(scenario, test)
                        if scenario_fullname not in complete_scenarios:
                            complete_scenarios.append(scenario_fullname)
            else:
                # check if the scenario already exists in the tests
                if scenario not in complete_scenarios:
                    complete_scenarios.append(scenario)

        tests = complete_scenarios

    # execute the tests
    results = {}
    blocked = False
    for test in tests:
        module = importlib.import_module('{0}.main'.format(test))

        # check if the tests are not blocked by a previous test
        if not blocked:
            module_result = module.run()
        else:
            module_result = module.run(blocked=True)

        # check if a test has failed, if it has failed check if we should block all other tests
        if hasattr(TestrailResult, module_result['status']):
            if getattr(TestrailResult, module_result['status']) == TestrailResult.FAILED and fail_on_failed_scenario:
                blocked = True
        else:
            raise AttributeError("Attribute `{0}` does not exists as status "
                                 "in TestrailResult".format(module_result['status']))

        results[test] = module_result

    if send_to_testrail:
        plan_url = push_to_testrail(results)
        return results, plan_url

    return results, None


def list_tests():
    """
    Lists all the test scenarios

    :returns: all available test scenarios
    :rtype: list
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


def push_to_testrail(results, config_path=TESTTRAIL_LOC, skip_on_no_results=True):
    """
    Push results to testtrail

    :param config_path: path to testrail config file
    :type config_path: str
    :param results: tests and results of test (e.g {'ci.scenarios.arakoon.collapse': {'status': 'NOK'},
                                                    'ci.scenarios.arakoon.archive': {'status': 'OK'}})
    :type results: dict
    :param skip_on_no_results: set the untested tests on SKIPPED
    :type skip_on_no_results: bool
    :return: Testrail URL to test plan
    :rtype: str
    """

    with open(config_path, "r") as JSON_CONFIG:
            testtrail_config = json.load(JSON_CONFIG)

    # fetch test-name based on environment, environment version & datetime
    test_title = "{0}_{1}_{2}".format(_get_test_name(), _get_ovs_version(), datetime.now())

    # create description based on system settings (hardware & linux distro)
    description = _get_description()

    tapi = TestrailApi(testtrail_config['url'], testtrail_config['username'], testtrail_config['password'])
    project_id = tapi.get_project_by_name(testtrail_config['project'])['id']
    suite_id = tapi.get_suite_by_name(project_id, testtrail_config['suite'])['id']

    # check if test_case & test_section exists in test_suite
    for test_case, test_result in results.iteritems():
        test_name = test_case.split('.')[3]
        test_section = test_case.split('.')[2].title()
        try:
            tapi.get_case_by_name(project_id, suite_id, test_name)
        except Exception:
            # check if section exists
            try:
                section = tapi.get_section_by_name(project_id, suite_id, test_section)
            except Exception:
                raise SectionNotFoundError("Section `{0}` is not available in testrail, "
                                           "please add or correct your mistake.".format(test_section))

            if hasattr(TestrailCaseType, test_result['case_type']):
                case_type_id = tapi.get_case_type_by_name(getattr(TestrailCaseType, test_result['case_type']))['id']
            else:
                raise AttributeError("Attribute `{0}` does not exists as case_type "
                                     "in TestrailCaseType".format(test_result['case_type']))
            # add case to existing section
            tapi.add_case(section_id=section['id'], title=test_name, type_id=case_type_id)

    # add plan
    plan = tapi.add_plan(project_id, test_title, description)
    # link suite to plan
    entry = tapi.add_plan_entry(plan['id'], suite_id, testtrail_config['suite'])

    # add results to test cases
    run_id = entry['runs'][0]['id']
    for test_case, test_result in results.iteritems():
        # check if test exists
        test_name = test_case.split('.')[3]
        test_id = tapi.get_test_by_name(run_id, test_name)['id']

        if hasattr(TestrailResult, test_result['status']):
            test_status_id = getattr(TestrailResult, test_result['status'])
        else:
            raise AttributeError("Attribute `{0}` does not exists as test_status in TestrailResult"
                                 .format(test_result['status']))
        # add results to test cases, if failed add a comment with errors
        if getattr(TestrailResult, test_result['status']) == TestrailResult.FAILED:
            tapi.add_result(test_id, test_status_id, comment=str(test_result['errors']))
        else:
            tapi.add_result(test_id, test_status_id)

    # end of adding results to testplan, setting other cases in SKIPPED
    if skip_on_no_results:
        for test in tapi.get_tests(run_id):
            if test['status_id'] == TestrailResult.UNTESTED:
                tapi.add_result(test['id'], int(TestrailResult.SKIPPED))

    return plan['url']


def _get_package_info():
    """
    Retrieve package information for installation

    :returns: package information of openvstorage, volumedriver, alba, arakoon & python-celery
    :rtype: str
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

    :returns: a structured environment based test name
    :rtype: str
    """
    number_of_nodes = len(StoragerouterHelper.get_storagerouter_ips())
    split_ip = StoragerouterHelper.get_local_storagerouter().ip.split('.')
    return str(number_of_nodes) + 'N-' + split_ip[2] + '.' + split_ip[3]


def _get_ovs_version():
    """
    Retrieve version of ovs installation

    :returns: openvstorage package version
    :rtype: str
    """
    packages = _get_package_info()
    main_pkg = [pck for pck in packages.splitlines() if "openvstorage " in pck]
    if not main_pkg:
        return ""

    return re.split("\s*", main_pkg[0])[1]


def _get_description():
    """
    Retrieve extensive information about the machine

    :returns: a extensive description of the local machine
    :rtype: str
    """
    description = ""

    # fetch ip information
    description += "# IP INFO \n"
    for ip in StoragerouterHelper.get_storagerouter_ips():
        description += "* {0}\n".format(ip)

    description += "\n"

    # hypervisor information
    with open(CONFIG_LOC, "r") as JSON_CONFIG:
            ci_config = json.load(JSON_CONFIG)
    description += "# HYPERVISOR INFO \n{0}\n".format(ci_config['ci']['hypervisor'])

    description += "\n"

    # fetch hardware information
    description += "# HARDWARE INFO \n"

    # board information
    description += "### Base Board Information \n"
    output = subprocess.check_output("dmidecode -t 2", shell=True).replace("#", "")
    description += "{0}\n".format(output)

    description += "\n"

    # fetch cpu information
    description += "### Processor Information \n"
    output = subprocess.Popen("grep 'model name'", stdin=
                              subprocess.Popen("cat /proc/cpuinfo", stdout=subprocess.PIPE, shell=True).stdout,
                              stdout=subprocess.PIPE, shell=True)
    cpus = subprocess.check_output("cut -d ':' -f 2", stdin=output.stdout, shell=True).strip().split('\n')
    description += "* Type: {0} \n".format(cpus[0])
    description += "* Amount: {0} \n".format(len(cpus))

    description += "\n"

    # fetch memory information
    description += "### Memory Information \n"
    output = math.ceil(float(subprocess.check_output("grep MemTotal", stdin=
                                                     subprocess.Popen("cat /proc/meminfo", stdout=subprocess.PIPE,
                                                                      shell=True)
                                                     .stdout, shell=True).strip().split()[1]) / 1024 / 1024)
    description += "* {0}GiB System Memory\n".format(int(output))

    description += "\n"

    # fetch disk information
    description += "### Disk Information \n"
    output = subprocess.check_output("lsblk", shell=True)
    description += output

    description += "\n"

    # package info
    description += "# PACKAGE INFO \n"
    description += "{0}\n".format(_get_package_info())

    return description
