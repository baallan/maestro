import collections
import hostlist
import yaml
import re

AUTH_ATTRS = [
    'auth',
    'conf'
]

CORE_ATTRS = [
    'daemons',
    'aggregators',
    'samplers',
    'stores'
]

DEFAULT_ATTR_VAL = {
    'maestro_comm' : False,
    'xprt'         : 'sock',
    'interval'     : 1000000,
    'auth'         : 'none',
    'mode'         : 'static'
}

INT_ATTRS = [
    'interval',
    'offset',
    'reconnect'
]

def cvt_intrvl_str_to_us(interval_s):
    """Converts a time interval string to microseconds

    A time-interval string is an integer or float follows by a
    unit-string. A unit-string is any of the following:

    's'  - seconds
    'ms' - milliseconds
    'us' - microseconds
    'm'  - minutes

    Unit strings are not case-sensitive.

    Examples:
    '1.5s' - 1.5 seconds
    '1.5S' - 1.5 seconds
    '2s'   - 2 seconds
    """
    error_str = f"{interval_s} is not a valid time-interval string\n"\
                f"'Only a single unit-string is allowed. e.g. '50s40us' is not a valid entry."\
                f"Examples of acceptable format:\n"\
                f"'1.5s' - 1.5 seconds\n"\
                f"'1.5S' - 1.5 seconds\n"\
                f"'2us'  - 2 microseconds\n"\
                f"'3m'   - 3 minutes\n"\
                f"\n"
    if type(interval_s) == int:
        return interval_s
    if type(interval_s) != str:
        raise ValueError(f"{error_str}")
    interval_s = interval_s.lower()
    if 'us' in interval_s:
        factor = 1
        if interval_s.split('us')[1] != '':
            raise ValueError(f"{error_str}")
        ival_s = interval_s.split('us')[0]
    elif 'ms' in interval_s:
        factor = 1000
        if interval_s.split('ms')[1] != '':
            raise ValueError(f"{error_str}")
        ival_s = interval_s.split('ms')[0]
    elif 's' in interval_s:
        factor = 1000000
        if interval_s.split('s')[1] != '':
            raise ValueError(f"{error_str}")
        ival_s = interval_s.split('s')[0]
    elif 'm' in interval_s:
        factor = 60000000
        if interval_s.split('m')[1] != '':
            raise ValueError(f"{error_str}")
        ival_s = interval_s.split('m')[0]
    try:
        mult = float(ival_s)
    except:
        raise ValueError(f"{interval_s} is not a valid time-interval string")
    return int(mult * factor)

def check_offset(interval_us, offset_us=None):
    if offset_us:
        if offset_us/interval_us > .5:
            offset_us = interval_us/2
    else:
        offset_us = 0
    return offset_us

def check_opt(attr, spec):
    # Check for optional argument and return None if not present
    if attr in AUTH_ATTRS:
        if attr == 'auth':
            attr = 'name'
        if 'auth' in spec:
            spec = spec['auth']
    if attr in spec:
        if attr in INT_ATTRS:
            return cvt_intrvl_str_to_us(spec[attr])
        return spec[attr]
    else:
        if attr in DEFAULT_ATTR_VAL:
            return DEFAULT_ATTR_VAL[attr]
        else:
            return None

def check_required(attr_list, container, container_name):
    """Verify that each name in attr_list is in the container"""
    for name in attr_list:
        if name not in container:
            raise ValueError("The '{0}' attribute is required in a {1}".
                             format(name, container_name))

def expand_names(name_spec):
    if type(name_spec) != str and isinstance(name_spec, collections.Sequence):
        names = []
        for name in name_spec:
            names += hostlist.expand_hostlist(name)
    else:
        names = hostlist.expand_hostlist(name_spec)
    return names

def parse_to_cfg_str(cfg_obj):
    cfg_str = ''
    for key in cfg_obj:
        if key not in INT_ATTRS:
            if len(cfg_str) > 0:
                cfg_str += ' '
            cfg_str += key + '=' + str(cfg_obj[key])
    return cfg_str

def parse_yaml_bool(bool_):
    if bool_ is True or bool_ == 'true' or bool_ == 'True':
        return True
    else:
        return False

# tilde substitution implementation
class TildeSubs(object):
    """manage a stack of dicts for ~{} expansion"""
    def __init__(self):
        self.stack = []
        self.push(dict())
        self.re = re.compile(r'~\{[^~{}]+\}')
    def push(self, d):
        """stash current dict."""
        self.stack.append(d)
    def pop(self):
        del self.stack[-1]
    def get_val(self, key):
        """reverse search on stack for closest value of the key.
           If nothing is found, returns False.
           If empty string is found, returns None."""
        for i in range(len(self.stack) -1, -1, -1):
            if key in self.stack[i]:
                return self.stack[i][key]
        return False
    def expand_val(self, val, debug=False):
        """ DFBU substitution on a string. Returns (changed, newval)"""
        if debug:
            print("searching value: {}\n".format(val))
        newval = ""
        last = 0
        changed = False
        for m in self.re.finditer(val):
            newval += val[last:m.start()]
            last = m.end()
            var = m.string[m.start():m.end()][2:-1]
            if debug:
                print("containing: {}\n".format(var))
            s = self.get_val(var)
            if s:
                changed = True
                newval += str(s)
                if debug:
                    print("replaced with: {}\n".format(s))
            else:
                if not isinstance(s, bool):
                    changed = True
                    if debug:
                        print("empty replace: {}\n".format(var))
                else:
                    if debug:
                        print("undefined: {}\n".format(var))
        newval += val[last:]
        return (changed, newval)
    def expand_key(self, key, debug=False):
        """ DFBU substitution on a key in deepest current dict"""
        if debug:
            print("checking: {}\n".format(key))
        val = self.stack[-1][key]
        (changed, newval) = self.expand_val(val, debug)
        if changed:
            if debug:
                print("key updated: {} : {}\n".format(key, newval))
            self.stack[-1][key] = newval
        return changed

# noetcd implementation
class Decoder(object):
    def __init__(self, s):
        self.s = s
    def decode(self):
        return self.s

class Meta(object):
    def __init__(self, s):
        self.key = Decoder(s)

class NoetcdClient(object):
    """Local-use-only, daemon-free replacement for python-etcd3 as used in
       maestro_ctrl and maestro.
       Provides only the portion of the py api needed for maestro call
       compatibility.
    """
    def __init__(self, preload=None):
        self.noetc = True
        self.d = dict()
        self.load_yaml(preload)
    def get_prefix(self, prefix):
        d = dict()
        x = list(filter(lambda x: x[0].startswith(prefix), self.d.items()))
        for (k, v) in x:
            d[Meta(k)] = Decoder(v)
        return d
    def put(self, path, val):
        self.d[path] = val
    def add_watch_callback(self, key, cb):
        """cb will never be called"""
        pass
    def delete_prefix(self, p):
        kill = list(filter(lambda x: x.startswith(p), self.d.keys()))
        for k in kill:
            self.d.pop(k)
    def load_yaml(self,filename):
        if filename:
            with open(filename) as f:
                m = yaml.safe_load(f)
                self.d.update(m)
    def save_yaml(self,filename):
        with open(filename, 'w') as f:
            yaml.safe_dump(self.d, f, default_flow_style=False)
    def print_all(self, filename=None):
        if not filename:
            for i in self.d.items():
                print(i)
        else:
            with open(filename, 'w') as f:
                for i in self.d.items():
                    print(i, file=f)

    def test(self):
        self.put("bob", "1")
        self.put("/bar", "1")
        self.put("/foo", "1")
        print(self.d)
        x = self.get_prefix("/b")
        print("x {}".format(x))
        self.delete_prefix("/")
        print(self.d)

if __name__ == "__main__":
    n = NoetcdClient()
    n.test()
