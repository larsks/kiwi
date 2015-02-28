import subprocess
import six
import functools
import shlex
import logging

LOG = logging.getLogger(__name__)


class CommandError(Exception):
    def __init__(self, command, returncode, stdout, stderr):
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def __repr__(self):
        return '<CommandError [%d]: %s>' % (
            self.returncode,
            self.stderr.splitlines()[0])

    def __str__(self):
        return repr(self)


def cmd(*args):
    '''This acts very much like subprocess.check_output, except that
    it raises CommandError if a command exits with a non-zero exit code,
    and the CommandError objects include the full command spec, a
    returncode, stdout, and stderr.'''

    LOG.debug('running command: %s', ' '.join(args))
    p = subprocess.Popen(args,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    out, err = p.communicate()

    if p.returncode != 0:
        LOG.debug('command failed [%d]: %s...',
                  p.returncode,
                  err.splitlines()[0])
        raise CommandError(args, p.returncode, out, err)

    return out


class Rule(tuple):
    def __new__(cls, *args):
        if isinstance(args[0], six.string_types):
            args = (shlex.split(args[0]),)

        return super(Rule, cls).__new__(cls, *args)

    def __str__(self):
        return ' '.join(self)


class Chain(object):
    def __init__(self, name, table):
        self.name = name
        self.table = table
        self.iptables = table.iptables

    def __str__(self):
        return '<Chain %s:%s>' % (
            self.table.table,
            self.name)

    def __repr__(self):
        return str(self)

    def rules(self):
        for rule in self.iptables('-S', self.name).splitlines():
            rule = Rule(rule)
            if rule[0] != '-A':
                continue

            yield Rule(rule[2:])

    def rule_exists(self, rule):
        try:
            self.iptables('-C', self.name, *rule)
        except CommandError as err:
            if err.returncode != 1:
                raise

            return False
        else:
            return True

    @property
    def policy(self):
        '''This is property that when read returns the current default
        policy for this chain and when assigned to changes the default
        policy.'''
        for rule in self.iptables('-S', self.name).splitlines():
            rule = Rule(rule)
            if rule[0] == '-P':
                return rule[2]

        raise ValueError('chain does not have default policy')

    @policy.setter
    def policy(self, value):
        '''Set the default policy for this chain.'''
        self.iptables('-P', self.name, value)

    def append(self, rule):
        self.iptables('-A', self.name, *rule)

    def insert(self, rule, pos=1):
        self.iptables('-I', self.name, str(pos), *rule)

    def replace(self, pos, rule):
        self.iptables('-R', self.name, str(pos), *rule)

    def zero(self):
        self.iptables('-Z', self.name)

    def delete(self, rule=None, pos=None):
        if rule is not None:
            self.iptables('-D', self.name, *rule)
        elif pos is not None:
            self.iptables('-D', self.name, str(pos))
        else:
            raise ValueError('requires either rule or position')

    def flush(self):
        self.iptables('-F', self.name)


class ChainFinder(object):
    def __init__(self, table):
        self.table = table

    def __getitem__(self, k):
        return self.table.get_chain(k)

    def __iter__(self):
        for k in self.keys():
            yield self.table.get_chain(k)

    def keys(self):
        for chain in self.table.list_chains():
            yield chain


class Table(object):
    def __init__(self, name='filter', netns=None):
        self.name = name

        prefix = ()
        if netns is not None:
            prefix = ('ip', 'netns', 'exec', netns)

        self.iptables = functools.partial(
            cmd, *(prefix + ('iptables', '-w', '-t', name)))

        self.chains = ChainFinder(self)

    def __str__(self):
        return '<Table %s>' % (self.name,)

    def __repr__(self):
        return str(self)

    def chain_exists(self, chain):
        try:
            self.iptables('-S', chain)
        except CommandError:
            return False
        else:
            return True

    def list_chains(self):
        for rule in self.iptables('-S').splitlines():
            rule = Rule(rule)
            if rule[0] in ['-P', '-N']:
                yield rule[1]

    def get_chain(self, chain):
        if not self.chain_exists(chain):
            raise KeyError(chain)

        return Chain(chain, self)

    def create_chain(self, chain):
        self.iptables('-N', chain)
        return self.chains[chain]

    def delete_chain(self, chain):
        self.iptables('-X', chain)

    def flush_chain(self, chain):
        self.iptables('-F', chain)

    def flush_all(self):
        self.iptables('-F')

    def zero_all(self):
        self.iptables('-Z')

    def rule_exists(self, chain, rule):
        chain = self.chain[chain]
        return chain.rule_exists(rule)


filter = Table('filter')
nat = Table('nat')
mangle = Table('mangle')
raw = Table('raw')
