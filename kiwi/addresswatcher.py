import logging
import requests
import time
import re
from multiprocessing import Process

import defaults

LOG = logging.getLogger(__name__)
re_address = re.compile('\d+\.\d+\.\d+\.\d+')


def iter_events(url, interval=1, recursive=True):
    '''Produces an inifite stream of events from etcd regarding the given
    URL.'''

    waitindex = None

    while True:
        try:
            params = {'recursive': recursive,
                      'wait': True,
                      'waitIndex': waitindex}

            r = requests.get(url, params=params)
            r.raise_for_status()

            event = r.json()
            waitindex = event['node']['modifiedIndex'] + 1
            yield event
        except Exception as exc:
            LOG.error('connection failed: %s' % exc)
            time.sleep(interval)


class AddressWatcher (Process):
    '''Watches an etcd directory of keys that represent public ip addresses
    being managed by kiwi, and writes the resulting events to the message
    queue.'''

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
        url = '%s/v2/keys%s/publicips' % (self.etcd_endpoint,
                                          self.etcd_prefix)

        for event in iter_events(url, interval=self.reconnect_interval):
            LOG.debug('event: %s', event)

            node = event['node']
            address = node['key'].split('/')[-1]

            if not re_address.match(address):
                LOG.error('invalid address %s', address)
                continue

            handler = getattr(self, 'handle_%s' %
                              event['action'].lower(), None)

            # we log missing handlers at debug level because we probably
            # intentionally have not written a handler for the event.
            if not handler:
                LOG.debug('unknown event: %(action)s' % event)
                continue

            handler(address, node)

    def handle_create(self, address, node):
        self.q.put({'message': 'create-address',
                    'target': address,
                    'address': address,
                    'node': node})

    def handle_set(self, address, node):
        self.q.put({'message': 'set-address',
                    'target': address,
                    'address': address,
                    'node': node})

    def handle_delete(self, address, node):
        self.q.put({'message': 'delete-address',
                    'target': address,
                    'address': address,
                    'node': node})

    handle_compareanddelete = handle_delete

    def handle_expire(self, address, node):
        self.q.put({'message': 'expire-address',
                    'target': address,
                    'address': address,
                    'node': node})

if __name__ == '__main__':
    from multiprocessing import Queue
    import pprint

    logging.basicConfig(level=logging.DEBUG)
    q = Queue()
    s = AddressWatcher(q)
    s.start()

    while True:
        msg = q.get()
        pprint.pprint(msg)
