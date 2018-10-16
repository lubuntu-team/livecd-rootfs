#!/usr/bin/python3

"""
This file parses the seed.yaml file for the chroot and appends it to the
given manifest file.
"""

import re
import sys
import yaml
import os.path


def log(msg):
    sys.stderr.write("snap_seed_parse: {}\n".format(msg))


log("Parsing seed.yaml")

CHROOT_ROOT = sys.argv[1] if len(sys.argv) > 1 and len(sys.argv[1]) > 0 \
                          else ''
'''The chroot rooth path should be passed in by the caller'''
log("CHROOT_ROOT: {}".format(CHROOT_ROOT))

if len(CHROOT_ROOT) > 0 and CHROOT_ROOT[-1] == '/':
    CHROOT_ROOT = CHROOT_ROOT[:-1]
YAML_PATH = CHROOT_ROOT + '/var/lib/snapd/seed/seed.yaml'
'''This is where we expect to find the seed.yaml file'''
LINE_PREFIX = 'snap:'
'''Snaps are prepended with this string in the manifest'''

log("yaml path: {}".format(YAML_PATH))
if not os.path.isfile(YAML_PATH):
    log("yaml path not found.")
    exit(1)
else:
    log("yaml path found.")

# Open the seed.yaml and ingest its contents
with open(YAML_PATH, 'r') as fh:
    yaml_lines = yaml.load(fh)['snaps']

to_write = ''
# Loop over dict items, generating one manifest line from each
# triplet
for item in yaml_lines:
    filestring = item['file']
    revision = filestring[filestring.rindex('_')+1:]
    revision = re.sub(r'[^0-9]', '', revision)
    to_write += "{}{}\t{}\t{}\n".format(LINE_PREFIX,
                                        item['name'],
                                        item['channel'],
                                        revision,
                                        )

# write accumulated text to stdout for redirection
print(to_write.strip('\n'))
