import requests
import uuid
import select
import time
import logging

from Queue import Empty as QueueEmpty
from multiprocessing import Queue
from addresswatcher import AddressWatcher
from servicewatcher import ServiceWatcher

class Manager (object):
    log = logging.getLogger('kiwi.manager')

    def __init__(self, id=None):
        if id is None:
            id = str(uuid.uuid1())
            self.id = id
            self.refresh_interval=10

            self.etcd_api = 'http://localhost:4001'
            self.etcd_prefix = '/kube'

            self.q = Queue()
            self.workers = [AddressWatcher(self.q),
                            ServiceWatcher(self.q)]
            self.addresses = set()

    def run(self):
        [worker.start() for worker in self.workers]

        last_refresh = 0

        while True:
            try:
                msg = self.q.get(True, self.refresh_interval)
                handler = getattr(self,
                                  'handle_%s' % msg['message'].replace('-', '_'),
                                  None)

                if not handler:
                    self.log.warn('unhandled message: %s', msg['message'])
                    continue

                handler(msg)
            except QueueEmpty:
                pass

            now = time.time()
            if now > last_refresh + self.refresh_interval:
                self.refresh()
                last_refresh = now

    def refresh(self):
        self.log.info('refresh')
        for address in list(self.addresses):
            self.refresh_address(address)

    def refresh_address(self, address):
        self.log.info('refresh %s', address)
        r = requests.put('%s/v2/keys%s/publicips/%s/lock' % (self.etcd_api,
                                                          self.etcd_prefix,
                                                          address),
                         params={'prevValue': self.id,
                                 'ttl': self.refresh_interval * 2},
                         data={'value': self.id})

        if not r.ok:
            self.log.error('failed to refresh claim on %s: %s',
                           address,
                           r.reason)
            self.release_address(address)

    def handle_address_msg(self):
        pass

    def handle_service_msg(self):
        pass

    def claim_address(self, address):
        r = requests.put('%s/v2/keys%s/publicips/%s/lock' % (self.etcd_api,
                                                          self.etcd_prefix,
                                                          address),
                         params={'prevExist': 'false',
                                 'ttl': self.refresh_interval*2},
                         data={'value': self.id})

        if not r.ok:
            self.log.warn('failed to claim %s: %s',
                          address,
                          r.reason)
            return

        self.log.info('claimed %s', address)
        self.addresses.add(address)
        

    def release_address(self, address):
        r = requests.delete('%s/v2/keys%s/publicips/%s/lock' % (self.etcd_api,
                                                          self.etcd_prefix,
                                                          address),
                         params={'prevValue': self.id})

        if not r.ok:
            self.log.warn('failed to release %s: %s',
                          address,
                          r.reason)
        else:
            self.log.info('released %s', address)

        if address in self.addresses:
            self.addresses.remove(address)

    def release_all_addresses(self):
        for address in self.addresses:
            self.release_address(address)

    def register_address(self, address):
        self.log.info('register address %s', address)
        self.claim_address(address)

    def handle_add_service(self, msg):
        service = msg['data']['service']
        if not 'publicIPs' in service:
            self.log.info('ignoring service %s with no public ips',
                          service['id'])
            return

        for address in service['publicIPs']:
                self.register_address(address)

    def handle_add_address(self, msg):
        address = msg['data']['address']
        self.claim_address(address)

    def handle_delete_address(self, msg):
        address = msg['data']['address']
        self.addresses.remove(address)

    def handle_release_lock(self, msg):
        address = msg['data']['address']
        self.claim_address(address)

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    l = logging.getLogger('requests')
    l.setLevel(logging.WARN)
    m = Manager()
    m.run()

