pub mod configuration;
pub mod netlink;
pub mod vici;

use std::{
    fmt::Display,
    net::{IpAddr, Ipv4Addr, Ipv6Addr},
    str::FromStr,
};

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy)]
pub struct IpNetwork {
    pub ip: IpAddr,
    pub mask: u8,
}

impl Serialize for IpNetwork {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        let r = format!("{}/{}", &self.ip, &self.mask);
        serializer.serialize_str(&r)
    }
}

impl<'de> Deserialize<'de> for IpNetwork {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        let s = String::deserialize(deserializer)?;
        let components: Vec<&str> = s.split('/').collect();
        let ip = IpAddr::from_str(components[0]).unwrap();

        let mask: u8;
        if components.len() > 1 {
            mask = u8::from_str(components[1]).unwrap();
        } else {
            mask = if ip.is_ipv4() { 32 } else { 128 }
        }

        Ok(IpNetwork { ip, mask })
    }
}

impl Display for IpNetwork {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let mut s = String::new();

        let mask = self.mask_bits();
        let ip_bits = self.to_bits();
        match self.ip {
            IpAddr::V4(_) => {
                let range = Ipv4Addr::from_bits((ip_bits & mask).try_into().unwrap());
                s.push_str(&format!("{}/{}", range, self.mask))
            }
            IpAddr::V6(_) => {
                let range = Ipv6Addr::from_bits(ip_bits & mask);
                s.push_str(&format!("{}/{}", range, self.mask));
            }
        }

        f.write_str(&s)
    }
}

impl FromStr for IpNetwork {
    type Err = std::io::Error;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        let components: Vec<&str> = s.split('/').collect();
        let ip = IpAddr::from_str(components[0]).unwrap();

        let mask: u8;
        if components.len() > 1 {
            mask = u8::from_str(components[1]).unwrap();
        } else {
            mask = if ip.is_ipv4() { 32 } else { 128 }
        }

        Ok(IpNetwork { ip, mask })
    }
}

impl IpNetwork {
    pub fn formatted_ip(&self) -> IpAddr {
        let ip_bits = self.to_bits();
        let mask_bits = self.mask_bits();

        let formatted_bits = ip_bits & mask_bits;
        match self.ip {
            IpAddr::V4(_) => IpAddr::V4(Ipv4Addr::from_bits((formatted_bits).try_into().unwrap())),
            IpAddr::V6(_) => IpAddr::V6(Ipv6Addr::from_bits(formatted_bits)),
        }
    }

    pub fn to_bits(&self) -> u128 {
        match self.ip {
            IpAddr::V4(ipv4_addr) => ipv4_addr.to_bits().into(),
            IpAddr::V6(ipv6_addr) => ipv6_addr.to_bits(),
        }
    }

    pub fn mask_bits(&self) -> u128 {
        let mut mask = 0;
        for _ in 0..self.mask {
            mask <<= 1;
            mask += 1;
        }

        if mask == 0 {
            return mask;
        } else if self.ip.is_ipv4() {
            mask <<= 32 - self.mask;
        } else {
            mask <<= 128 - self.mask;
        }
        mask
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AddressFamily {
    Ip6,
    Ip4,
}

impl Serialize for AddressFamily {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        match &self {
            AddressFamily::Ip6 => serializer.serialize_str("ip6"),
            AddressFamily::Ip4 => serializer.serialize_str("ip4"),
        }
    }
}

impl<'de> Deserialize<'de> for AddressFamily {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        let s = &String::deserialize(deserializer)?[0..];

        match s {
            "ip6" => Ok(Self::Ip6),
            "ip4" => Ok(Self::Ip4),
            _ => Err(serde::de::Error::custom("unknown address_family")),
        }
    }
}

#[cfg(test)]
mod test {
    use std::{
        net::{Ipv4Addr, Ipv6Addr},
        str::FromStr,
    };

    use crate::utils::IpNetwork;

    #[tokio::test]
    async fn test_ipnetwork() {
        let v4_net = IpNetwork {
            ip: std::net::IpAddr::V4(Ipv4Addr::from_str("192.168.128.1").unwrap()),
            mask: 24,
        };
        assert_eq!(format!("{v4_net}"), "192.168.128.0/24");

        let orig = (v4_net.to_bits() & v4_net.mask_bits()) + 2;
        let new_v4_net = IpNetwork {
            ip: std::net::IpAddr::V4(Ipv4Addr::from_bits(orig.try_into().unwrap())),
            mask: v4_net.mask,
        };
        assert_eq!(format!("{}", new_v4_net.ip), "192.168.128.2");

        let v6_net = IpNetwork {
            ip: std::net::IpAddr::V6(Ipv6Addr::from_str("240e::1").unwrap()),
            mask: 60,
        };
        assert_eq!(format!("{v6_net}"), "240e::/60");

        let orig = (v6_net.to_bits() & v6_net.mask_bits()) + 2;
        let new_v6_net = IpNetwork {
            ip: std::net::IpAddr::V6(Ipv6Addr::from_bits(orig.try_into().unwrap())),
            mask: v6_net.mask,
        };
        assert_eq!(format!("{}", new_v6_net.ip), "240e::2");
    }
}
