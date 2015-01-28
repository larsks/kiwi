import logging
import subprocess

import defaults
from exc import *

class Firewall (object):

    log = logging.getLogger('kiwi.firewall')

    def __init__(self,
                 fwchain=defaults.fwchain,
                 fwmark=defaults.fwmark):
        self.fwchain = fwchain
        self.fwmark = fwmark
        
        self.create_chain()
        self.flush_rules()

    def cleanup(self):
        self.flush_rules()

    def create_chain(self):
        ret = subprocess.call([
                'iptables', '-t', 'mangle',
                '-S', self.fwchain
            ])

        if ret == 0:
            return

        self.log.info('creating chain %s', self.fwchain)
        try:
            subprocess.check_call([
                'iptables', '-t', 'mangle',
                '-N', self.fwchain
            ])
        except subprocess.CalledProcessError as exc:
            raise FirewallDriverError(status=exc)

    def flush_rules(self):
        self.log.info('flushing all rules from %s',
                      self.fwchain)
        try:
            subprocess.check_call([
                'iptables', '-t', 'mangle',
                '-F', self.fwchain])
        except subprocess.CalledProcessError as exc:
            raise FirewallDriverError(status=exc)

    def add_service(self, address, service):
        self.log.info('adding firewall rules for service %s on %s port %d',
                      service['id'], address, service['port'])
        try:
            subprocess.check_call([str(x) for x in [
                'iptables', '-t', 'mangle',
                '-A', self.fwchain,
                '-d', address,
                '-p', service['protocol'].lower(),
                '--dport', service['port'],
                '-m', 'comment',
                '--comment', service['id'],
                '-j', 'MARK', '--set-mark', self.fwmark
            ]])
        except subprocess.CalledProcessError as exc:
            raise FirewallDriverError(status=exc)

    def remove_service(self, address, service):
        self.log.info('removing firewall rules for service %s on %s port %d',
                      service['id'], address, service['port'])
        try:
            subprocess.check_call([str(x) for x in [
                'iptables', '-t', 'mangle',
                '-D', self.fwchain,
                '-d', address,
                '-p', service['protocol'].lower(),
                '--dport', service['port'],
                '-m', 'comment',
                '--comment', service['id'],
                '-j', 'MARK', '--set-mark', self.fwmark
            ]])
        except subprocess.CalledProcessError as exc:
            raise FirewallDriverError(status=exc)

logging.basicConfig(level=logging.DEBUG)
f = Firewall()

