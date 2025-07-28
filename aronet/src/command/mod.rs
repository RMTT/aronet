mod birdcl;
mod daemon;
mod swanctl;

use crate::utils::configuration::{Config, Registry};
use birdcl::BirdclArgs;
use clap::{Parser, Subcommand};
use daemon::DaemonArgs;
use swanctl::SwanctlArgs;

const CLI_ABOUT: &'static str = "aronet cli tool";
const DEFAULT_CONFIG_PATH: &'static str = "/etc/aronet/config.json";
const DEFAULT_REGISTRY_PATH: &'static str = "/etc/aronet/registry.json";

#[derive(Parser, Debug)]
#[command(version, long_about = CLI_ABOUT, arg_required_else_help(true))]
struct Cli {
    #[arg[short, long, default_value = DEFAULT_CONFIG_PATH]]
    config: String,

    #[arg[short, long, default_value = DEFAULT_REGISTRY_PATH]]
    registry: String,

    #[command(subcommand)]
    command: CommandType,
}

#[derive(Debug, Subcommand)]
enum CommandType {
    Daemon(DaemonArgs),
    Swanctl(SwanctlArgs),
    Birdcl(BirdclArgs),
}

pub fn run() {
    let cli = Cli::parse();

    match &cli.command {
        CommandType::Daemon(args) => {
            let config = Config::parse(&cli.config).expect("cannot open configuration file");
            let registry = Registry::parse(&cli.registry).expect("cannot open registry file");

            daemon::run(args, &config, &registry);
        }
        CommandType::Swanctl(args) => {
            let config = Config::parse(&cli.config).unwrap();
            swanctl::run(args, &config);
        }
        CommandType::Birdcl(args) => {
            let config = Config::parse(&cli.config).unwrap();
            birdcl::run(args, &config);
        }
    }
}
