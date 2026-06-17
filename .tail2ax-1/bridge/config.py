# -*- coding: utf-8 -*-
import yaml
import os.path


# define custom tag handler
def join(loader, node):
    return ''.join([str(i) for i in loader.construct_sequence(node)])


# register the tag handler
yaml.add_constructor('!join', join)


def read_config(config_file):
    return yaml.load(open(os.path.abspath(config_file), 'r'), Loader=yaml.Loader)
