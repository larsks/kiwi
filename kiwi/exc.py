class KiwiError (Exception):
    def __init__(self, message=None, reason=None, returncode=None,
                 stdout=None, stderr=None, *args, **kwargs):
        self.reason = reason
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        super(KiwiError, self).__init__(message)


class InterfaceDriverError (KiwiError):
    pass


class FirewallDriverError (KiwiError):
    pass


class UnknownAddressError (KiwiError):
    pass


class UnclaimedAddressError(KiwiError):
    pass


class ClaimFailedError (KiwiError):
    pass


class RefreshFailedError (KiwiError):
    pass
