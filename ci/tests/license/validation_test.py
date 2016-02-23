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
License validation testsuite
"""

import os
from ci.tests.general.general import General


class TestValidation(object):
    """
    License validation testsuite
    """
    tests_to_run = General.get_tests_to_run(General.get_test_level())

    alternative_first_lines = ["Copyright 2014 iNuron NV", "Copyright 2015 iNuron NV", "Copyright 2016 iNuron NV"]
    license_to_check = """Copyright 2014 iNuron NV

    Licensed under the Open vStorage Modified Apache License (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.openvstorage.org/license

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
    """
    extensions = ['py', 'js', 'html', 'css']
    folders_to_check = ['/opt/OpenvStorage']
    # define files and directories to skip checking
    # relative paths to the root
    skip_files = ['/webapps/frontend/index.html',
                  '/config/gunicorn.cfg.py',
                  '/config/django/django_gunicorn_ovs.cfg.py',
                  '/opt/OpenvStorage/ovs/extensions/generic/fakesleep.py']
    skip_dirs = ['/webapps/frontend/lib',
                 '/webapps/api/static/rest_framework/css',
                 '/webapps/frontend/css',
                 '/webapps/api/static/rest_framework/js',
                 '/.git',
                 '/scripts/',
                 '/extensions/db/arakoon/arakoon/arakoon/',
                 '/extensions/db/arakoon/pyrakoon/pyrakoon/',
                 '/opt/OpenvStorage/config/templates/cinder-volume-driver/',
                 '/opt/OpenvStorage/config/templates/cinder-unit-tests/']
    # define files and directories to except from skip
    # should be subdirectories of the skip directories
    # or files inside the skip_dirs
    except_skip_dirs = ['/webapps/frontend/lib/ovs']
    except_skip_files = ['/webapps/frontend/css/ovs.css']

    ####################
    # HELPER FUNCTIONS #
    ####################

    @staticmethod
    def get_all_files(root_folder, extensions=None):
        """
        Recursively get all files in root_folder
        :param root_folder: Folder to start with and recursively go down
        :param extensions: File extensions to add to the filter
        :return: List of files
        """
        for skip_dir in TestValidation.skip_dirs:
            if skip_dir in root_folder:
                dirskip = True
                for except_skip_dir in TestValidation.except_skip_dirs:
                    if skip_dir in except_skip_dir:
                        dirskip = False
                        break
                if dirskip:
                    return []
        files_to_process = []
        if not os.path.exists(root_folder):
            raise ValueError('Root folder {0} does not exist'.format(root_folder))

        files_dirs = os.listdir(root_folder)
        for file_name in files_dirs:
            path = os.path.join(root_folder, file_name)
            if os.path.isfile(path):
                if extensions:
                    for extension in extensions:
                        if path.endswith(extension):
                            files_to_process.append(path)
                            break
                else:
                    files_to_process.append(path)

        dirs = []
        files_dirs = os.listdir(root_folder)
        for file_name in files_dirs:
            path = os.path.join(root_folder, file_name)
            if os.path.isdir(path):
                dirs.append(path)

        for dir_ in dirs:
            dir_path = os.path.join(root_folder, dir_)
            files_to_process.extend(TestValidation.get_all_files(dir_path, extensions))
        return files_to_process

    #########
    # TESTS #
    #########

    @staticmethod
    def check_license_headers_test():
        """
        Check license headers
        """
        General.check_prereqs(testcase_number=1,
                              tests_to_run=TestValidation.tests_to_run)

        license_splitlines = TestValidation.license_to_check.splitlines()
        files_with_diff_licenses = ''
        for root_folder in TestValidation.folders_to_check:
            files_to_process = TestValidation.get_all_files(root_folder, TestValidation.extensions)

            for file_name in files_to_process:
                skip = False
                for skip_file in TestValidation.skip_files:
                    if file_name.endswith(skip_file):
                        skip = True
                        break
                for skip_dir in TestValidation.skip_dirs:
                    dirskip = False
                    if skip_dir in file_name:
                        dirskip = True
                        for except_skip_dir in TestValidation.except_skip_dirs:
                            if except_skip_dir in file_name:
                                dirskip = False
                                break
                    if dirskip:
                        skip = True
                        break
                for except_skip_file in TestValidation.except_skip_files:
                    if except_skip_file in file_name:
                        skip = False
                        break
                if not skip:
                    with open(file_name, 'r') as utf_file:
                        data = utf_file.read().decode("utf-8-sig").encode("utf-8")
                        lines_to_check = data.splitlines()
                    offset = 0

                    comments = {'py': ('# ', ''),
                                'cfg': ('# ', ''),
                                'js': ('// ', ''),
                                'html': ('<!--', ' -->'),
                                'css': ('/*', '*/')}
                    before, after = comments.get(file_name.split('.')[-1], ('# ', ''))
                    if after:
                        offset += 1
                    comment_section_found = False
                    for line_index in range(0, len(lines_to_check) - 1):
                        if lines_to_check[line_index].lstrip().startswith(before):
                            # found the first commented piece of code
                            offset += line_index
                            comment_section_found = True
                            break
                    if comment_section_found:
                        # checking first line against 2014/2015/2016 license
                        first_line_checked = False
                        for alternative_first_line in TestValidation.alternative_first_lines:
                            if alternative_first_line in lines_to_check[0 + offset]:
                                first_line_checked = True
                        if not first_line_checked:
                            files_with_diff_licenses += 'First line {1} differs for {0}\n'.format(file_name, lines_to_check[0 + offset])
                        else:
                            # checking the rest of the lines
                            if offset + len(license_splitlines) > len(lines_to_check):
                                # found comment section but it's too small for license to fit
                                files_with_diff_licenses += 'File too small for license to fit: {0}\n'.format(file_name)
                            else:
                                for line_index in range(1, len(license_splitlines) - 1):
                                    if license_splitlines[line_index] not in lines_to_check[line_index + offset]:
                                        files_with_diff_licenses += 'File {0} has a different license\n{1}\nExpected:\n{2}\n'.format(file_name, lines_to_check[line_index + offset], license_splitlines[line_index])
                                        break
                    else:
                        files_with_diff_licenses += 'No comments detected in {0}\n'.format(file_name)
        assert files_with_diff_licenses == '', 'Following files were found with different licenses:\n {0}'.format(files_with_diff_licenses)
