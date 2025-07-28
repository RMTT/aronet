project(
    'aronet',
    'rust',
    version: '0.1.0-beta1',
    meson_version: '>=1.1',
    default_options: [
    ]
)

subdir('aronet')

#strongswan related
if get_option('strongswan')
  subproject('strongswan')
endif

# bird related
if get_option('bird')
  subproject('bird')
endif
