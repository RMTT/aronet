use crate::utils::AddressFamily;
use std::{
    env::current_exe,
    net::{IpAddr, Ipv4Addr, Ipv6Addr},
    path::PathBuf,
    str::FromStr,
};

use serde::{Deserialize, Serialize};

use super::IpNetwork;

#[derive(Serialize, Deserialize, Debug)]
pub struct Config {
    pub private_key: String,
    pub organization: String,
    pub common_name: String,
    pub daemon: DaemonConfig,
    pub endpoints: Vec<EndpointsConfig>,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct DaemonConfig {
    pub extra_network: Option<Vec<IpNetwork>>,
    pub network: IpNetwork,
    #[serde(default)]
    pub mode: DaemonMode,
    pub extra_ip: Option<Vec<IpNetwork>>,
    pub runtime_dir: Option<String>,
    pub charon_path: Option<String>,
    pub bird_path: Option<String>,
    pub ifname: Option<String>,
    pub route_table: Option<u32>,
    pub netns_name: Option<String>,
}

#[derive(Serialize, Deserialize, Debug, Clone, Copy, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum DaemonMode {
    Netns,
    Vrf,
}

impl Default for DaemonMode {
    fn default() -> Self {
        return Self::Vrf;
    }
}

#[derive(Serialize, Deserialize, Debug)]
pub struct EndpointsConfig {
    pub address: Option<String>,
    pub port: u16,
    pub serial_number: u32,
    pub address_family: Option<AddressFamily>,
}

const DEFAULT_RUNTIME_DIR: &'static str = "/var/run/aronet";

impl EndpointsConfig {
    pub fn is_address_valid(&self) -> bool {
        !(self.address.is_none() && self.address_family.is_none())
    }

    pub fn address_family(&self) -> AddressFamily {
        if let Some(i) = &self.address {
            let ip_result = IpAddr::from_str(&i);

            // address could be domain name
            if let Ok(ip) = ip_result {
                if ip.is_ipv4() {
                    return AddressFamily::Ip4;
                } else {
                    return AddressFamily::Ip6;
                }
            }
        }
        if let Some(i) = self.address_family {
            i
        } else {
            // default address family
            AddressFamily::Ip4
        }
    }

    pub fn get_address(&self) -> Vec<String> {
        if self.address.is_some() {
            vec![self.address.clone().unwrap()]
        } else {
            vec![]
        }
    }

    pub fn is_address_public(&self) -> bool {
        !self.address.is_none()
    }
}

impl Config {
    pub fn parse(path: &str) -> Result<Config, std::io::Error> {
        let config_file = std::fs::File::open(path)?;
        let config: Config = serde_json::from_reader(config_file)?;

        Ok(config)
    }

    pub fn runtime_dir(&self) -> PathBuf {
        if let Some(p) = self.daemon.runtime_dir.as_ref() {
            PathBuf::from(p)
        } else {
            PathBuf::from(DEFAULT_RUNTIME_DIR)
        }
    }

    pub fn charon_pidfile_path(&self) -> PathBuf {
        self.runtime_dir().join("charon.pid")
    }

    pub fn swanctl_conf_dir(&self) -> PathBuf {
        self.runtime_dir().join("swanctl")
    }

    pub fn ifname(&self) -> &str {
        if let Some(name) = &self.daemon.ifname {
            name
        } else {
            "aronet"
        }
    }

    pub fn bird_conf_path(&self) -> PathBuf {
        self.runtime_dir().join("bird.conf")
    }

    pub fn route_table(&self) -> u32 {
        if let Some(table) = self.daemon.route_table {
            table
        } else {
            match self.daemon.mode {
                DaemonMode::Netns => 254,
                DaemonMode::Vrf => 128,
            }
        }
    }

    pub fn charon_path(&self) -> PathBuf {
        if let Some(p) = self.daemon.charon_path.as_ref() {
            PathBuf::from(p)
        } else {
            current_exe()
                .unwrap()
                .parent()
                .unwrap()
                .parent()
                .unwrap()
                .join("libexec")
                .join("aronet")
                .join("charon")
        }
    }

    pub fn bird_path(&self) -> PathBuf {
        if let Some(p) = self.daemon.charon_path.as_ref() {
            PathBuf::from(p)
        } else {
            current_exe()
                .unwrap()
                .parent()
                .unwrap()
                .parent()
                .unwrap()
                .join("libexec")
                .join("aronet")
                .join("bird")
        }
    }

    pub fn birdcl_path(&self) -> PathBuf {
        if let Some(p) = self.daemon.charon_path.as_ref() {
            PathBuf::from(p)
        } else {
            current_exe()
                .unwrap()
                .parent()
                .unwrap()
                .parent()
                .unwrap()
                .join("libexec")
                .join("aronet")
                .join("birdcl")
        }
    }

    pub fn swanctl_path(&self) -> PathBuf {
        current_exe()
            .unwrap()
            .parent()
            .unwrap()
            .parent()
            .unwrap()
            .join("libexec")
            .join("aronet")
            .join("swanctl")
    }

    pub fn vici_socket_path(&self) -> PathBuf {
        self.runtime_dir().join("charon.vici")
    }

    pub fn strongswan_config_path(&self) -> PathBuf {
        self.runtime_dir().join("strongswan.conf")
    }

    pub fn extra_network(&self) -> Vec<IpNetwork> {
        let r: Vec<IpNetwork> = vec![];

        if let Some(networks) = &self.daemon.extra_network {
            networks.clone()
        } else {
            r
        }
    }

    pub fn netns_name(&self) -> String {
        if let Some(name) = self.daemon.netns_name.as_ref() {
            name.clone()
        } else {
            "aronet".to_string()
        }
    }

    pub fn main_network(&self) -> IpNetwork {
        let orig = (self.daemon.network.to_bits() & self.daemon.network.mask_bits()) + 1;

        if self.daemon.network.ip.is_ipv4() {
            IpNetwork {
                ip: IpAddr::V4(Ipv4Addr::from_bits(orig.try_into().unwrap())),
                mask: self.daemon.network.mask,
            }
        } else {
            IpNetwork {
                ip: IpAddr::V6(Ipv6Addr::from_bits(orig.try_into().unwrap())),
                mask: self.daemon.network.mask,
            }
        }
    }

    pub fn peer_network(&self) -> IpNetwork {
        let orig = (self.daemon.network.to_bits() & self.daemon.network.mask_bits()) + 2;

        if self.daemon.network.ip.is_ipv4() {
            IpNetwork {
                ip: IpAddr::V4(Ipv4Addr::from_bits(orig.try_into().unwrap())),
                mask: self.daemon.network.mask,
            }
        } else {
            IpNetwork {
                ip: IpAddr::V6(Ipv6Addr::from_bits(orig.try_into().unwrap())),
                mask: self.daemon.network.mask,
            }
        }
    }
}

pub type Registries = Vec<Registry>;

#[derive(Serialize, Deserialize, Debug)]
pub struct Registry {
    pub public_key: String,
    pub organization: String,
    pub nodes: Vec<NodeConfig>,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct Remarks {
    pub network: IpNetwork,
    #[serde(default = "Vec::new")]
    pub extra_network: Vec<IpNetwork>,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct NodeConfig {
    pub common_name: String,
    pub endpoints: Vec<EndpointsConfig>,
    pub remarks: Remarks,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct RemarkConfig;

impl Registry {
    pub fn parse(path: &str) -> Result<Registries, std::io::Error> {
        let registry_file = std::fs::File::open(path)?;
        let registry: Vec<Registry> = serde_json::from_reader(registry_file)?;

        Ok(registry)
    }
}

pub fn build_id(organization: &str, common_name: &str, endpoint: &EndpointsConfig) -> String {
    format!(
        "O={organization},CN={common_name},serialNumber={}",
        endpoint.serial_number
    )
}
