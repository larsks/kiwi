import requests
import uuid
import time
import logging
import netaddr
import threading
import Queue

from exc import *
import defaults
import addresswatcher
import servicewatcher


LOG = logging.getLogger(__name__)


class Manager (object):
    def __init__(self,
                 id=None,
                 kube_endpoint=defaults.kube_endpoint,
                 etcd_endpoint=defaults.etcd_endpoint,
                 etcd_prefix=defaults.etcd_prefix,
                 iface_driver=None,
                 fw_driver=None,
                 cidr_ranges=None,
                 refresh_interval=defaults.refresh_interval):

        super(Manager, self).__init__()

        if id is None:
            id = str(uuid.uuid1())

        self.id = id
        self.refresh_interval = refresh_interval

        self.etcd_endpoint = etcd_endpoint
        self.etcd_prefix = etcd_prefix
        self.kube_endpoint = kube_endpoint
        self.iface_driver = iface_driver
        self.fw_driver = fw_driver
        self.cidr_ranges = cidr_ranges

        if self.cidr_ranges:
            self.cidr_ranges = [netaddr.IPNetwork(n)
                                for n in cidr_ranges]

        self.addresses = {}

        self.q = Queue.Queue()

    def run(self):
        try:
            self.mainloop()
        finally:
            self.cleanup()

    def watch_addresses(self):
        '''Read address events and stuff them into the queue.'''
        watcher = addresswatcher.AddressWatcher(
            etcd_endpoint=self.etcd_endpoint,
            etcd_prefix=self.etcd_prefix)

        for event in watcher:
            self.q.put(event)

    def watch_services(self):
        '''Read service events and stuff them into the queue.'''
        watcher = servicewatcher.ServiceWatcher(
            kube_endpoint=self.kube_endpoint)

        for event in watcher:
            LOG.debug('event:', event)
            self.q.put(event)

    def mainloop(self):
        last_refresh = 0

        # start worker threads to feed the event queue
        [thread.start() for thread in [
            threading.Thread(target=self.watch_services),
            threading.Thread(target=self.watch_addresses),
        ]]

        while True:
            try:
                msg = self.q.get(True, self.refresh_interval)
                LOG.debug('dequeued message %s for %s',
                          msg['message'],
                          msg['target'])

                self.handle_message(msg)
            except AttributeError:
                LOG.debug('unhandled message %s for %s',
                          msg['message'],
                          msg['target'])
            except Queue.Empty:
                LOG.debug('Punt!')
                pass

            now = time.time()
            if now > last_refresh + self.refresh_interval:
                self.refresh()
                last_refresh = now

    def handle_message(self, msg):
        attr = 'handle_%s' % msg['message'].replace('-', '_')
        LOG.debug('looking for %s', attr)
        handler = getattr(self, attr)

        handler(msg)

    def refresh(self):
        LOG.info('start refresh pass (%d addresses)',
                 len(self.addresses))

        claimed = 0
        for address in self.addresses.keys():
            if self.address_is_claimed(address):
                claimed += 1
                self.refresh_address(address)

        LOG.info('finished refresh pass (%d addresses, %d claimed)',
                 len(self.addresses),
                 claimed)

    def url_for(self, address):
        return '%s/v2/keys%s/publicips/%s' % (
            self.etcd_endpoint,
            self.etcd_prefix,
            address)

    def refresh_address(self, address):
        assert address in self.addresses
        assert self.addresses[address]['claimed']

        LOG.info('refresh %s', address)
        try:
            r = requests.put(self.url_for(address),
                             params={'prevValue': self.id,
                                     'ttl': self.refresh_interval * 2},
                             data={'value': self.id})
            r.raise_for_status()

            if self.iface_driver:
                self.iface_driver.refresh_address(
                    address,
                    lft=self.refresh_interval*2)
        except Exception as exc:
            LOG.error('failed to refresh address %s: %s',
                      address, exc)
            self.release_address(address)

    def claim_address(self, address):
        assert address in self.addresses

        try:
            r = requests.put(self.url_for(address),
                             params={'prevExist': 'false',
                                     'ttl': self.refresh_interval*2},
                             data={'value': self.id})
        except requests.ConnectionError as exc:
            LOG.error('connection to %s failed: %s',
                      self.url_for(address),
                      exc)
            return
        else:
            if not r.ok:
                # We log failures at debug level because we expect to see
                # failures here if another node asserts a claim first.
                LOG.debug('failed to claim %s: %s',
                          address,
                          r.reason)
                return

            LOG.warn('claimed %s', address)
            self.addresses[address]['claimed'] = True

            if self.iface_driver:
                try:
                    self.iface_driver.add_address(address,
                                                  lft=self.refresh_interval*2)
                except InterfaceDriverError as exc:
                    LOG.error('failed to configure address on system: %d',
                              exc.returncode)

    def release_address(self, address):
        if not self.address_is_claimed(address):
            LOG.debug('not releasing unclaimed address %s',
                      address)
            return

        self.addresses[address]['claimed'] = False

        try:
            r = requests.delete(self.url_for(address),
                                params={'prevValue': self.id})
        except requests.ConnectionError as exc:
            LOG.error('connection to %s failed: %s',
                      self.url_for(address),
                      exc)
        else:
            if not r.ok:
                LOG.error('failed to release %s: %s',
                          address,
                          r.reason)
            else:
                LOG.warn('released %s', address)

        if self.iface_driver:
            try:
                self.iface_driver.remove_address(address)
            except InterfaceDriverError as exc:
                LOG.error('failed to remove address on system: %d',
                          exc.returncode)

    def remove_address(self, address):
        assert address in self.addresses

        LOG.info('removing address %s', address)
        self.release_address(address)
        del self.addresses[address]

    def release_all_addresses(self):
        for address in self.addresses.keys():
            self.release_address(address)

    def handle_add_service(self, msg):
        service = msg['service']

        for address in service.get('publicIPs', []):
            if not self.address_is_valid(address):
                LOG.warn('ignoring invalid address %s',
                         address)
                continue

            LOG.info('adding service %s on %s',
                     service['id'],
                     address)

            if self.fw_driver:
                try:
                    self.fw_driver.add_service(address, service)
                except FirewallDriverError as exc:
                    LOG.error('failed to configure host firewall: %d',
                              exc.returncode)

            try:
                self.addresses[address]['count'] += 1
            except KeyError:
                self.addresses[address] = {
                    'count': 1,
                    'claimed': False
                }

            if not self.address_is_claimed(address):
                self.claim_address(address)

    def handle_delete_service(self, msg):
        service = msg['service']

        for address in service.get('publicIPs', []):
            if not self.address_is_valid(address):
                LOG.warn('ignoring invalid address %s',
                         address)
                continue

            LOG.info('removing service %s on %s',
                     service['id'],
                     address)

            if self.fw_driver:
                try:
                    self.fw_driver.remove_service(address, service)
                except FirewallDriverError as exc:
                    LOG.error('failed to configure host firewall: %d',
                              exc.returncode)

            if address in self.addresses:
                self.addresses[address]['count'] -= 1
                if not self.address_is_active(address):
                    self.remove_address(address)

    def handle_delete_address(self, msg):
        address = msg['address']
        if self.address_is_active(address):
            self.claim_address(address)

    handle_expire_address = handle_delete_address

    def address_is_active(self, address):
        return (address in self.addresses and
                self.addresses[address]['count'] > 0)

    def address_is_claimed(self, address):
        return (address in self.addresses and
                self.addresses[address]['claimed'])

    def address_is_valid(self, address):
        if self.cidr_ranges is None:
            return True

        for net in self.cidr_ranges:
            if address in net:
                return True

        return False

    def cleanup(self):
        self.release_all_addresses()

        if self.fw_driver:
            self.fw_driver.cleanup()

        if self.iface_driver:
            self.iface_driver.cleanup()


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    l = logging.getLogger('requests')
    l.setLevel(logging.WARN)
    m = Manager()
    m.run()
