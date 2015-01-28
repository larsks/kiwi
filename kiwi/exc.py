class KiwiError (Exception):
    pass


class InterfaceDriverError (KiwiError):
    def __init__(self, status=None):
        self.status = status
        super(InterfaceDriverError, self).__init__()

class FirewallDriverError (KiwiError):
    def __init__(self, status=None):
        self.status = status
        super(FirewallDriverError, self).__init__()
