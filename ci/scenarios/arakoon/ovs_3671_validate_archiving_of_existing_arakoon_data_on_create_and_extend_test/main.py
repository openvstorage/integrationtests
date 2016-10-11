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


class ArakoonArchiving(object):

    def __init__(self):
        pass

    @staticmethod
    def main():
        ArakoonArchiving.test_archiving()
        return {'status': 'PASSED', 'case_type': 'FUNCTIONAL'}

    @staticmethod
    def test_archiving():
        """
        Required method that has to follow our json output guideline
        This data will be sent to testrails to process it thereafter
        :return:
        """


def run():
    return ArakoonArchiving().main()

if __name__ == "__main__":
    run()
