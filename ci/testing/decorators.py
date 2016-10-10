def required_roles(roles, location="GLOBAL"):
    def validate_required_roles(func):
        def validate(*args, **kwargs):
            # can be GLOBAL, can be LOCAL
            if location == "GLOBAL":
                print roles
            elif location == "LOCAL":
                print kwargs['storagerouter_ip']
                print roles
            else:
                raise Exception()
            return func(*args, **kwargs)
        return validate
    return validate_required_roles


class MyHandler(object):
    @staticmethod
    @required_roles(['DB'])
    def validate_global():
        print('hello world')

    @staticmethod
    @required_roles(['DB', 'SCRUB'], "LOCAL")
    def validate_local(storagerouter_ip):
        print('hello world')