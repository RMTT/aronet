## Aronet

Auto routed and full mesh overlay network with flexibility based on ipsec, srv6 and babel. Inspired by https://github.com/NickCao/ranet

### Requirements

Linux:
+ kernel >= 5.1
+ enable vrf module
+ firewall port: 6696(babel), 12025(default for node connectivity)
+ some cli tools: iproute2, sysctl, nftables
+ enable following sysctl parameters:
	+ `net.netfilter.nf_hooks_lwtunnel`: let packets from srv6 tunnel be processed by netfilter
	+ `net.ipv6.conf.all.forwarding`
    + `net.ipv4.ip_forward`
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
  "private_key": "-----BEGIN PRIVATE KEY-----\nMC4CAQAwBQYDK2VwBCIEINWlTiVYz8YqhHQ2Gl1mNVNlZ5iH/Y31jZFluWhLkWv/\n-----END PRIVATE KEY-----",
  "organization": "example",
  "common_name": "host-01",
  "daemon": {
    "extra_network": [
      "240e::1/60"
    ],
    "network": "fd00::1/64",
    "mode": "vrf"
  },
  "endpoints": [
    {
      "address": "1.1.1.1",
      "port": 12025,
      "serial_number": 0
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

Note that `aronet` will reserve the `{daemon.network}:ffff::/80` range for internal usage. The majority of this range will be used for srv6 actions. And the ipv4 traffic will be routed via ipv6 light weight tunnel(ipv4 nexthop via ipv6).

<details>

<summary> example registry.json </summary>

#### `registry.json`

`registry.json` contains information of nodes in a mesh overlay network. And your nodes will connect to the nodes in `registry.json`. example:
```json
[
  {
    "public_key": "-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEASCV1oi1Fu7jK31pSvMq1ofahu9BRI9O7zsZZ2bpdmJo=\n-----END PUBLIC KEY-----",
    "organization": "example",
    "nodes": [
      {
        "common_name": "host-01",
        "endpoints": [
          {
            "address": "2.2.2.2",
            "port": 12345,
            "serial_number": 0
          },
          {
            "address": "::1",
            "port": 12345,
            "serial_number": 1
          }
        ],
        "remarks": {
          "network": "fd66::1/64"
        }
      }
    ]
  },
  {
    "public_key": "-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEAgsODQENIjHqks45F0U3tcJbg5rp1bQvb93z3aP75y/c=\n-----END PUBLIC KEY-----",
    "organization": "example2",
    "nodes": [
      {
        "common_name": "host-01",
        "endpoints": [
          {
            "address": "1.1.1.2",
            "port": 12345,
            "serial_number": 0
          },
          {
            "address": "::1",
            "port": 12345,
            "serial_number": 1
          }
        ],
        "remarks": {
          "network": "fd67::1/64",
          "extra_network": [
            "192.168.129.1/24"
          ]
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
And then load the registry:
```shell
aronet load -r /path/to/registry.json
```


## Explanation

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
