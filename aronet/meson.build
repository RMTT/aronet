find_program('cargo', required: true)
sed = find_program('sed', required: true)

version = meson.project_version()
build_type = get_option('buildtype')

custom_target('aronet',
  command: [ './build.sh', build_type, version, '@CURRENT_SOURCE_DIR@', '@OUTDIR@' ],
  build_by_default: true,
  install: true,
  install_dir: 'bin',
  install_tag: ['bin'],
  output: [ 'aronet' ]
  )
