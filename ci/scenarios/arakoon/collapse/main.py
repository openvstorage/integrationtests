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
        ExampleTest._process_test_results()
        ExampleTest._push_to_testrail()
        return {'status': 'NOK'}

    @staticmethod
    def _execute_test():
        """
        Required method that has to follow our json output guideline
        This data will be sent to testrails to process it thereafter
        :return:
        """
        pass

    @staticmethod
    def _process_test_results():
        """
        Required method that has to follow our json output guideline
        This data will be sent to testrails to process it thereafter
        :return:
        """
        pass

    @staticmethod
    def _push_to_testrail():
        """
        Required method that has to follouw our testrail pushing guidelines
        Will send the data to testrail
        :return:
        """
        pass


def run():
    return ExampleTest().main()

if __name__ == "__main__":
    run()
