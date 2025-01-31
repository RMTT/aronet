project(
    'aronet',
    version: '0.0.1',
    meson_version: '>=0.63.0',
    default_options: [
      'python.install_env=auto'
    ]
)

pymod = import('python')
python = pymod.find_installation('python',
  modules: ['vici', 'json']
)
python.dependency()

python_sources = [
  'aronet/__init__.py'
]

python.install_sources(python_sources, subdir: 'aronet')

# strongswan related
subproject('strongswan')

# babeld related
subproject('babeld')

custom_target('aronet',
  input: ['aronet/main.py'],
  command: ['cp', '@INPUT@', '@OUTPUT@'],
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'r-xr-xr-x',
  output: 'aronet')


summary({'bindir': get_option('bindir'),
        'libdir': get_option('libdir'),
        'datadir': get_option('datadir'),
        'libexecdir': get_option('libexecdir'),
        })
