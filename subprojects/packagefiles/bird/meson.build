project('bird', 'c', meson_version : '>=0.56.0')

autoheader = find_program('autoheader', required: true)
autoconf = find_program('autoconf', required: true)
find_program('make', required: true)

run_command(autoheader, check: true)
run_command(autoconf, check: true)

configure_options = [
  '--with-protocols=babel,static',
  '--with-runtimedir=/var/run/aronet',
]

run_command('./configure', configure_options, check: true)

custom_target('bird',
  command: [ './build.sh', '@CURRENT_SOURCE_DIR@', '@OUTDIR@' ],
  build_by_default: true,
  install: true,
  install_dir: 'libexec',
  output: [ 'bird', 'birdcl' ]
  )
