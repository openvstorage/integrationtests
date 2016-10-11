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


class ExampleTest(object):

    def __init__(self):
        pass

    @staticmethod
    def main():
        ExampleTest._execute_test()

        # status depends on attributes in class: ci.helpers.testtrailapi.TestrailResult
        # case_type depends on attributes in class: ci.helpers.testtrailapi.TestrailCaseType
        return {'status': 'PASSED', 'case_type': 'ADMINISTRATION'}

    @staticmethod
    def _execute_test():
        """
        Required method that has to follow our json output guideline
        This data will be sent to testrails to process it thereafter
        :return:
        """
        pass


def run():
    return ExampleTest().main()

if __name__ == "__main__":
    ExampleTest().main()
