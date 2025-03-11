project(
    'aronet',
    meson_version: '>=1.1',
    default_options: [
      'prefix=/'
    ]
)

pymod = import('python')
python = pymod.find_installation('python')
python_sources = [
  'aronet/__init__.py',
  'aronet/main.py',
  'aronet/config.py',
  'aronet/util.py',
  'aronet/netlink.py',
  'aronet/cmd/__init__.py',
  'aronet/cmd/base.py',
  'aronet/cmd/daemon.py',
  'aronet/cmd/load.py',
  'aronet/cmd/birdc.py',
  'aronet/cmd/swanctl.py',
  'aronet/daemon/__init__.py',
  'aronet/daemon/strongswan.py',
  'aronet/daemon/backend.py',
  'aronet/daemon/bird.py',
  'aronet/strongswan/__init__.py',
  'aronet/strongswan/client.py',
  'aronet/libexec/updown.sh',
]

python.install_sources(python_sources, preserve_path: true)

#strongswan related
if get_option('strongswan')
  subproject('strongswan')
endif

# bird related
if get_option('bird')
  subproject('bird')
endif
