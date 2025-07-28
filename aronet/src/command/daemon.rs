use crate::daemon::{Daemon, bird::Bird, strongswan::Strongswan};
use crate::utils::IpNetwork;
use crate::utils::configuration::{Config, DaemonMode, Registries};
use crate::utils::netlink::Netlink;
use clap::{Args, ValueEnum};
use futures::join;
use log::{info, warn};
use std::io::ErrorKind;
use std::net::IpAddr;
use std::str::FromStr;
use tokio::signal::unix::{SignalKind, signal};
use tokio_util::sync::CancellationToken;

#[derive(Debug, Args)]
pub struct DaemonArgs {
    #[arg(value_enum)]
    action: Actions,
}

#[derive(ValueEnum, Clone, Debug)]
enum Actions {
    Run,
    Info,
}

struct DaemonState<'a> {
    strongswan: Strongswan<'a>,
    bird: Bird<'a>,
    netlink: Netlink,
    cancel_token: CancellationToken,
    config: &'a Config,
    registries: &'a Registries,
}

impl<'a> DaemonState<'a> {
    async fn handle_signals(&self) {
        let mut sig_int = signal(SignalKind::interrupt()).unwrap();
        let mut sig_term = signal(SignalKind::terminate()).unwrap();

        tokio::select! {
            _ = sig_int.recv() => self.shutdown().await,
            _ = sig_term.recv() => self.shutdown().await,
        }
    }

    async fn shutdown(&self) {
        info!("daemon shutdown...");
        self.cancel_token.cancel();
    }

    async fn clean_resources(&self) {
        info!("cleanup netlink resources of daemon...");
        if self.config.daemon.mode == DaemonMode::Netns {
            info!("trying to delete netns");
            if let Err(err) = self.netlink.delete_netns(&self.config.netns_name()).await {
                if !err.is_netlink_not_found() {
                    warn!("failed to delete netns: {err}");
                }
            }
        } else {
            info!("trying to delete main interface");
            if let Err(err) = self.netlink.delete_link(self.config.ifname()).await {
                if !err.is_netlink_not_found() {
                    warn!("failed to delete main interface: {err}");
                }
            }
        }
    }

    pub async fn start(&mut self) {
        // clean previous netlink resources before start
        self.clean_resources().await;

        self.setup().await;
        join!(
            self.strongswan.runner(),
            self.bird.runner(),
            self.handle_signals()
        );

        self.cancel_token.cancelled().await;
        self.clean_resources().await;
    }

    pub async fn setup(&mut self) {
        // swanctl is under runtime_dir, so this also creates runtime_dir
        tokio::fs::create_dir_all(self.config.swanctl_conf_dir().as_path())
            .await
            .unwrap_or_else(|err| {
                if err.kind() != ErrorKind::AlreadyExists {
                    panic!(
                        "failed to create directory {:?}: {err:?}",
                        self.config.swanctl_conf_dir().as_path()
                    );
                }
            });

        let mut if_ips: Vec<crate::utils::IpNetwork> = vec![self.config.main_network()];
        if let Some(extra_ips) = self.config.daemon.extra_ip.as_ref() {
            for i in extra_ips {
                if_ips.push(*i);
            }
        }

        info!("creating main interface {}", self.config.ifname());
        match self.config.daemon.mode {
            // in netns mode, the main interface is a veth pair
            crate::utils::configuration::DaemonMode::Netns => {
                self.netlink
                    .create_netns(&self.config.netns_name())
                    .await
                    .expect("failed to create netns");

                self.netlink
                    .create_veth(
                        self.config.ifname(),
                        self.config.ifname(),
                        Some(&self.config.netns_name()),
                        Some(&if_ips),
                        Some(&vec![self.config.peer_network()]),
                    )
                    .await
                    .map_err(|e| format!("{e}"))
                    .expect("cannot create veth");

                // direct traffic out of netns
                self.netlink
                    .create_route(
                        IpNetwork::from_str("::/0").unwrap(),
                        self.config.ifname(),
                        None,
                        None,
                        None,
                        None,
                        None,
                        Some(&self.config.netns_name()),
                    )
                    .await
                    .map_err(|e| format!("{e}"))
                    .expect("creating default route for ipv6 in netns failed");

                self.netlink
                    .create_route(
                        IpNetwork::from_str("0.0.0.0/0").unwrap(),
                        self.config.ifname(),
                        Some(self.config.main_network().ip),
                        None,
                        None,
                        None,
                        None,
                        Some(&self.config.netns_name()),
                    )
                    .await
                    .expect("creating default route for ipv4 in netns failed");
            }
            crate::utils::configuration::DaemonMode::Vrf => {
                // in vrf mode, the main interface is a vrf device
                self.netlink
                    .create_vrf(self.config.ifname(), self.config.route_table(), if_ips)
                    .await
                    .map_err(|e| format!("failed to create vrf {}: {e}", self.config.ifname()))
                    .unwrap();
            }
        }

        // common things for netns and vrf mode
        let local_name = format!("{}-{}", self.config.organization, self.config.common_name);
        let mut gateway: Option<IpAddr> = None;
        if self.config.daemon.mode == DaemonMode::Netns {
            gateway = Some(self.config.peer_network().ip);
        }
        for registry in self.registries {
            for node in &registry.nodes {
                let remote_name = format!("{}-{}", registry.organization, node.common_name);

                if local_name == remote_name {
                    continue;
                }

                let mut networks = node.remarks.extra_network.clone();
                networks.push(node.remarks.network);
                for net in networks {
                    self.netlink
                        .create_route(
                            net,
                            self.config.ifname(),
                            gateway,
                            None,
                            None,
                            None,
                            None,
                            None,
                        )
                        .await
                        .map_err(|e| format!("{e}"))
                        .expect("creating route failed");
                }
            }
        }
    }
}

#[tokio::main(flavor = "current_thread")]
async fn _run(args: &DaemonArgs, config: &Config, registries: &Registries) {
    let nl = Netlink::new().await;
    let token = CancellationToken::new();

    let mut state = DaemonState {
        strongswan: Strongswan::new(config, registries, token.clone()),
        bird: Bird::new(config, token.clone()),
        netlink: nl,
        cancel_token: token,
        config,
        registries,
    };

    match args.action {
        Actions::Run => {
            state.start().await;
        }
        Actions::Info => {
            todo!()
        }
    }
}

pub fn run(args: &DaemonArgs, config: &Config, registries: &Registries) {
    _run(args, config, registries);
}
