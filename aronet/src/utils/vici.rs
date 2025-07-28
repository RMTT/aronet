use std::{
    collections::HashMap,
    ops::{Deref, DerefMut},
    path::Path,
};

use futures::stream::TryStreamExt;
use futures::{io, pin_mut};
use serde::{Deserialize, Serialize, de::Visitor};

pub struct Client(rsvici::Client);

impl Deref for Client {
    type Target = rsvici::Client;

    fn deref(&self) -> &Self::Target {
        &self.0
    }
}

impl DerefMut for Client {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.0
    }
}

#[derive(Debug, Deserialize)]
pub struct Version {
    daemon: String,
    version: String,
    sysname: String,
    release: String,
    machine: String,
}

#[derive(Debug)]
pub struct Updown {
    pub up: Option<bool>,
    pub ike_sas: HashMap<String, IkeSa>,
}

impl<'de> Deserialize<'de> for Updown {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        deserializer.deserialize_map(UpdownVisitor::new())
    }
}

struct UpdownVisitor {}
impl UpdownVisitor {
    pub fn new() -> Self {
        UpdownVisitor {}
    }
}

impl<'de> Visitor<'de> for UpdownVisitor {
    type Value = Updown;

    fn expecting(&self, formatter: &mut std::fmt::Formatter) -> std::fmt::Result {
        formatter.write_str("Updown Struct")
    }

    fn visit_map<A>(self, mut map: A) -> Result<Self::Value, A::Error>
    where
        A: serde::de::MapAccess<'de>,
    {
        let mut up: Option<bool> = None;
        let mut ike_sas: HashMap<String, IkeSa> = HashMap::new();
        while let Some(key) = map.next_key::<String>()? {
            if key == "up" {
                up = Some(map.next_value::<bool>()?);
            } else {
                let sa = map.next_value::<IkeSa>()?;
                ike_sas.insert(key, sa);
            }
        }

        Ok(Updown { up, ike_sas })
    }
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub struct IkeSa {
    pub if_id_in: String,
    pub if_id_out: String,
    pub local_id: String,
    pub remote_id: String,
}

#[derive(Deserialize, Debug)]
struct CommonResponse {
    success: bool,
    errmsg: Option<String>,
}

impl CommonResponse {
    pub fn ok_or(&self) -> io::Result<()> {
        if self.success {
            Ok(())
        } else {
            Err(io::Error::new(
                std::io::ErrorKind::Other,
                self.errmsg.clone().unwrap_or(String::from("")),
            ))
        }
    }
}

#[derive(Debug, Serialize)]
struct Key<'a, 'b> {
    r#type: &'a str,
    data: &'b str,
}

#[derive(Debug, Serialize)]
struct Authentication {
    auth: &'static str,
    pubkeys: Vec<String>,
    id: String,
}

#[derive(Debug, Serialize)]
struct Child {
    local_ts: Vec<String>,
    remote_ts: Vec<String>,
    mode: &'static str,
    dpd_action: &'static str,
    start_action: &'static str,
    close_action: &'static str,
}

#[derive(Debug, Serialize)]
struct Connection {
    version: u32,
    local_addrs: Vec<String>,
    remote_addrs: Vec<String>,
    local_port: u16,
    remote_port: u16,
    encap: bool,
    mobike: bool,
    dpd_delay: u64,
    keyingtries: u32,
    unique: &'static str,
    if_id_in: &'static str,
    if_id_out: &'static str,
    local: Authentication,
    remote: Authentication,
    children: HashMap<&'static str, Child>,
}

#[derive(Debug)]
pub struct PeerConfig<'a> {
    pub id: &'a str,
    pub addrs: Vec<String>,
    pub port: u16,
    pub pubkey: &'a str,
}

impl Client {
    pub async fn connect<P: AsRef<Path>>(path: P) -> io::Result<Client> {
        let c = rsvici::unix::connect(path).await?;

        Ok(Client(c))
    }

    pub async fn version(&mut self) -> io::Result<Version> {
        let v: Version = self.request("version", ()).await?;

        Ok(v)
    }

    pub async fn get_conns(&mut self) -> io::Result<Vec<String>> {
        #[derive(Debug, Deserialize)]
        struct Conns {
            conns: Vec<String>,
        }

        let r: Conns = self.request("get-conns", ()).await?;

        Ok(r.conns)
    }

    pub async fn load_key(&mut self, data: &str) -> io::Result<()> {
        let key = Key {
            r#type: "any",
            data,
        };

        let r: CommonResponse = self.request("load-key", key).await?;

        r.ok_or()
    }

    pub async fn load_conn(
        &mut self,
        name: &str,
        local: PeerConfig<'_>,
        remote: PeerConfig<'_>,
    ) -> io::Result<()> {
        let conn = Connection {
            version: 2,
            local_addrs: local.addrs,
            remote_addrs: remote.addrs,
            local_port: local.port,
            remote_port: remote.port,
            encap: true,
            mobike: false,
            dpd_delay: 10,
            keyingtries: 0,
            unique: "replace",
            if_id_in: "%unique",
            if_id_out: "%unique",
            local: Authentication {
                auth: "pubkey",
                pubkeys: vec![local.pubkey.to_string()],
                id: local.id.to_string(),
            },
            remote: Authentication {
                auth: "pubkey",
                pubkeys: vec![remote.pubkey.to_string()],
                id: remote.id.to_string(),
            },
            children: HashMap::from([(
                "default",
                Child {
                    local_ts: vec!["0.0.0.0/0".to_string(), "::/0".to_string()],
                    remote_ts: vec!["0.0.0.0/0".to_string(), "::/0".to_string()],
                    mode: "tunnel",
                    dpd_action: "restart",
                    start_action: "none",
                    close_action: "none",
                },
            )]),
        };

        let r: CommonResponse = self
            .request("load-conn", HashMap::from([(name, conn)]))
            .await?;
        r.ok_or()
    }

    pub async fn unload_conn(&mut self, name: &str) -> io::Result<()> {
        #[derive(Serialize)]
        struct Msg<'a> {
            name: &'a str,
        }

        let msg = Msg { name };
        let r: CommonResponse = self.request("unload-conn", msg).await?;
        r.ok_or()
    }

    pub async fn initiate(&mut self, name: &str) -> io::Result<()> {
        #[derive(Serialize)]
        struct Msg<'a> {
            child: &'a str,
            ike: &'a str,
            timeout: i32,
            init_limits: bool,
        }

        let msg = Msg {
            ike: name,
            child: "default",
            timeout: -1,
            init_limits: false,
        };
        let r: CommonResponse = self.request("initiate", msg).await?;
        r.ok_or()
    }

    pub async fn list_sas(&mut self) -> Result<HashMap<String, IkeSa>, Box<dyn std::error::Error>> {
        let sas = self.stream_request::<(), HashMap<String, IkeSa>>("list-sas", "list-sa", ());
        pin_mut!(sas);

        let mut s: HashMap<String, IkeSa> = HashMap::new();

        while let Some(t) = sas.try_next().await? {
            for (k, v) in t {
                s.insert(k, v);
            }
        }

        Ok(s)
    }
}
