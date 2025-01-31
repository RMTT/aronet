project('strongswan', 'c', meson_version : '>=0.56.0')

run_command('./autogen.sh', check: true)

mod = import('unstable-external_project')

configure_options = [
  '--enable-static'
  ]

if build_machine.system() == 'darwin'
  configure_options += [
    '--disable-kernel-netlink',
    '--enable-kernel-pfroute',
    '--enable-kernel-pfkey',
    '--disable-gmp',
    '--enable-openssl',
    '--enable-osx-attr',
    '--disable-scripts'
    ]
else
  configure_options += []
endif

run_command('./configure', configure_options, check: true)

custom_target('strongswan',
  command: ['./build.sh', '@CURRENT_SOURCE_DIR@', '@OUTPUT@'],
  build_by_default: true,
  install: true,
  install_dir: get_option('libexecdir') + '/aronet',
  output: 'charon'
  )
