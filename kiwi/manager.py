import requests
import uuid
import time
import logging

from Queue import Empty as QueueEmpty
from multiprocessing import Process
import defaults


class Manager (Process):
    log = logging.getLogger('kiwi.manager')

    def __init__(self, mqueue,
                 id=None,
                 kube_endpoint=defaults.kube_endpoint,
                 etcd_endpoint=defaults.etcd_endpoint,
                 etcd_prefix=defaults.etcd_prefix,
                 refresh_interval=defaults.refresh_interval):

        super(Manager, self).__init__()

        if id is None:
            id = str(uuid.uuid1())

        self.id = id
        self.refresh_interval = 10

        self.etcd_endpoint = etcd_endpoint
        self.etcd_prefix = etcd_prefix
        self.kube_endpoint = kube_endpoint

        self.q = mqueue
        self.addresses = {}

    def run(self):
        last_refresh = 0

        while True:
            try:
                msg = self.q.get(True, self.refresh_interval)
                self.log.debug('dequeued message %s',
                               msg['message'])
                self.log.debug('state dump: %s', self.addresses)

                handler = getattr(
                    self,
                    'handle_%s' % msg['message'].replace('-', '_'),
                    None)

                if not handler:
                    self.log.debug('unhandled message: %s', msg['message'])
                    continue

                handler(msg)
            except QueueEmpty:
                pass

            now = time.time()
            if now > last_refresh + self.refresh_interval:
                self.refresh()
                last_refresh = now

    def refresh(self):
        self.log.info('start refresh pass (%d addresses)',
                      len(self.addresses))
        for address in self.addresses.keys():
            if self.address_is_claimed(address):
                self.refresh_address(address)
        self.log.info('finished refresh pass (%d addresses)',
                      len(self.addresses))

    def url_for(self, address):
        return '%s/v2/keys%s/publicips/%s' % (
            self.etcd_endpoint,
            self.etcd_prefix,
            address)

    def refresh_address(self, address):
        assert address in self.addresses
        assert self.addresses[address]['claimed']

        self.log.info('refresh %s', address)
        r = requests.put(self.url_for(address),
                         params={'prevValue': self.id,
                                 'ttl': self.refresh_interval * 2},
                         data={'value': self.id})

        if not r.ok:
            self.log.error('failed to refresh claim on %s: %s',
                           address,
                           r.reason)
            self.release_address(address)

    def claim_address(self, address):
        assert address in self.addresses

        r = requests.put(self.url_for(address),
                         params={'prevExist': 'false',
                                 'ttl': self.refresh_interval*2},
                         data={'value': self.id})

        if not r.ok:
            # We log failures at debug level because we expect to see
            # failures here if another node asserts a claim first.
            self.log.debug('failed to claim %s: %s',
                           address,
                           r.reason)
            return

        self.log.warn('claimed %s', address)
        self.addresses[address]['claimed'] = True

    def release_address(self, address):
        if not self.address_is_claimed(address):
            self.log.debug('not releasing unclaimed address %s',
                           address)
            return

        self.addresses[address]['claimed'] = False

        r = requests.delete(self.url_for(address),
                            params={'prevValue': self.id})

        if not r.ok:
            self.log.error('failed to release %s: %s',
                           address,
                           r.reason)
        else:
            self.log.warn('released %s', address)

    def remove_address(self, address):
        assert address in self.addresses

        self.log.info('removing address %s', address)
        self.release_address(address)
        del self.addresses[address]

    def release_all_addresses(self):
        for address in self.addresses.keys():
            self.release_address(address)

    def handle_add_service(self, msg):
        service = msg['service']

        for address in service.get('publicIPs', []):
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


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    l = logging.getLogger('requests')
    l.setLevel(logging.WARN)
    m = Manager()
    m.run()
