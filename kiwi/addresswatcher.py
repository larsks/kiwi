import logging
import requests
import time
import re
from multiprocessing import Process

import defaults

re_address = re.compile('\d+\.\d+\.\d+\.\d+')


class AddressWatcher (Process):
    log = logging.getLogger('kiwi.addresswatcher')

    def __init__(self,
                 queue,
                 etcd_endpoint=defaults.etcd_endpoint,
                 etcd_prefix=defaults.etcd_prefix,
                 reconnect_interval=defaults.reconnect_interval):
        super(AddressWatcher, self).__init__()

        self.q = queue
        self.etcd_endpoint = etcd_endpoint
        self.etcd_prefix = etcd_prefix
        self.reconnect_interval = reconnect_interval

    def run(self):
        waitindex = None

        while True:
            self.log.debug('watching from waitindex = %s', waitindex)
            r = requests.get('%s/v2/keys%s/publicips' % (self.etcd_endpoint,
                                                         self.etcd_prefix),
                             params={'recursive': 'true',
                                     'wait': 'true',
                                     'waitIndex': waitindex})
            if r.ok:
                event = r.json()
                self.log.debug('event: %s', event)
                waitindex = event['node']['modifiedIndex'] + 1

                node = event['node']
                address = node['key'].split('/')[-1]

                if not re_address.match(address):
                    self.log.error('invalid address %s', address)
                    continue

                handler = getattr(self, 'handle_%s' %
                                  event['action'].lower(), None)

                if not handler:
                    self.log.debug('unknown event: %(action)s' % event)
                    continue

                handler(address, node)
            else:
                self.log.error('request failed (%d): %s',
                               r.status_code,
                               r.reason)
                time.sleep(self.reconnect_interval)

    def handle_create(self, address, node):
        self.q.put({'message': 'create-address',
                    'address': address,
                    'node': node})

    def handle_set(self, address, node):
        self.q.put({'message': 'set-address',
                    'address': address,
                    'node': node})

    def handle_delete(self, address, node):
        self.q.put({'message': 'delete-address',
                    'address': address,
                    'node': node})

    handle_compareanddelete = handle_delete

    def handle_expire(self, address, node):
        self.q.put({'message': 'expire-address',
                    'address': address,
                    'node': node})

if __name__ == '__main__':
    import multiprocessing
    logging.basicConfig(level=logging.DEBUG)

    q = multiprocessing.Queue()
    s = AddressWatcher(q)
    s.start()

    while True:
        msg = q.get()
        print 'msg:', msg
