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
from ci.helpers.system import SystemHelper
from ovs.log.log_handler import LogHandler
from ci.helpers.exceptions import SectionNotFoundError
from ci.helpers.storagerouter import StoragerouterHelper
from ci.helpers.testrailapi import TestrailApi, TestrailCaseType, TestrailResult

LOGGER = LogHandler.get(source='autotests', name="ci_autotests")
TEST_SCENARIO_LOC = "/opt/OpenvStorage/ci/scenarios/"
CONFIG_LOC = "/opt/OpenvStorage/ci/config/setup.json"
TESTTRAIL_LOC = "/opt/OpenvStorage/ci/config/testrail.json"
EXCLUDE_FLAG = "-exclude"


def run(scenarios=['ALL'], send_to_testrail=False, fail_on_failed_scenario=False, only_add_given_results=True,
        exclude_scenarios=[]):
    """
    Run single, multiple or all test scenarios

    :param scenarios: run scenarios defined by the test_name, leave empty when ALL test scenarios need to be executed
                      (e.g. ['ci.scenarios.alba.asd_benchmark', 'ci.scenarios.arakoon.collapse'])
    :type scenarios: list
    :param exclude_scenarios: exclude scenarios defined by the test_name
                              (e.g. when scenarios=['ALL'] is specified, you can exclude some tests)
    :type scenarios: list
    :param send_to_testrail: send results of test to testrail in a new testplan
    :type send_to_testrail: bool
    :param fail_on_failed_scenario: the run will block all other tests if one scenario would fail
    :type fail_on_failed_scenario: bool
    :param only_add_given_results: ONLY ADD the given cases in results
    :type only_add_given_results: bool
    :returns: results and possible testrail url
    :rtype: tuple
    """

    # grab the tests to execute
    LOGGER.info("Collecting tests ...")
    # filter out tests with EXCLUDE_FLAG
    tests = [autotest for autotest in list_tests(scenarios) if autotest not in exclude_scenarios]
    # print tests to be executed
    LOGGER.info("Executing the following tests: {0}".format(tests))
    # execute the tests
    LOGGER.info("Starting tests ...")
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
                if 'blocking' not in module_result:
                    # if a test reports failed but blocked is not present = by default blocked == True
                    blocked = True
                elif module_result['blocking'] is not False:
                    # if a test reports failed but blocked != False
                    blocked = True
        else:
            raise AttributeError("Attribute `{0}` does not exists as status "
                                 "in TestrailResult".format(module_result['status']))

        # add test to results & also remove possible EXCLUDE_FLAGS on test name
        results[test.replace(EXCLUDE_FLAG, '')] = module_result

    LOGGER.info("Start pushing tests to testrail ...")
    if send_to_testrail:
        plan_url = push_to_testrail(results, only_add_given_cases=only_add_given_results)
        return results, plan_url

    LOGGER.info("Finished tests...")
    return results, None


def list_tests(wanted_tests=['ALL'], exclude=EXCLUDE_FLAG):
    """
    Lists the requested test scenarios
    :returns: all available test scenarios
    :rtype: list
    """
    if isinstance(wanted_tests, str):
        wanted_tests = [wanted_tests]
    if not isinstance(wanted_tests, list):
        raise TypeError('Wanted test argument is a {0}, expected a list'.format(type(wanted_tests)))
    LOGGER.info("Listing tests ...")
    if wanted_tests != ['ALL']:
        converted_wanted_tests = [test.replace('.', '/') for test in wanted_tests]
    # collect sections
    scenario_categories = os.listdir(TEST_SCENARIO_LOC)
    # collect tests/scenarios under sections
    scenarios = []
    for scenario_category in scenario_categories:
        category_path = os.path.join(TEST_SCENARIO_LOC, scenario_category)
        if scenario_category == 'example' or not os.path.isdir(category_path):
            continue
        for scenario in os.listdir(category_path):
            if scenario.endswith(exclude) and wanted_tests == ['ALL']:
                continue
            scenario_path = os.path.join(category_path, scenario)
            if os.path.isdir(scenario_path):
                if wanted_tests != ['ALL'] and scenario_path.split('/', 3)[3] not in converted_wanted_tests:
                    continue
                scenarios.append("ci.scenarios.{0}.{1}".format(scenario_category, scenario))
    return scenarios


def push_to_testrail(results, config_path=TESTTRAIL_LOC, skip_on_no_results=True, only_add_given_cases=False):
    """
    Push results to testtrail

    :param config_path: path to testrail config file
    :type config_path: str
    :param results: tests and results of test (e.g {'ci.scenarios.arakoon.collapse': {'status': 'FAILED'},
                                                    'ci.scenarios.arakoon.archive': {'status': 'PASSED'}})
    :type results: dict
    :param skip_on_no_results: set the untested tests on SKIPPED
    :type skip_on_no_results: bool
    :param only_add_given_cases: ONLY ADD the given cases in results
    :type only_add_given_cases: bool
    :return: Testrail URL to test plan
    :rtype: str
    """
    LOGGER.info("Pushing tests to testrail ...")
    with open(config_path, "r") as JSON_CONFIG:
            testtrail_config = json.load(JSON_CONFIG)

    # fetch test-name based on environment, environment version & datetime
    test_title = "{0}_{1}_{2}".format(_get_test_name(), _get_ovs_version(), datetime.now())

    # create description based on system settings (hardware & linux distro)
    description = _get_description()

    # setup testrail api connection
    if not testtrail_config['url']:
        raise RuntimeError("Invalid url for testrail")

    if not testtrail_config['key']:
        # no key provided so we will continue with username & password
        if not testtrail_config['username'] and testtrail_config['password']:
            raise RuntimeError("Invalid username or password specified for testrail")
        else:
            tapi = TestrailApi(server=testtrail_config['url'], user=testtrail_config['username'],
                               password=testtrail_config['password'])
    else:
        tapi = TestrailApi(testtrail_config['url'], key=testtrail_config['key'])

    project_id = tapi.get_project_by_name(testtrail_config['project'])['id']
    suite_id = tapi.get_suite_by_name(project_id, testtrail_config['suite'])['id']

    # check if test_case & test_section exists in test_suite
    for test_case, test_result in results.iteritems():
        test_name = test_case.split('.')[3]
        test_section = SystemHelper.upper_case_first_letter(test_case.split('.')[2])
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

    if not only_add_given_cases:
        # add all tests to the test_suite, regardless of execution
        entry = tapi.add_plan_entry(plan['id'], suite_id, testtrail_config['suite'])
    else:
        # collect case_ids of executed tests
        executed_case_ids = []
        for test_case in results.iterkeys():
            section_id = tapi.get_section_by_name(project_id, suite_id,
                                                  SystemHelper.upper_case_first_letter(test_case.split('.')[2])
                                                  .strip())['id']
            executed_case_ids.append(tapi.get_case_by_name(project_id=project_id, suite_id=suite_id,
                                                           name=test_case.split('.')[3], section_id=section_id)['id'])
        # only add tests to test_suite that have been executed
        entry = tapi.add_plan_entry(plan['id'], suite_id, testtrail_config['suite'], case_ids=executed_case_ids,
                                    include_all=False)

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
        # add results to test cases, if the've got something in the field `errors`
        if test_result['errors'] is not None:
            tapi.add_result(test_id, test_status_id, comment=str(test_result['errors']))
        else:
            tapi.add_result(test_id, test_status_id)

    # end of adding results to testplan, setting other cases in SKIPPED
    if skip_on_no_results:
        for test in tapi.get_tests(run_id):
            if test['status_id'] == TestrailResult.UNTESTED:
                tapi.add_result(test['id'], int(TestrailResult.SKIPPED))

    LOGGER.info("Finished pushing tests to testrail ...")
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
    description_lines = []
    # fetch ip information
    description_lines.append('# IP INFO')
    for ip in StoragerouterHelper.get_storagerouter_ips():
        description_lines.append('* {0}'.format(ip))
    description_lines.append('')  # New line gap
    # hypervisor information
    with open(CONFIG_LOC, "r") as JSON_CONFIG:
            ci_config = json.load(JSON_CONFIG)
    description_lines.append('# HYPERVISOR INFO')
    description_lines.append('{0}'.format(ci_config['ci']['hypervisor']))
    description_lines.append('')  # New line gap
    # fetch hardware information
    description_lines.append("# HARDWARE INFO")
    # board information
    description_lines.append("### Base Board Information")
    description_lines.append("{0}".format(subprocess.check_output("dmidecode -t 2", shell=True).replace("#", "").strip()))
    description_lines.append('')  # New line gap
    # fetch cpu information
    description_lines.append("### Processor Information")
    output = subprocess.Popen("grep 'model name'", stdin=subprocess.Popen("cat /proc/cpuinfo", stdout=subprocess.PIPE, shell=True).stdout, stdout=subprocess.PIPE, shell=True)
    cpus = subprocess.check_output("cut -d ':' -f 2", stdin=output.stdout, shell=True).strip().split('\n')
    description_lines.append("* Type: {0}".format(cpus[0]))
    description_lines.append("* Amount: {0}".format(len(cpus)))
    description_lines.append('')  # New line gap
    # fetch memory information
    description_lines.append("### Memory Information")
    output = math.ceil(float(subprocess.check_output("grep MemTotal", stdin=subprocess.Popen("cat /proc/meminfo", stdout=subprocess.PIPE, shell=True).stdout, shell=True).strip().split()[1]) / 1024 / 1024)
    description_lines.append("* {0}GiB System Memory".format(int(output)))
    description_lines.append('')  # New line gap
    # fetch disk information
    description_lines.append("### Disk Information")
    output = subprocess.check_output("lsblk", shell=True)
    description_lines.append(output.strip())
    description_lines.append('')  # New line gap
    # package info
    description_lines.append("# PACKAGE INFO")
    description_lines.append("{0}".format(_get_package_info()))

    return '\n'.join(description_lines)
