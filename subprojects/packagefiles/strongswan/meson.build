project('strongswan', 'c', meson_version : '>=0.56.0')

find_program('make', required: true)

run_command('./autogen.sh', check: true)

configure_options = [
  '--enable-static',
  '--disable-shared',
  '--enable-static',
  '--enable-monolithic',
  '--with-piddir=/var/run/aronet',
  '--disable-x509',
  '--disable-revocation',
  '--disable-constraints',
  '--disable-pgp',
  '--disable-dnskey',
  '--disable-sshkey',
  '--disable-xcbc',
  '--disable-cmac',
  '--disable-resolve',
  '--disable-xauth-generic'
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
elif build_machine.system() == 'linux'
  configure_options += []
endif

run_command('./configure', configure_options, check: true)

pymod = import('python')
python = pymod.find_installation('python')
custom_target('strongswan',
  command: ['./build.sh', '@CURRENT_SOURCE_DIR@', '@OUTDIR@'],
  build_by_default: true,
  install: true,
  install_dir: python.get_install_dir() / 'aronet/libexec',
  output: [ 'charon', '_updown', 'swanctl' ]
  )
