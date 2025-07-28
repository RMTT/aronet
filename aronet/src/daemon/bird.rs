use adler2::Adler32;
use std::{path::PathBuf, process::Stdio};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};

use log::info;
use tokio::fs::OpenOptions;
use tokio_util::sync::CancellationToken;

use crate::utils::{IpNetwork, configuration::DaemonMode, netlink::Netlink};

use super::Daemon;

macro_rules! BIRD_CONF {
    () => {
        r#"
log stderr all;
ipv6 sadr table sadr6;
router id {router_id};

protocol device {{
  scan time 5;
}}

protocol kernel {{
  kernel table {route_table};
  learn off;
  ipv6 sadr {{
    export where source = RTS_BABEL;
    import none;
  }};
}}

protocol kernel {{
  kernel table {route_table};
  learn off;
  ipv4 {{
    export where source = RTS_BABEL;
    import none;
  }};
}}

protocol static {{
  ipv4;
  {ipv4_networks}
}}

protocol static {{
  ipv6 sadr;
  {ipv6_networks}
}}

protocol babel {{
  {vrf_statement};
  ipv6 sadr {{
    export all;
    import all;
  }};
  ipv4 {{
    export all;
    import all;
  }};
  interface "{prefix}-*" {{
    type tunnel;
    rxcost 32;
    hello interval 20 s;
    rtt cost 1024;
    rtt max 1024 ms;
    rx buffer 2000;
    check link;
  }};
}}
"#
    };
}

pub struct Bird<'a> {
    conf_path: PathBuf,
    route_table: u32,
    ifname: &'a str,
    networks: Vec<IpNetwork>,
    bird_path: PathBuf,
    daemon_mode: DaemonMode,
    netns: String,
    cancel_token: CancellationToken,
}

impl<'a> Bird<'a> {
    pub fn new(config: &'a crate::utils::configuration::Config, token: CancellationToken) -> Self
    where
        Self: Sized,
    {
        let mut networks = config.extra_network();
        networks.push(config.daemon.network.clone());

        Bird {
            conf_path: config.bird_conf_path(),
            route_table: config.route_table(),
            ifname: config.ifname(),
            networks,
            bird_path: config.bird_path(),
            daemon_mode: config.daemon.mode,
            netns: config.netns_name(),
            cancel_token: token,
        }
    }

    async fn run_bird(&self) {
        let nl = Netlink::new().await;
        let link = nl.get_link(self.ifname, None).await.unwrap();
        let mut router_id: u32 = 0;
        for attr in link.attributes {
            match attr {
                netlink_packet_route::link::LinkAttribute::Address(addr) => {
                    let mut adler = Adler32::new();
                    adler.write_slice(&addr);
                    router_id = adler.checksum();
                    break;
                }
                _ => {
                    continue;
                }
            }
        }

        let mut networks_v4 = String::new();
        let mut networks_v6 = String::new();

        for n in &self.networks {
            if n.ip.is_ipv4() {
                let s = format!("route {n} unreachable;\n");
                networks_v4.push_str(&s);
            } else {
                let s = format!("route {n} from ::/0 unreachable;\n");
                networks_v6.push_str(&s);
            }
        }

        info!("generating configuration of bird...");
        let mut conf_file = OpenOptions::new()
            .write(true)
            .create(true)
            .truncate(true)
            .open(self.conf_path.as_path())
            .await
            .unwrap();
        let mut vrf_statement = "".to_string();
        if self.daemon_mode == DaemonMode::Vrf {
            vrf_statement = format!("vrf \"{}\"", self.ifname);
        }

        let conf_str = format!(
            BIRD_CONF!(),
            route_table = self.route_table,
            prefix = self.ifname,
            ipv4_networks = networks_v4,
            ipv6_networks = networks_v6,
            vrf_statement = vrf_statement,
            router_id = router_id
        );

        conf_file.write_all(conf_str.as_bytes()).await.unwrap();
        conf_file.shutdown().await.unwrap();

        let mut nl = Netlink::new().await;
        if self.daemon_mode == DaemonMode::Netns {
            nl.pushns(&self.netns).unwrap();
        }
        let mut bird = tokio::process::Command::new(self.bird_path.as_path())
            .arg("-c")
            .arg(self.conf_path.as_path())
            .arg("-f")
            .stderr(Stdio::piped())
            .spawn()
            .expect("cannot launch bird");

        if self.daemon_mode == DaemonMode::Netns {
            nl.popns().unwrap();
        }

        let stderr = bird.stderr.take().unwrap();
        let mut stderr_reader = BufReader::new(stderr).lines();

        // catch stderr
        tokio::spawn(async move {
            while let Some(line) = stderr_reader.next_line().await.unwrap() {
                info!("{line}");
            }
        });

        tokio::select! {
            _ = bird.wait() => {}
            _ = self.cancel_token.cancelled() => {
                info!("kill bird...");
                let _ = bird.kill().await;
            }
        }
    }
}

impl<'a> Daemon for Bird<'a> {
    async fn runner(&self) {
        self.run_bird().await;
    }
}
