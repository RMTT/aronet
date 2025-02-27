## Aronet

Auto routed and full mesh overlay network with flexibility based on ipsec, srv6 and babel. Inspired by https://github.com/NickCao/ranet

### Requirements

Linux:
+ kerner >= 4.14
+ enable vrf module
+ firewall port: 6696(babel), 12025(default for node connectivity)
+ enable following sysctl parameters:
	+ `net.netfilter.nf_hooks_lwtunnel`: let packets from srv6 tunnel be processed by netfilter
	+ `sysctl net.ipv6.conf.all.forwarding`
    + `sysctl net.ipv4.ip_forward`
    + `net.core.devconf_inherit_init_net`: optional for network namespace mode, let netns inherit kernel parameters from its parent namespace
    + `net.ipv4.tcp_l3mdev_accept`: optional for vrf mode, let packets be forwarded from aronet vrf accept tcp traffic
    + `net.ipv4.udp_l3mdev_accept`: optional for vrf mode, let packets be forwarded from aronet vrf accept udp traffic

### Usage


To run aronet, you need two files basically:

<details>

<summary> example config.json </summary>

#### `config.json`

 `config.json` contains basic configuration for running aronet, example:
 
 ```json
{
  "private_key": "./test/config/moon/private.pem",
  "organization": "example",
  "common_name": "host-01",
  "daemon": {
    "prefixs": [
      "192.168.128.1/24"
    ],
    "use_netns": false,
    "network": "fd66::1/64" # must be a v6 network with prefix less or equal to 64
  },
  # endpoints are some ip:port pairs for establishing tunnels with other nodes in a registry
  "endpoints": [
    {
      "address": "1.1.1.1",
      "port": 12025,
    },
    {
      "address_family": "ip6",
      "address": null,
      "port": 12025,
      "serial_number": 1
    }
  ]
}
```

</details>

After aronet started, it will create a vrf device(or a network namespace if use netns mode) called `aronet` with address in `daemon.network`, then other nodes will route the traffic of `daemon.prefixs` to your node. The `endpoints` tell other nodes how to connect to your node.

Note that `aronet` will reserve the `{daemon.network}:ffff::/80` range for internal usage. The majority of this range will be used for srv6 actions.

<details>

<summary> example registry.json </summary>

#### `registry.json`

`registry.json` contains information of nodes in a mesh overlay network. And your nodes will connect to the nodes in `registry.json`. example:
```json
[
  {
    "public_key": "-- raw pem of public key --",
    "organization": "example",
    "nodes": [
      {
        "common_name": "host-01",
        "endpoints": [
          {
            "address": "2.2.2.2",
            "port": 12345,
          },
          {
            "address": "::1",
            "port": 12345
          }
        ],
        "remarks": {
          "prefixs": [
            "192.168.128.1/24"
          ],
          "network": "fd66::1/64"
        }
      }
    ]
  },
  {
    "public_key": "-- raw pem of public key --",
    "organization": "example2",
    "nodes": [
      {
        "common_name": "host-01",
        "endpoints": [
          {
            "address": "1.1.1.2",
            "port": 12345
          },
          {
            "address": "::1",
            "port": 12345
          }
        ],
        "remarks": {
          "prefixs": [
            "192.168.129.1/24"
          ],
          "network": "fd67::1/64"
        }
      }
    ]
  }
]
```

</details>

The information of nodes is derived from your `config.json`. As a full example, see configurations under `tests`.

To launch aronet, firstly launch the `daemon`:
```shell
aronet daemon run -c /path/to/config.json
```
And then load the configurations:
```shell
aronet load -c /path/to/config.sjon -r /path/to/registry.json
```


## Explantation

<details>

<summary> VRF mode </summary>

### VRF mode

![topology of vrf mode](/assets/images/topology-vrf.png)



</details>

<details>

<summary> network namespace mode </summary>

### network namespace mode

![topology of vrf mode](/assets/images/topology-netns.png)


</details>
