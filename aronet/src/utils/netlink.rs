use std::{
    collections::HashMap,
    fmt::{Debug, Display},
    net::IpAddr,
    os::fd::{AsFd, AsRawFd},
};

use futures::stream::TryStreamExt;
use netlink_packet_route::{
    link::LinkFlags,
    route::{RouteAttribute, RouteScope, RouteType},
};
use nix::sched::CloneFlags;
use rtnetlink::{
    Handle, LinkUnspec, LinkVeth, LinkVrf, LinkXfrm, NetworkNamespace,
    RouteMessageBuilder, new_connection, packet_route::link::LinkMessage,
};
use tokio::fs::{self, File};

use super::IpNetwork;

pub struct Netlink {
    handles: HashMap<String, Handle>,
    netns_stack: Vec<std::fs::File>,
}

#[derive(Clone)]
pub struct NetlinkError {
    err: rtnetlink::Error,
    errmsg: String,
}

impl Debug for NetlinkError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.errmsg)
    }
}

impl From<rtnetlink::Error> for NetlinkError {
    fn from(value: rtnetlink::Error) -> Self {
        Self {
            err: value.clone(),
            errmsg: format!("{value}"),
        }
    }
}

impl From<std::io::Error> for NetlinkError {
    fn from(value: std::io::Error) -> Self {
        Self {
            err: rtnetlink::Error::RequestFailed,
            errmsg: format!("{value}"),
        }
    }
}

impl Display for NetlinkError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.errmsg)
    }
}

impl NetlinkError {
    pub fn is_netlink_exist(&self) -> bool {
        match &self.err {
            rtnetlink::Error::NetlinkError(error_message) => {
                if let Some(code) = error_message.code {
                    return i32::from(code) == -17;
                }
                return false;
            }
            _ => false,
        }
    }

    pub fn is_netlink_not_found(&self) -> bool {
        match &self.err {
            rtnetlink::Error::NetlinkError(error_message) => {
                if let Some(code) = error_message.code {
                    return i32::from(code) == -19;
                }
                return false;
            }
            _ => false,
        }
    }

    pub fn new(msg: &str) -> Self {
        Self {
            err: rtnetlink::Error::RequestFailed,
            errmsg: msg.to_string(),
        }
    }
}

type Result<T> = std::result::Result<T, NetlinkError>;

const DEFAULT_HANDLE: &str = "";

impl Netlink {
    pub async fn new() -> Self {
        let (connection, handle, _) = new_connection().expect("cannot create netlink connection");
        tokio::spawn(connection);

        let mut handle_map = HashMap::new();
        handle_map.insert(DEFAULT_HANDLE.to_string(), handle);

        Self {
            handles: handle_map,
            netns_stack: vec![],
        }
    }

    fn handle(&self, name: &str) -> &Handle {
        self.handles.get(name).unwrap()
    }

    pub fn pushns(&mut self, name: &str) -> std::io::Result<()> {
        let orig_f = std::fs::File::open("/proc/self/ns/net")?;
        let new_f = std::fs::File::open(format!("/var/run/netns/{name}"))?;

        nix::sched::setns(new_f.as_fd(), CloneFlags::CLONE_NEWNET)?;

        self.netns_stack.push(orig_f);

        Ok(())
    }

    pub fn popns(&mut self) -> nix::Result<()> {
        if let Some(f) = self.netns_stack.pop() {
            nix::sched::setns(f.as_fd(), CloneFlags::CLONE_NEWNET)?;
        }

        Ok(())
    }

    pub async fn get_link(&self, name: &str, netns: Option<&str>) -> Result<LinkMessage> {
        let mut links = self
            .handle(netns.unwrap_or(DEFAULT_HANDLE))
            .link()
            .get()
            .match_name(name.to_string())
            .execute();

        links
            .try_next()
            .await?
            .ok_or(NetlinkError::new("failed to get link"))
    }

    pub async fn create_vrf(
        &self,
        name: &str,
        table_id: u32,
        address: Vec<IpNetwork>,
    ) -> Result<LinkMessage> {
        self.handle(DEFAULT_HANDLE)
            .link()
            .add(LinkVrf::new(name, table_id).up().build())
            .execute()
            .await?;

        let link = self.get_link(name, None).await?;

        for ip in address {
            self.handle(DEFAULT_HANDLE)
                .address()
                .add(link.header.index, ip.ip, ip.mask)
                .execute()
                .await?;
        }

        Ok(link)
    }

    /// LinkMessage can specify netns fs
    pub async fn create_xfrm(
        &self,
        name: &str,
        id: u32,
        master: Option<&str>,
        netns: Option<&str>,
    ) -> Result<()> {
        let mut master_index = 0;
        if let Some(m) = master {
            let link = self.get_link(m, None).await?;
            master_index = link.header.index;
        }

        let mut xfrm_msg = LinkXfrm::new(name, 0, id)
            .controller(master_index)
            .mtu(1400)
            .up();

        let ns_file: File;
        if let Some(ns_path) = netns {
            ns_file = fs::File::open(format!("/var/run/netns/{ns_path}")).await?;
            xfrm_msg = xfrm_msg.setns_by_fd(ns_file.as_raw_fd());
        }

        let mut xfrm = xfrm_msg.build();
        // bird need interfaces support MULTICAST
        xfrm.header.flags |= LinkFlags::Multicast;
        xfrm.header.change_mask |= LinkFlags::Multicast;

        self.handle(DEFAULT_HANDLE)
            .link()
            .add(xfrm)
            .execute()
            .await?;

        Ok(())
    }

    pub async fn delete_link(&self, name: &str) -> Result<()> {
        let link = self.get_link(name, None).await?;
        self.handle(DEFAULT_HANDLE)
            .link()
            .del(link.header.index)
            .execute()
            .await?;

        Ok(())
    }

    pub async fn create_route(
        &self,
        dest: IpNetwork,
        output: &str,
        gateway: Option<IpAddr>,
        table: Option<u32>,
        priority: Option<u32>,
        kind: Option<RouteType>,
        scope: Option<RouteScope>,
        netns: Option<&str>,
    ) -> Result<()> {
        let mut table_id = 254;
        let handle: &Handle = self.handle(netns.unwrap_or(DEFAULT_HANDLE));

        if table.is_some() {
            table_id = table.unwrap();
        }

        let mut route = RouteMessageBuilder::<IpAddr>::new()
            .table_id(table_id)
            .destination_prefix(dest.formatted_ip(), dest.mask)
            .map_err(|e| NetlinkError::new(&format!("{e}")))?;

        if let Some(g) = gateway {
            if dest.ip.is_ipv4() && g.is_ipv6() {
                // for ipv4 nexthop via ipv6
                let route_message = route.get_mut();
                route_message.attributes.push(RouteAttribute::Via(g.into()));
            } else {
                route = route
                    .gateway(g)
                    .map_err(|e| NetlinkError::new(&format!("{e}")))?;
            }
        }

        if let Some(p) = priority {
            route = route.priority(p);
        }

        if let Some(s) = scope {
            route = route.scope(s);
        }

        let index = self.get_link(output, netns).await?;
        route = route.output_interface(index.header.index);

        if let Some(k) = kind {
            route = route.kind(k);
        }

        handle.route().add(route.build()).execute().await?;

        Ok(())
    }

    pub async fn create_rule(&self, priority: u32, table_id: u32) -> Result<()> {
        self.handle(DEFAULT_HANDLE)
            .rule()
            .add()
            .priority(priority)
            .table_id(table_id)
            .execute()
            .await?;

        Ok(())
    }

    pub async fn create_netns(&mut self, name: &str) -> Result<()> {
        let r = fs::try_exists(format!("/var/run/netns/{name}")).await;
        if r.is_err() || !r.unwrap() {
            NetworkNamespace::add(name.to_string()).await?;
        }

        self.pushns(name)
            .map_err(|e| NetlinkError::new(&format!("{e}")))?;
        let (connection, handle, _) = new_connection().expect("cannot create netlink connection");
        tokio::spawn(connection);
        self.handles.insert(name.to_string(), handle);
        self.popns()
            .map_err(|e| NetlinkError::new(&format!("{e}")))?;
        Ok(())
    }

    pub async fn delete_netns(&self, name: &str) -> Result<()> {
        let r = fs::try_exists(format!("/var/run/netns/{name}")).await;

        if r.is_ok() && r.unwrap() {
            NetworkNamespace::del(name.to_string()).await?;
            Ok(())
        } else {
            Ok(())
        }
    }

    pub async fn create_veth(
        &mut self,
        name: &str,
        peer_name: &str,
        peer_netns: Option<&str>,
        address: Option<&Vec<IpNetwork>>,
        peer_address: Option<&Vec<IpNetwork>>,
    ) -> Result<()> {
        let mut veth_msg = LinkVeth::new(peer_name, name);

        let ns_file: File;
        if let Some(peer_ns) = peer_netns {
            ns_file = fs::File::open(format!("/var/run/netns/{peer_ns}")).await?;

            veth_msg = veth_msg.setns_by_fd(ns_file.as_raw_fd());
        }

        self.handle(DEFAULT_HANDLE)
            .link()
            .add(veth_msg.build())
            .execute()
            .await?;

        if let Some(addrs) = address {
            let link = self.get_link(name, None).await?;
            for ip in addrs {
                self.handle(DEFAULT_HANDLE)
                    .address()
                    .add(link.header.index, ip.ip, ip.mask)
                    .execute()
                    .await?;
            }
        }
        self.handle(DEFAULT_HANDLE)
            .link()
            .set(LinkUnspec::new_with_name(name).up().build())
            .execute()
            .await?;

        // configure peer interface
        if let Some(peer_addrs) = peer_address {
            let link = self.get_link(peer_name, peer_netns).await?;
            for ip in peer_addrs {
                self.handle(peer_netns.unwrap_or(DEFAULT_HANDLE))
                    .address()
                    .add(link.header.index, ip.ip, ip.mask)
                    .execute()
                    .await?;
            }
        }
        self.handle(peer_netns.unwrap_or(DEFAULT_HANDLE))
            .link()
            .set(LinkUnspec::new_with_name(peer_name).up().build())
            .execute()
            .await?;

        Ok(())
    }

    pub async fn delete_route_from_outdev(&self, name: &str) -> Result<()> {
        let iface = self.get_link(name, None).await?;
        let mut routes = self
            .handle(DEFAULT_HANDLE)
            .route()
            .get(RouteMessageBuilder::<IpAddr>::new().build())
            .execute();

        'outer: while let Some(route) = routes.try_next().await? {
            for attr in &route.attributes {
                match attr {
                    netlink_packet_route::route::RouteAttribute::Oif(id) => {
                        if *id != iface.header.index {
                            continue 'outer;
                        }
                    }
                    _ => {}
                }
            }

            self.handle(DEFAULT_HANDLE)
                .route()
                .del(route)
                .execute()
                .await?;
        }

        Ok(())
    }

    pub async fn move_link_to_netns(&self, name: &str, netns: &str) -> Result<()> {
        let netns_file = File::open(format!("/var/run/netns/{netns}")).await?;
        self.handle(DEFAULT_HANDLE)
            .link()
            .set(
                LinkUnspec::new_with_name(name)
                    .setns_by_fd(netns_file.as_raw_fd())
                    .up()
                    .build(),
            )
            .execute()
            .await?;

        Ok(())
    }
}

#[cfg(test)]
mod test {
    use std::str::FromStr;

    use super::*;

    #[tokio::test]
    #[ignore = ""]
    async fn create_and_delete_netns() {
        let mut nl = Netlink::new().await;

        let r = nl.create_netns("aronet-test").await;
        assert!(
            r.is_ok(),
            "failed to create netns \"aronet-test\": {}",
            r.err().unwrap()
        );
        let r = nl.delete_netns("aronet-test").await;
        assert!(
            r.is_ok(),
            "failed to delete netns \"aronet-test\": {}",
            r.err().unwrap()
        );
    }

    #[tokio::test]
    async fn create_veth_peer() {
        let mut nl = Netlink::new().await;

        let r = nl.create_netns("aronet-test").await;
        assert!(
            r.is_ok(),
            "failed to create netns \"aronet-test\": {}",
            r.err().unwrap()
        );

        let r = nl
            .create_veth(
                "aronet-test",
                "aronet-test",
                Some("aronet-test"),
                Some(&vec![IpNetwork {
                    ip: IpAddr::from_str("127.1.1.1").unwrap(),
                    mask: 32,
                }]),
                Some(&vec![IpNetwork {
                    ip: IpAddr::from_str("127.1.1.2").unwrap(),
                    mask: 32,
                }]),
            )
            .await;
        assert!(
            r.is_ok(),
            "failed to create veth pair \"aronet-test\": {}",
            r.err().unwrap()
        );

        let r = nl.delete_netns("aronet-test").await;
        assert!(
            r.is_ok(),
            "failed to delete netns \"aronet-test\": {}",
            r.err().unwrap()
        );
    }
}
