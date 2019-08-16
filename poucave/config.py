import toml


def load(configfile):
    return toml.load(open(configfile, "r"))
