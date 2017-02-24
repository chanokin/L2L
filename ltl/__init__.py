from collections import OrderedDict
from warnings import warn

import functools

__author__ = 'anand'


def static_vars(**kwargs):
    """
    Provides functionality similar to static in C/C++ for functions that use this decorator
    :param kwargs:
    :return:
    """
    def decorate(func):
        for k in kwargs:
            setattr(func, k, kwargs[k])
        return func
    return decorate


class sdictm(object):
    """
    A dictionary which allows accessing it's values using a dot notation. i.e. `d['a']` can be accessed as `d.a`
    Mutable version
    """
    _INSTANCE_VAR_LIST = ['_data']

    def __init__(self, obj):
        self._data = OrderedDict()
        assert obj is not None
        if isinstance(obj, dict):
            for key, val in obj.items():
                if isinstance(val, dict):
                    self._data[key] = self.__class__(val)
                elif isinstance(val, list):
                    self._data[key] = []
                    for v in val:
                        if isinstance(v, dict):
                            self._data[key].append(self.__class__(v))
                        else:
                            self._data[key] = val
                else:
                    self._data[key] = val
        else:
            raise RuntimeError("should be initialized with a dictionary only")
        assert isinstance(self._data, dict)

    def __getattr__(self, attr):
        if attr == '__getstate__':
            raise AttributeError()
        if attr in self._INSTANCE_VAR_LIST:
            return object.__getattribute__(self, attr)
        ret = self._data.get(attr)
        if ret is None:
            warn("Returning None value for {}".format(attr), stacklevel=2)
        return ret

    def __getitem__(self, key):
        return self.__getattr__(key)

    def __set__(self, key, value):
            self._data[key] = value

    def __setitem__(self, key, value):
        self.__set__(key, value)

    def __setattr__(self, attr, value):
        if attr in self._INSTANCE_VAR_LIST:
            object.__setattr__(self, attr, value)
        else:
            self._data[attr] = value

    def get(self, key, default_value):
        value = self[key]
        if value is None:
            return default_value
        else:
            return value

    def keys(self):
        return self._data.keys()

    def todict(self):
        dic_data = OrderedDict()
        for key, value in self._data.items():
            if isinstance(value, sdictm):
                dic_data[key] = value.todict()
            elif isinstance(value, list):
                dic_data[key] = []
                for v in value:
                    if isinstance(v, sdictm):
                        dic_data[key].append(v.todict())
                    else:
                        dic_data[key].append(v)
            else:
                dic_data[key] = value
        return dic_data

    def copy(self):
        """
        Return a copy of the class. The copy is deep.
        :return:
        """
        return self.__class__(self.todict())

    def update(self, quiet=False, **kwargs):
        """
        Update the dictionary with the values given in the function (only goes one level down)
        :param kwargs:
        :return:
        """

        print = functools.partial(printq, quiet=quiet)

        for key, value in kwargs.items():
            if key in self._data:
                print("Replacing {} with {} for key {}".format(self._data[key], value, key))
            else:
                print("Adding new key {} with value {}".format(key, value))
            self._data[key] = value

        return self

    def apply(self, fn):
        """
        Recursively apply fn on all leaf key, value pairs
        :param fn:
        :return:
        """
        for key, value in self._data.copy().items():
            if isinstance(value, sdictm):
                value.apply(fn)
            elif isinstance(value, list):
                contains_sdictm = False
                for i, v in enumerate(value):
                    if isinstance(v, sdictm):
                        v.apply(fn)
                        contains_sdictm = True
                if not contains_sdictm:
                    fn(self._data, key, value)
            else:
                fn(self._data, key, value)

    def frozen(self):
        return sdict(self.todict())


class sdict(sdictm):
    """
    Immutable version of :class:`~ltl.sdictm`
    """
    def __set__(self, attr, value):
        raise RuntimeError("Immutable dictionary")

    def __setattr__(self, attr, value):
        if attr in self._INSTANCE_VAR_LIST:
            object.__setattr__(self, attr, value)
        else:
            raise RuntimeError("Immutable dictionary")

    def update(self, **kwargs):
        raise RuntimeError("Immutable dictionary")

    def apply(self, fn):
        raise RuntimeError("Immutable dictionary")


class IndivParamSpec:
    """
    This is a service that translates between a parameter dict and a list based individual based
    on the given specifications

    This allows for convenient specification of parameters for the optimizers via their names.
    The names must bedot separated identifiers representing the parameters full names in the
    pypet trajectory It borrows the sdict interface completely 
    """
    existing_translators = {}

    def __new__(cls, name, spec_tuple_list):
        if name not in IndivParamSpec.existing_translators:
            # Initializing class params_spec
            params_spec = []
            for spec_tuple in spec_tuple_list:
                param_name = spec_tuple[0]
                param_type = spec_tuple[1]
                assert spec_tuple[1] in ['seq', 'scalar'], "The Param type can only be either 'seq' or 'scalar'"
                if spec_tuple[1] == 'seq':
                    param_len = spec_tuple[2]
                else:
                    param_len = 1
                params_spec.append((param_name, param_type, param_len))
        
            new_obj = super(IndivParamSpec, cls).__new__(cls)
            new_obj.name = name
            new_obj.params_spec = params_spec
            IndivParamSpec.existing_translators[name] = new_obj
        else:
            new_obj = IndivParamSpec.existing_translators[name]

        return new_obj

    def __getnewargs__(self):
        return (self.name, self.params_spec)

    def params_to_list(self, ind_params_dict):
        return_list = []
        for par_name, par_type, par_len in self.params_spec:
            if par_type == 'seq':
                return_list.extend(ind_params_dict[par_name])
            elif par_type == 'scalar':
                return_list.append(ind_params_dict[par_name])
        return return_list

    def list_to_params(self, ind_params_list):
        cursor = 0
        return_dict = OrderedDict()
        for par_name, par_type, par_len in self.params_spec:
            if par_type == 'seq':
                return_dict[par_name] = ind_params_list[cursor:cursor+par_len]
                cursor += par_len
            elif par_type == 'scalar':
                return_dict[par_name] = ind_params_list[cursor]
                cursor += 1
        assert cursor == len(ind_params_list), "Incorrect Parameter List length, Somethings not right"
        return return_dict

    def get_param_names(self):
        return tuple(x[0] for x in self.params_spec)
        
    def get_grouped_param_dict(self, paramdict_iter):
        paramdicttuple = tuple(paramdict_iter)
        
        return_dict = OrderedDict({})
        for par_name, _, __ in self.params_spec:
            return_dict[par_name] = []

        for param_dict in paramdicttuple:
            for par_name, _, __ in self.params_spec:
                return_dict[par_name].append(param_dict[par_name])

        return return_dict


def printq(s, quiet):
    if not quiet:
        print(s)


def static_var(varname, value):
    def decorate(func):
        setattr(func, varname, value)
        return func
    return decorate


def get(obj, key, default_value):
    try:
        return obj[key]
    except:
        return default_value


class DummyTrajectory:
    pass
