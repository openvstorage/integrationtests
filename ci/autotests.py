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
import sys
import nose
import time
import datetime
import StringIO
import subprocess
import ConfigParser
from xml.dom import minidom
from ci.tests.general.general import General
from ci.tests.general.general_storagerouter import GeneralStorageRouter
from ci.scripts import testrailapi, testEnum
from ci.scripts import xunit_testrail

at_config = General.get_config()
TESTRAIL_STATUS_ID_PASSED = '1'
TESTRAIL_STATUS_ID_BLOCKED = '2'
TESTRAIL_STATUS_ID_FAILED = '5'
TESTRAIL_STATUS_ID_SKIPPED = '11'
TESTRAIL_FOLDER = at_config.get(section="main", option="output_folder")
TESTRAIL_KEY = at_config.get(section="testrail", option="key")
TESTRAIL_PROJECT = at_config.get(section="testrail", option="test_project")
TESTRAIL_QUALITYLEVEL = at_config.get(section="main", option="qualitylevel")
TESTRAIL_SERVER = at_config.get(section="testrail", option="server")

BLOCKED_MESSAGE = "BLOCKED"


class TestRunnerOutputFormat(object):
    """
    Enumerator
    """
    CONSOLE = 'CONSOLE'
    XML = 'XML'
    TESTRAIL = 'TESTRAIL'


def run(tests='', output_format=TestRunnerOutputFormat.CONSOLE, output_folder='/var/tmp',
        project_name='Open vStorage Engineering', always_die=False, qualitylevel='', existing_plan_id="",
        interactive=True):
    """
    Run single, multiple or all test cases:
        - single: - string: 'gui'
        - multiple - list: ['gui', 'sanity']
        - all - None value or empty list

    output format:
        - TESTRAIL requires credentials to testrail
        - CONSOLE|XML can be used to run tests locally
    :param tests: Tests to execute
    :param output_format: Format for output  CONSOLE, XML, TESTRAIL
    :param output_folder: Folder where results file will be stored
    :param project_name: Name of testrail project
    :param always_die: Die on 1st test that fails
    :param qualitylevel: Quality level of setup where tests are executed
    :param existing_plan_id: Plan ID for testrail
    :param interactive: Run interactively
    :return: None
    """
    if str(output_format) not in ['CONSOLE', 'XML', 'TESTRAIL']:
        if interactive:
            output_format = _check_input(predicate=lambda x: getattr(TestRunnerOutputFormat, x, False),
                                         msg='Enter output format - [CONSOLE / XML / TESTRAIL]')
        else:
            raise RuntimeError('output_format should be: CONSOLE | XML | TESTRAIL')
        output_format = getattr(TestRunnerOutputFormat, str(output_format))

    if type(always_die) != bool:
        if interactive:
            always_die = eval(_check_input(predicate=lambda x: type(eval(x)) == bool,
                                           msg="Only boolean values allowed for always_die param\n" +
                                               "Do you want the tests to stop after error/failure?[True/False]"))
        else:
            raise RuntimeError('always_die parameter should be a boolean: True|False')

    if interactive:
        if output_format in (TestRunnerOutputFormat.XML, TestRunnerOutputFormat.TESTRAIL) and not output_folder:
            output_folder = _check_input(predicate=lambda x: os.path.exists(x) and os.path.isdir(x),
                                         msg='Incorrect output_folder: {0}'.format(output_folder))
    elif not output_folder or not(os.path.exists(output_folder) and os.path.isdir(output_folder)):
        raise RuntimeError("Output folder incorrect: {0}".format(output_folder))

    version = _get_ovs_version()

    # Default arguments. First argument is a dummy as it is stripped within nose.
    arguments = ['', '--where', General.TESTS_DIR, '--verbosity', '3']
    if always_die is True:
        arguments.append('-x')

    if output_format in (TestRunnerOutputFormat.XML, TestRunnerOutputFormat.TESTRAIL):
        testrail_ip = ''
        testrail_key = ''
        testrail_title = ''
        testrail_project = ''
        testrail_description = ''
        if not output_folder:
            raise AttributeError("No output folder for the {0} result files specified".format(output_format))
        if not os.path.exists(output_folder):
            raise AttributeError("Given output folder doesn't exist. Please create it first!")

        if output_format == TestRunnerOutputFormat.TESTRAIL:
            if not TESTRAIL_SERVER:
                raise AttributeError("No testrail ip specified")
            if not TESTRAIL_KEY:
                raise AttributeError("No testrail key specified")
            if not project_name:
                raise AttributeError("No testrail project name specified")
            if not qualitylevel:
                raise AttributeError("No quality_level specified")
            if not version:
                raise AttributeError("No version specified")

            testrail_ip = TESTRAIL_SERVER
            testrail_key = TESTRAIL_KEY
            env_info = _get_env_info()
            testrail_title = env_info + "__" + version + "__" + qualitylevel + "__" + GeneralStorageRouter.get_hypervisor_type()
            testrail_project = project_name
            testrail_description = _get_description()

        arguments.append('--with-xunit_testrail')
        arguments.append('--xunit_file2')
        arguments.append('/'.join([output_folder, 'test_results{0}.xml'.format(time.time())]))
        arguments.append('--testrail-ip')
        arguments.append(testrail_ip)
        arguments.append('--testrail-key')
        arguments.append(testrail_key)
        arguments.append('--project-name')
        arguments.append(testrail_project)
        arguments.append('--push-name')
        arguments.append(testrail_title)
        arguments.append('--description')
        arguments.append(testrail_description)
        arguments.append('--plan-id')
        arguments.append(existing_plan_id)

    if tests:
        if type(tests) != list:
            tests = [tests]
        tests_to_run = []
        for test_spec in tests:
            test_spec = test_spec.replace(':', '.')
            test_spec_parts = test_spec.split('.')
            if len(test_spec_parts) < 2 or test_spec_parts[0] != 'ci' or test_spec_parts[1] != 'tests':
                raise ValueError('When specifying a testdirectory, testmodule, testclass or testcase, the name needs to start with "ci.tests"')
            if len(test_spec_parts) >= 5 and not test_spec_parts[4].startswith('Test'):
                raise ValueError('Expected a class name starting with "Test"')

            if len(test_spec_parts) >= 5:
                test_spec = '{0}:{1}'.format('.'.join(test_spec_parts[:4]), '.'.join(test_spec_parts[4:]))

            tests_to_run.append(test_spec)

        arguments.append('--tests')
        arguments.append(','.join(tests_to_run))

    nose.run(argv=arguments, addplugins=[xunit_testrail.XunitTestrail()])


def list_tests(args=None, with_plugin=False):
    """
    Lists all the tests that nose detects under TESTS_DIR
    :param args: Extra arguments for listing tests
    :param with_plugin: Use the --with-testEnum plugin
    """
    if not args:
        arguments = ['--where', General.TESTS_DIR, '--verbosity', '3', '--collect-only']
    else:
        arguments = args + ['--collect-only']

    if with_plugin is True:
        arguments.append('--with-testEnum')

        fake_stdout = StringIO.StringIO()
        old_stdout = sys.stdout
        sys.stdout = fake_stdout

        try:
            nose.run(argv=arguments, addplugins=[testEnum.TestEnum()])
        except Exception:
            raise
        finally:
            sys.stdout = old_stdout

        return fake_stdout.getvalue().split()

    testcases = []
    for line in General.execute_command(command='nosetests {0}'.format(' '.join(arguments)))[1].splitlines():
        if line.startswith('ci.tests'):
            testcases.append(line.split(' ... ')[0])
    return testcases


def push_to_testrail(project_name, output_folder, version=None, filename="", milestone="", comment=""):
    """
    Push xml file with test results to Testrail
    :param project_name: Name of testrail project
    :param output_folder: Output folder containing the results in XML format
    :param version: Version
    :param filename: File name of results
    :param milestone: Milestone in testrail
    :param comment: Extra comment
    :return: Testrail URL
    """
    def _get_textual_values(seconds):
        if not seconds:
            return "%2i %5s, %2i %7s, %2i %7s\n" % (0, 'hours', 0, 'minutes', 0, 'seconds')
        hours = seconds / 60 / 60
        rest = seconds % (60 * 60)
        minutes = rest / 60
        rest %= 60
        hours_text = 'hour' if hours == 1 else 'hours'
        minutes_text = 'minute' if minutes == 1 else 'minutes'
        seconds_text = 'second' if rest == 1 else 'seconds'
        return "%2i %5s, %2i %7s, %2i %7s\n" % (hours, hours_text, minutes, minutes_text, rest, seconds_text)

    if not filename:
        if not (os.path.exists(output_folder) and os.path.isdir(output_folder)):
            output_folder = _check_input(predicate=(os.path.exists(output_folder) and os.path.isdir(output_folder)),
                                         msg='Incorrect output_folder: {0}'.format(output_folder))

        result_files = [f for f in os.listdir(output_folder) if ".xml" in f]
        result_files.sort(reverse=True)

        if not result_files:
            print "\nNo test_results files were found in {0}".format(output_folder)
            return

        files_to_ask_range = list(range(len(result_files)))
        files_to_ask = zip(files_to_ask_range, result_files)
        filename_index = eval(_check_input(predicate=lambda x: eval(x) in files_to_ask_range,
                                           msg="Please choose results file \n" + "\n".join(
                                               map(lambda x: str(x[0]) + "->" + str(x[1]), files_to_ask)) + ":\n"))
        filename = '/'.join([output_folder, result_files[filename_index]])

    if not version:
        version = _get_ovs_version()

    test_result_file = filename
    if not os.path.exists(test_result_file):
        raise Exception("Test result file {0} was not found on system".format(test_result_file))
    if not os.path.isfile(test_result_file):
        raise Exception("{0} is not a valid file".format(test_result_file))

    testrail_api = testrailapi.TestrailApi(TESTRAIL_SERVER, key=TESTRAIL_KEY)
    project = testrail_api.get_project_by_name(project_name)
    project_id = project['id']

    milestone_id = None
    if milestone:
        milestone = testrail_api.get_milestone_by_name(project_id, milestone)
        milestone_id = milestone['id']

    today = datetime.datetime.today()
    date = today.strftime('%a %b %d %H:%M:%S')
    env_info = _get_env_info()
    name = '_'.join([env_info, version, date])

    project_mapping_file = '/'.join([General.CONFIG_DIR, "project_testsuite_mapping.cfg"])
    project_map = ConfigParser.ConfigParser()
    project_map.read(project_mapping_file)

    if not project_map.has_section(project_name):
        raise Exception(
            "Config file {0} does not contain section for specified project {1}".format(project_mapping_file,
                                                                                        project_name))

    error_messages = []

    xmlfile = minidom.parse(test_result_file).childNodes[0]
    duration_suite_map = {}
    for child in xmlfile.childNodes:
        suite = child.getAttribute('classname').split('.')[-2]
        if suite == '<nose' or suite.startswith('ContextSuite'):
            continue

        if suite not in duration_suite_map:
            duration_suite_map[suite] = 0
        duration_suite_map[suite] += int(child.getAttribute('time'))

    durations = ''
    for key in sorted(duration_suite_map.keys()):
        durations += "%30s: " % key + _get_textual_values(duration_suite_map[key])

    durations += '\n%30s: ' % 'Total Duration' + _get_textual_values(sum(duration_suite_map.values()))

    added_suites = []
    plan_id = None
    suite_to_run = {}
    case_name_to_test_id = {}

    # Retrieve test cases from xml file
    all_cases = {}
    ran_cases = {}
    suite_name = ''
    suite_id = ''
    suite_name_to_id = {}
    section_name_to_id = {}

    all_sections = {}

    for child in xmlfile.childNodes:
        classname = child.getAttribute('classname')
        if classname.startswith(('<nose', 'nose', '&lt;nose')):
            continue

        option = classname.split('.')[-3]

        if child.childNodes and child.childNodes[0].getAttribute('type') in ['nose.plugins.skip.SkipTest', 'unittest.case.SkipTest'] and \
           child.childNodes[0].getAttribute('message') != BLOCKED_MESSAGE:
            continue
        case_name = child.getAttribute('name')
        match = re.search("c\d+_(.+)", case_name)
        case_name = match.groups()[0] if match else case_name

        previous_suite_name = suite_name
        suite_name = project_map.get(project_name, option).split(';')[0]
        section_names = project_map.get(project_name, option).split(';')[1].split(',')
        section_name = section_names[-1]

        if suite_name != previous_suite_name:
            suite = testrail_api.get_suite_by_name(project_id, suite_name)
            suite_id = suite['id']
            suite_name_to_id[suite_name] = suite_id
            all_cases[suite_name] = testrail_api.get_cases(project_id, suite['id'])

        section = testrail_api.get_section_by_name(project_id, suite['id'], section_name)

        if suite['id'] not in all_sections:
            all_sections[suite['id']] = testrail_api.get_sections(project_id, suite['id'])
        section_id = section['id']

        if suite_id in section_name_to_id:
            section_name_to_id[suite_id][section_name] = section_id
        else:
            section_name_to_id[suite_id] = {section_name: section_id}
        case_id = [case for case in all_cases[suite_name] if case['section_id'] == section_id and case['title'] == case_name]
        if not case_id:
            new_case = testrail_api.add_case(section_id=section_id, title=case_name)
            all_cases[suite_name].append(new_case)

        ran_cases[suite_name] = ran_cases[suite_name].add(case_name) or ran_cases[suite_name] if ran_cases.get(suite_name) else set([case_name])

    testcase_ids_to_select = []

    for child in xmlfile.childNodes:
        classname = child.getAttribute('classname')

        if classname.startswith(('<nose', 'nose')):
            if child.childNodes[0].childNodes and child.childNodes[0].childNodes[0].nodeType == minidom.DocumentType.CDATA_SECTION_NODE:
                error_messages.append(child.childNodes[0].childNodes[0].data)
            else:
                error_messages.append(child.childNodes[0].getAttribute('message'))
            continue

        suite = classname.split('.')[-3]

        is_blocked = False

        if child.childNodes and "SkipTest" in child.childNodes[0].getAttribute('type'):
            if child.childNodes[0].getAttribute('message') == BLOCKED_MESSAGE:
                is_blocked = True

        if not project_map.has_option(project_name, suite):
            raise Exception("Testsuite '%s' is not configured for project '%s' in '%s'" % (suite, project_name,
                                                                                           project_mapping_file))

        full_name = project_map.get(project_name, suite)
        suite_name = full_name.split(';')[0]
        create_run = False
        if suite_name not in added_suites:
            create_run = True
            if suite_name not in suite_name_to_id:
                continue
            added_suites.append(suite_name)
            testcase_ids_to_select = [case['id'] for case in all_cases[suite_name] if case['title'] in ran_cases[suite_name]]

        case_name = child.getAttribute('name')

        if plan_id is None:
            create_run = False
            description = _get_description(plan_comment=comment, durations=durations)
            plan_id = testrail_api.add_plan(project_id, name, description, milestone_id or None)['id']
            entry = testrail_api.add_plan_entry(plan_id, suite_name_to_id[suite_name], suite_name, include_all=False,
                                                case_ids=testcase_ids_to_select)
            run_id = entry['runs'][0]['id']
            suite_to_run[suite_name] = run_id

        if create_run:
            entry = testrail_api.add_plan_entry(plan_id, suite_name_to_id[suite_name], suite_name, include_all=False,
                                                case_ids=testcase_ids_to_select)
            run_id = entry['runs'][0]['id']
            suite_to_run[suite_name] = run_id

        run_id = suite_to_run[suite_name]
        if case_name not in case_name_to_test_id:
            all_tests_for_run = testrail_api.get_tests(run_id=run_id)
            for test in all_tests_for_run:
                case_name_to_test_id[test['title'] + str(run_id)] = test['id']

        test_id = case_name_to_test_id[case_name + str(run_id)]

        comment = ''
        if not child.childNodes:
            status_id = TESTRAIL_STATUS_ID_PASSED
        elif child.childNodes[0].getAttribute('type') in ['nose.plugins.skip.SkipTest', 'unittest.case.SkipTest']:
            if is_blocked:
                status_id = TESTRAIL_STATUS_ID_BLOCKED
            else:
                status_id = TESTRAIL_STATUS_ID_SKIPPED
            if child.childNodes[0].childNodes and \
               child.childNodes[0].childNodes[0].nodeType == minidom.DocumentType.CDATA_SECTION_NODE:
                comment = child.childNodes[0].childNodes[0].data
        else:
            status_id = TESTRAIL_STATUS_ID_FAILED
            if child.childNodes[0].childNodes and \
               child.childNodes[0].childNodes[0].nodeType == minidom.DocumentType.CDATA_SECTION_NODE:
                comment = child.childNodes[0].childNodes[0].data
            else:
                comment = child.childNodes[0].getAttribute('message')
        elapsed = int(child.getAttribute('time'))
        if elapsed == 0:
            elapsed = 1
        testrail_api.add_result(test_id=test_id, status_id=status_id, comment=comment, version=version,
                                elapsed='%ss' % elapsed, custom_fields={'custom_hypervisor': GeneralPMachine.get_hypervisor_type()})

    xmlfile.unlink()
    del xmlfile

    if error_messages:
        print "\nSome testsuites failed to start because an error occurred during setup:\n{0}".format(error_messages)

    url = None
    if plan_id:
        url = "http://%s/index.php?/plans/view/%s" % (TESTRAIL_SERVER, plan_id)
        print "\n" + url

    return url


##################
# HELPER FUNCTIONS
##################

def _get_description(plan_comment="", durations=""):
    """
    Generate description for pushing to Testrail
    """
    child_process = subprocess.Popen(args="dmidecode | grep -A 12 'Base Board Information'",
                                     shell=True,
                                     stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)
    sysinfo, _ = child_process.communicate()
    if child_process.returncode != 0:
        sysinfo = "NO MOTHERBOARD INFORMATION FOUND"

    child_process = subprocess.Popen(args="lshw -short",
                                     shell=True,
                                     stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)
    lshwinfo, _ = child_process.communicate()
    if child_process.returncode != 0:
        lshwinfo = "NO HARDWARE INFORMATION FOUND"

    diskinfo = ''
    meminfo = []
    cpuinfo = []
    for line in lshwinfo.splitlines():
        if line.find("disk") >= 0:
            if line.find('DVD-ROM') >= 0 or line.find('CD-ROM') >= 0:
                continue
            l = line.split()
            l.pop(2)
            l.pop(0)
            for part in l:
                diskinfo += '%13s' % part
            diskinfo += '\n'
        elif line.find('System Memory') >= 0 or line.find("System memory") >= 0:
            l = line.split()
            index = l.index('memory') + 1
            for item in l[index:]:
                meminfo.append(item)
        elif line.find('processor') >= 0 and line.find('CPU [empty]') == -1:
            l = line.split()
            index = l.index('processor') + 1
            cinfo = " ".join(l[index:])
            cpuinfo.append(cinfo)
    hardware_info = "### " + sysinfo + '\n### Disk Information\n' + diskinfo + '\n### Processor Information\n' + '* ' + '\n* '.join(cpuinfo) + '\n### Memory Information\n' + '* ' + ' '.join(meminfo)
    description = ""
    node_ips = ""
    for ip in GeneralPMachine.get_all_ips():
        node_ips += "* " + ip + "\n"
    for item, value in (("ip", "%s" % node_ips),
                        ("testsuite", durations),
                        ("Hypervisor", GeneralPMachine.get_hypervisor_type()),
                        ("hardware", hardware_info),
                        ("package", _get_package_info()),
                        ("Comment ", ('*' * 40 + "\n" + plan_comment) if plan_comment else '')):
        description += "# %s INFO \n%s\n" % (item.upper(), value)

    return description


def _check_input(predicate, msg):
    """
    :param predicate:
    :param msg:
    :return:
    """
    while True:
        try:
            result = raw_input(msg)
            if predicate(result):
                return result
        except Exception:
            continue


def _get_ovs_version():
    """
    Retrieve version of ovs installation
    """
    packages = _get_package_info()
    main_pkg = [pck for pck in packages.splitlines() if "openvstorage " in pck]
    if not main_pkg:
        return ""

    return re.split("\s*", main_pkg[0])[1]


def _get_package_info():
    """
    Retrieve package information for installation
    """
    command = "dpkg-query -W -f='${binary:Package} ${Version}\t${Description}\n' | grep 'openvstorage\|volumedriver-base\|alba \|arakoon\|python-celery '"

    child_process = subprocess.Popen(command, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)

    (output, _error) = child_process.communicate()
    return output


def _get_env_info():
    """
    Retrieve number of env nodes and the last two ip digits to add to the testrail title
    """
    number_of_nodes = len(GeneralStorageRouter.get_storage_routers())
    split_ip = GeneralStorageRouter.get_local_storagerouter().ip.split('.')
    return str(number_of_nodes) + 'N-' + split_ip[2] + '.' + split_ip[3]
