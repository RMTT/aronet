use std::fs;
use std::{path::PathBuf, process::Stdio};

use base64::Engine;
use base64::prelude::BASE64_STANDARD;
use futures::TryStreamExt;
use tokio::fs::OpenOptions;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::join;
use tokio::time::{Duration, sleep};
use tokio_util::sync::CancellationToken;

use crate::utils::configuration::{Config, DaemonMode, EndpointsConfig, Registries, build_id};
use crate::utils::netlink::{Netlink, NetlinkError};
use crate::utils::vici::{Client, PeerConfig, Updown};
use log::{debug, info, warn};

use super::Daemon;

macro_rules! STRONGSWAN_CONF {
    () => {
        r#"
charon {{
  port = 0
  port_nat_t = 12025
  retransmit_timeout = 30
  retransmit_base = 1

  filelog {{
      stderr {{
          path = stderr
          # to achive realtime log capture
          flush_line = yes
          cfg = 1
          default = 0
      }}
  }}

  plugins {{
    vici {{
      socket = "unix://{}"
    }}
    socket-default {{
      set_source = yes
      set_sourceif = yes
    }}
    dhcp {{
      load = no
    }}
  }}
}}
"#
    };
}

pub struct Strongswan<'a> {
    organizaton: &'a str,
    common_name: &'a str,
    pidfile_path: PathBuf,
    charon_path: PathBuf,
    vici_socket_path: PathBuf,
    strongswan_conf_path: PathBuf,
    swanctl_conf_dir: PathBuf,
    registries: &'a Registries,
    endpoints: &'a Vec<EndpointsConfig>,
    private_key: &'a str,
    ifname: &'a str,
    daemon_mode: DaemonMode,
    netns: String,
    cancel_token: CancellationToken,
}

impl<'a> Strongswan<'a> {
    pub fn new(config: &'a Config, registries: &'a Registries, token: CancellationToken) -> Self
    where
        Self: Sized,
    {
        Strongswan {
            pidfile_path: config.charon_pidfile_path(),
            charon_path: config.charon_path(),
            vici_socket_path: config.vici_socket_path(),
            strongswan_conf_path: config.runtime_dir().join("strongswan.conf"),
            swanctl_conf_dir: config.swanctl_conf_dir(),
            registries,
            endpoints: &config.endpoints,
            organizaton: &config.organization,
            common_name: &config.common_name,
            private_key: &config.private_key,
            ifname: config.ifname(),
            daemon_mode: config.daemon.mode,
            netns: config.netns_name(),
            cancel_token: token,
        }
    }

    pub async fn run_charon(&self) {
        info!("generating configuration of charon...");
        let mut conf_file = OpenOptions::new()
            .write(true)
            .create(true)
            .truncate(true)
            .open(self.strongswan_conf_path.as_path())
            .await
            .unwrap();
        let conf_str = format!(STRONGSWAN_CONF!(), self.vici_socket_path.to_str().unwrap());
        conf_file.write_all(conf_str.as_bytes()).await.unwrap();
        conf_file.shutdown().await.unwrap();

        info!("starting charon...");
        let mut charon = tokio::process::Command::new(self.charon_path.as_path())
            .env(
                "STRONGSWAN_CONF",
                self.strongswan_conf_path.to_str().unwrap(),
            )
            .env("SWANCTL_DIR", self.swanctl_conf_dir.to_str().unwrap())
            .stderr(Stdio::piped())
            .spawn()
            .expect("cannot launch charon");

        let stderr = charon.stderr.take().unwrap();
        let mut stderr_reader = BufReader::new(stderr).lines();

        // catch stderr
        tokio::spawn(async move {
            while let Some(line) = stderr_reader.next_line().await.unwrap() {
                info!("charon: {line}");
            }
        });

        join!(self.listen_updown(), self.init_connections_and_key());

        tokio::select! {
            _ = charon.wait() => {
                warn!("charon exited unexpectedly");
            },
            _ = self.cancel_token.cancelled() => {
                info!("kill strongswan...");
                let _ = charon.kill().await;
            }
        }
    }

    async fn connect_vici(&self) -> Result<Client, std::io::Error> {
        let mut vici;
        loop {
            sleep(Duration::from_secs(1)).await;

            vici = Client::connect(self.vici_socket_path.as_path()).await;

            if vici.is_ok() {
                break;
            }
        }

        vici
    }

    pub async fn handle_updown_event(&self, event: &Updown, nl: &Netlink) {
        debug!("ike-updown: {:?}", event);

        for entry in &event.ike_sas {
            let sa = entry.1;
            let xfrm_name = format!("{}-{}", self.ifname, sa.if_id_in);

            if event.up == Some(true) {
                let r: Result<(), NetlinkError>;
                match self.daemon_mode {
                    DaemonMode::Netns => {
                        // must create xfrm in the netns which charon running, then move this
                        // interface to another netns
                        r = nl
                            .create_xfrm(
                                &xfrm_name,
                                sa.if_id_in.parse::<u32>().unwrap(),
                                None,
                                None,
                            )
                            .await;
                        if nl
                            .move_link_to_netns(&xfrm_name, &self.netns)
                            .await
                            .is_err()
                        {
                            warn!(
                                "moving interface {xfrm_name} to netns {} failed",
                                self.netns
                            )
                        }
                    }
                    DaemonMode::Vrf => {
                        r = nl
                            .create_xfrm(
                                &xfrm_name,
                                sa.if_id_in.parse::<u32>().unwrap(),
                                Some(self.ifname),
                                None,
                            )
                            .await;
                    }
                }
                if let Err(e) = r {
                    warn!("failed to create link {xfrm_name}: {e}");
                }
            } else {
                let r = nl.delete_link(&xfrm_name).await;
                if let Err(e) = r {
                    warn!("failed to delete link {xfrm_name}: {e}");
                }
            }
        }
    }

    pub async fn listen_updown(&self) {
        let mut vici = self.connect_vici().await.unwrap();
        let cancel_token = self.cancel_token.clone();
        info!("updown handler: connection to vici socket was established");

        let mut stream = Box::pin(vici.subscribe::<Updown>("ike-updown"));

        let nl = Netlink::new().await;
        loop {
            tokio::select! {
                v = stream.try_next() => {
                    if let Some(event) = v.unwrap() {
                        self.handle_updown_event(&event, &nl).await;
                    }
                }
                _ = cancel_token.cancelled() => {
                    info!("stop listen updown events...");
                    break;
                }
            }
        }
    }

    /// monitor sas for every 10 seconds. In some case, sa will be removed if charon receives
    /// NO_PROPOSAL_CHOSEN msg, so we need to restart it.
    pub async fn monitor_sas(&self, mut vici: Client, connections_name: &Vec<String>) {
        let cancel_token = self.cancel_token.clone();
        loop {
            let sas_wrap = vici.list_sas().await;

            if sas_wrap.is_err() {
                warn!(
                    "failed to request \"list-sas\": {}",
                    sas_wrap.err().unwrap()
                );
            } else {
                let sas = sas_wrap.unwrap();
                debug!("list-sas: {sas:?}");
                for name in connections_name {
                    if sas.get(name).is_some() {
                        continue;
                    }

                    let r = vici.initiate(&name).await;

                    if let Err(e) = r {
                        warn!("connection {name} was failed to initiate: {e}")
                    }
                }
            }

            tokio::select! {
                _ = cancel_token.cancelled() => {
                    info!("stop monitor sas...");
                    break;
                }
                _ = tokio::time::sleep(Duration::new(10, 0)) => {continue;}
            };
        }
    }

    pub async fn init_connections_and_key(&self) {
        let mut vici = self.connect_vici().await.unwrap();
        info!("connection to vici socket was established");

        // load private key, support string or file path of pem
        let private_key: &str;
        let private_stirng: String;
        if self.private_key.starts_with("-----BEGIN PRIVATE KEY-----") {
            private_key = self.private_key;
        } else {
            private_stirng =
                fs::read_to_string(self.private_key).expect("failed to read private key from file");
            private_key = private_stirng.as_str();
        }
        vici.load_key(&private_key).await.unwrap();

        // load connections
        let local_name = format!("{}-{}", self.organizaton, self.common_name);
        let pubkey_pem = openssl::pkey::PKey::private_key_from_pem(private_key.as_bytes())
            .expect("failed to derive pubkey from private key")
            .public_key_to_pem()
            .expect("failed to derive pubkey from private key");
        let pubkey_str = str::from_utf8(&pubkey_pem).unwrap();
        let mut connections_name: Vec<String> = Vec::new();
        for local in self.endpoints {
            if !local.is_address_valid() {
                warn!(
                    "local endpoint with serialNumber {} has invalid address or address_family",
                    local.serial_number
                );
                continue;
            }

            let local_id = build_id(self.organizaton, self.common_name, local);

            for registry in self.registries {
                for node in &registry.nodes {
                    let node_name = format!("{}-{}", registry.organization, node.common_name);

                    if local_name == node_name {
                        continue;
                    }

                    for remote in &node.endpoints {
                        if local.address_family() != remote.address_family() {
                            continue;
                        }

                        if !remote.is_address_valid() {
                            warn!(
                                "remote endpoint of {}-{} with serialNumber {} has invalid address or address_family",
                                registry.organization, node.common_name, remote.serial_number
                            );
                            continue;
                        }

                        // if local and remote both behind NAT, the connection cannot be established
                        if !local.is_address_public() && !remote.is_address_public() {
                            continue;
                        }

                        let remote_id = build_id(&registry.organization, &node.common_name, remote);
                        let conn_name_ori = format!("{}-{}", &local_id, &remote_id);
                        let conn_name = BASE64_STANDARD.encode(conn_name_ori);
                        let r = vici
                            .load_conn(
                                &conn_name,
                                PeerConfig {
                                    id: &local_id,
                                    addrs: local.get_address(),
                                    port: local.port,
                                    pubkey: pubkey_str,
                                },
                                PeerConfig {
                                    id: &remote_id,
                                    addrs: remote.get_address(),
                                    port: remote.port,
                                    pubkey: &registry.public_key,
                                },
                            )
                            .await;
                        if let Err(e) = r {
                            warn!("connection {conn_name} was failed to load: {e}");
                            continue;
                        }

                        connections_name.push(conn_name);
                    }
                }
            }
        }

        self.monitor_sas(vici, &connections_name).await;
    }
}

impl Daemon for Strongswan<'_> {
    async fn runner(&self) {
        self.run_charon().await
    }
}
