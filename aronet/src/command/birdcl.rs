use std::{
    os::unix::process::CommandExt,
    process::{self, Stdio},
};

use clap::Args;

use crate::utils::configuration::Config;

#[derive(Args, Debug)]
pub struct BirdclArgs {
    #[arg(trailing_var_arg(true), allow_hyphen_values(true))]
    args: Option<Vec<String>>,
}

pub fn run(args: &BirdclArgs, config: &Config) {
    let mut p = process::Command::new(config.birdcl_path().as_path());
    p.stdout(Stdio::inherit());
    p.stderr(Stdio::inherit());

    if let Some(a) = &args.args {
        p.args(a);
    }

    let _ = p.exec();
}
