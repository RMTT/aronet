project('babeld', 'c', meson_version : '>=0.56.0')


os_args = ''
if build_machine.system() == 'darwin'
  os_args = 'LDLIBS='
endif


custom_target('babeld',
  command: ['./build.sh', '@CURRENT_SOURCE_DIR@', '@OUTPUT@', os_args],
  build_by_default: true,
  install: true,
  install_dir: get_option('libexecdir') + '/aronet',
  install_mode: 'r-xr-xr-x',
  output: 'babeld')
